"""Local-only lifecycle test. Preserves volumes and all unrelated CSE resources."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time

from backend.evidence import Evidence,source_identity
from infra.cse.diagnostics import DockerUnavailable,collect,classify,command

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=Evidence(Path('evidence'));summary={'test':'LOCAL_CSE_STABILITY','state':'NOT_RUN',
        'MEC':'unavailable','Hosted':'NOT_CONTACTED','persistence':'NOT_RUN','shutdown':'NOT_RUN'}
    checks={};start_requested=False;stop_requested=False;restarted=False
    try:
        command(['docker','version','--format','{{.Server.Version}}'])
        try:out.write('before-start.json',collect())
        except DockerUnavailable:out.write('before-start.json',{'state':'NO_AVAILABLE_PRIOR_CONTAINER'})
        print(json.dumps({'test':summary['test'],'phase':'BUILD_LOCAL_IMAGES'}),flush=True)
        command(['docker','compose','--profile','stability','build','cse','stability-probe'],timeout=300)
        # A listening socket can precede the CSE's usable oneM2M endpoint.
        # Compose run --no-deps below does not wait for dependency health.
        summary['phase']='WAIT_INITIAL_CSE_HEALTH';start_requested=True
        print(json.dumps({'test':summary['test'],'phase':summary['phase']}),flush=True)
        command(['docker','compose','up','-d','--wait','--wait-timeout','90','cse'],timeout=150)
        ready=collect();out.write('ready-before-prepare.json',ready)
        if ready.get('health_status')!='healthy':
            raise AssertionError('Actual CSE healthcheck not healthy before prepare')
        checks['initial_CSE_healthcheck_passed']=True
        state='/app/'+str(out.path/'persistence.json')
        def probe(phase):
            args=['docker','compose','--profile','stability','run','--rm','-T','--no-deps',
                'stability-probe',phase,'--state',state]
            r=subprocess.run(args,capture_output=True,text=True,timeout=150)
            candidates=[]
            for line in r.stdout.splitlines():
                try:item=json.loads(line)
                except ValueError:continue
                if isinstance(item,dict) and item.get('test')=='CSE_PERSISTENCE_PROBE':candidates.append(item)
            if len(candidates)!=1:raise AssertionError('Persistence probe produced no unique result')
            value=candidates[0];out.write('probe-'+phase+'.json',value)
            if r.returncode or value['state']!='PASS':
                summary.update(failed_probe_phase=phase,failed_probe_evidence=value.get('evidence'),
                    failed_probe_reason=value.get('reason','Unspecified probe failure'),
                    failed_probe_http_status=value.get('http_status'),failed_probe_rsc=value.get('rsc'))
                raise AssertionError('Actual CSE '+phase+' probe failed')
        summary['phase']='PREPARE_ACTUAL_CSE_MARKER'
        print(json.dumps({'test':summary['test'],'phase':'PREPARE_ACTUAL_CSE_MARKER'}),flush=True)
        probe('prepare');running=collect();out.write('running.json',running)
        checks['persistent_data_volume_mounted']=any(m['type']=='volume' and m['destination']=='/data'
            for m in running['mounts'])
        since=datetime.now(timezone.utc).isoformat();begin=time.monotonic()
        summary['phase']='CONTROLLED_CSE_STOP';stop_requested=True
        command(['docker','compose','stop','--timeout','30','cse'],timeout=60)
        elapsed=time.monotonic()-begin
        stopped=collect(since=since);classification=classify(stopped,controlled_stop_elapsed=elapsed,grace_seconds=30)
        out.write('controlled-stop.json',{**stopped,'stop_elapsed_seconds':elapsed,
            'requested_grace_seconds':30,'classification':classification})
        checks['stop_exit_zero_no_OOM']=stopped['state']['ExitCode']==0 and stopped['state']['OOMKilled'] is False
        # collect(since=...) filters logs to this controlled stop; an old
        # successful shutdown must never stand in for this attempt.
        checks['shutdown_complete_marker_observed']=any(e['event']=='SHUTDOWN_COMPLETE'
            for e in stopped.get('logs',{}).get('events',[]))
        summary['shutdown']='PASS' if (checks['stop_exit_zero_no_OOM']
            and checks['shutdown_complete_marker_observed']) else 'FAIL'
        summary['shutdown_classification']=classification
        print(json.dumps({'test':summary['test'],'phase':'RESTART_AND_VERIFY_SAME_RESOURCES',
            'shutdown_classification':classification}),flush=True)
        summary['phase']='WAIT_RESTARTED_CSE_HEALTH'
        command(['docker','compose','start','--wait','--wait-timeout','90','cse'],timeout=150)
        restarted=True
        ready=collect();out.write('ready-before-verify.json',ready)
        if ready.get('health_status')!='healthy':
            raise AssertionError('Actual CSE healthcheck not healthy before verify')
        checks['restarted_CSE_healthcheck_passed']=True
        summary['phase']='VERIFY_SAME_CSE_RESOURCES'
        summary['persistence']='FAIL'  # Attempted below; a failed read is not NOT_RUN.
        probe('verify');after=collect();out.write('after-restart.json',after)
        checks['same_AE_CNT_CIN_and_key_after_restart']=True;summary['persistence']='PASS'
        checks['logs_observed']=all('events' in view.get('logs',{}) for view in [running,after])
        checks['no_default_key_warning']=(not any(e['event']=='DEFAULT_SECRET_WARNING'
            for view in [running,after] for e in view['logs']['events'])) if checks['logs_observed'] else None
        summary.update(state='PASS' if all(checks.values()) else 'FAIL',phase='COMPLETE',checks=checks,
            note='CSE remains running; no volume reset or Hosted request performed')
    except DockerUnavailable:
        summary.update(state='FAIL' if start_requested else 'BLOCKED',reason='Local Docker operation unavailable; inspect recorded substeps')
    except (AssertionError,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        summary.update(state='FAIL',reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        if stop_requested and not restarted:
            try:
                command(['docker','compose','start','cse'],timeout=90)
                summary['recovery_start']='REQUESTED_NOT_HEALTH_VERIFIED'
            except DockerUnavailable:summary['recovery_start']='UNAVAILABLE'
        if summary['state']=='FAIL' and start_requested:
            try:out.write('failure-observation.json',collect())
            except (DockerUnavailable,ValueError,KeyError):
                out.write('failure-observation.json',{'state':'UNAVAILABLE'})
        out.write('assertions.json',checks);out.write('meta.json',{'test':summary['test'],**source_identity(ROOT)})
        out.write('summary.json',summary)
    print(json.dumps({'evidence':str(out.path),**summary}));return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
