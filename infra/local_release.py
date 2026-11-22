"""Serial local acceptance, optionally from a clean archived Git commit.

Uses a separate Compose project/loopback ports; never runs git push, deploys
externally, resets CSE volumes or counts an unattempted step as successful.
"""
import argparse
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile

from backend.evidence import Evidence,source_identity

ROOT=Path(__file__).resolve().parents[1]
PORT_SETTINGS=('CSE_HOST_PORT','APP_HOST_PORT','SCENARIO_HOST_PORT','SECURE_HOST_PORT')


def available_loopback_ports():
    """Ask the OS for four distinct free ports without touching other services.

    Keep all selections bound until the set is complete so the allocator cannot
    return the same port twice. Release before Compose binds; a later external
    race remains a real startup failure, never a reason to stop another service.
    """
    try:
        with ExitStack() as reserved:
            ports={}
            for name in PORT_SETTINGS:
                listener=reserved.enter_context(socket.socket(socket.AF_INET,socket.SOCK_STREAM))
                listener.bind(('127.0.0.1',0))
                port=listener.getsockname()[1]
                if type(port) is not int or not 1024<=port<=65535 or str(port) in ports.values():
                    raise RuntimeError('OS did not allocate distinct unprivileged loopback ports')
                ports[name]=str(port)
            return ports
    except OSError:
        raise RuntimeError('Cannot allocate isolated loopback ports; local socket access is required') from None


def unpack_commit(archive: bytes, destination: Path):
    """Only regular files/directories from the reviewed Git archive."""
    destination.mkdir(parents=True,exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        members=stream.getmembers()
        for member in members:
            path=(destination/member.name).resolve()
            if not path.is_relative_to(destination.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe source archive member')
        for member in members:
            path=destination/member.name
            if member.isdir():path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                with stream.extractfile(member) as source:path.write_bytes(source.read())
                path.chmod(member.mode & 0o777)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--clean-checkout',action='store_true')
    args=parser.parse_args()
    evidence=Evidence(ROOT/'evidence');work=ROOT
    summary={'test':'LOCAL_RELEASE_ACCEPTANCE','state':'NOT_RUN','Hosted':'NOT_CONTACTED',
        'MEC':'unavailable','source':'CLEAN_COMMIT_ARCHIVE' if args.clean_checkout else 'CURRENT_WORKTREE',
        'steps':[],'external_publication':'NOT_PERFORMED'}
    environment=os.environ.copy()
    environment.update(COMPOSE_PROJECT_NAME='fr-accept-'+evidence.path.name.lower())
    # Explicit loopback-only, isolated test endpoints; never inherit remote targets.
    environment.update(FIREROUTE_PROFILE='local',CSE_CONTAINER_BASE_URL='http://cse:8080',CSE_ORIGINATOR='CAdmin')
    commands=[('unit',['make','test-unit']),('frontend',['make','test-frontend']),
        ('source-engine',['make','test-scenario']),('browser-driver',['make','test-browser-driver']),
        ('compose',['make','compose-check']),('standards',['make','p1-standards']),
        ('CSE-core',['make','p0-smoke']),('routes',['make','p1-routes']),('Group-ACK',['make','p1-group']),
        ('selected-HTTP',['make','p1-scenario-dashboard']),('hazards',['make','p1-hazards']),
        ('input-faults',['make','p1-faults']),('CSE-recovery',['make','p1-recovery']),
        ('observer-latency',['make','p1-latency']),('HTTP-demo',['make','demo-scenario-up']),
        ('rendered-browser',['node','tests/browser/dashboard.mjs']),
        ('HTTPS-demo',['make','demo-secure-up']),('HTTPS-certificate-role',['make','test-https']),
        ('rendered-HTTPS-browser',['node','tests/browser/dashboard.mjs','--https'])]
    try:
        for binary in ['docker','make','node',os.getenv('CHROME_BIN','google-chrome'),'openssl']:
            if not shutil.which(binary):raise RuntimeError('Missing required local tool: '+binary)
        docker=subprocess.run(['docker','info','--format','{{.ServerVersion}}'],capture_output=True,text=True,timeout=10)
        if docker.returncode:raise RuntimeError('Docker access unavailable; run from your Docker-capable terminal')
        if args.clean_checkout:
            if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):
                raise RuntimeError('Commit reviewed changes before clean-checkout verification')
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            archive=subprocess.check_output(['git','archive','--format=tar',commit],cwd=ROOT)
            work=ROOT/'.runtime/releases'/evidence.path.name
            unpack_commit(archive,work);summary['git_commit']=commit
        environment.update(available_loopback_ports())
        evidence.write('meta.json',{'worktree':str(work),'isolation_project':environment['COMPOSE_PROJECT_NAME'],
            'ports':{k:environment[k] for k in PORT_SETTINGS},
            **source_identity(work)})
        summary['state']='RUNNING'
        for name,command in commands:
            if name in {'rendered-browser','rendered-HTTPS-browser'}:
                key='SECURE_HOST_PORT' if name=='rendered-HTTPS-browser' else 'SCENARIO_HOST_PORT'
                command=[*command,'--port',environment[key]]
            print(json.dumps({'test':summary['test'],'phase':name}),flush=True)
            step={'name':name,'exit_code':None,'state':'RUNNING'}
            summary['steps'].append(step);evidence.write('progress.json',summary)
            output=evidence.path/(name+'.txt')
            with output.open('w') as log:
                result=subprocess.run(command,cwd=work,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            step.update(exit_code=result.returncode,state='PASS' if result.returncode==0 else 'FAIL')
            evidence.write('progress.json',summary)
            if result.returncode:raise ValueError('Acceptance step failed: '+name+'; inspect its retained log/evidence')
        summary['state']='PASS'
    except RuntimeError as exc:summary.update(state='BLOCKED',reason=str(exc))
    except KeyboardInterrupt:summary.update(state='FAIL',reason='INTERRUPTED; current step is not successful')
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        summary.update(state='FAIL',reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
    finally:
        for step in summary['steps']:
            if step['state']=='RUNNING':step.update(state='FAIL',reason='Interrupted or failed before exit status')
        if summary['steps']:
            # Only our isolated project; volume/evidence deletion is never requested.
            try:
                with (evidence.path/'cleanup.txt').open('w') as log:
                    result=subprocess.run(['make','down'],cwd=work,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=90)
                    standards=subprocess.run(['docker','compose','-p',environment['COMPOSE_PROJECT_NAME']+'-standards',
                        '-f','compose.standards.yaml','down'],cwd=work,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=90)
                summary['cleanup_exit_code']=max(result.returncode,standards.returncode)
            except (OSError,subprocess.SubprocessError):summary['cleanup_exit_code']='UNVERIFIED'
            if summary['cleanup_exit_code']!=0 and summary['state']=='PASS':summary['state']='FAIL'
        summary['planned_steps']=len(commands);summary['unattempted_steps']=len(commands)-len(summary['steps'])
        evidence.write('summary.json',summary)
    print(json.dumps({**summary,'evidence':str(evidence.path)},sort_keys=True))
    return 0 if summary['state']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
