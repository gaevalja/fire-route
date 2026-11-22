"""Read-only local Docker observations; never publish env/config/secret values."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import re
import subprocess


class DockerUnavailable(RuntimeError):pass


def command(args,*,timeout=30):
    try:r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):raise DockerUnavailable('Local Docker command unavailable') from None
    if r.returncode:raise DockerUnavailable('Local Docker command failed (exit '+str(r.returncode)+')')
    return r.stdout+r.stderr if args[:2]==['docker','logs'] else r.stdout


def inspect_view(raw):
    state=raw['State'];host=raw.get('HostConfig',{});config=raw.get('Config',{})
    health=state.get('Health',{}).get('Status')
    return {'container_id':raw['Id'],'image_id':raw.get('Image'),
        'state':{k:state.get(k) for k in ['Status','Running','ExitCode','OOMKilled','Pid','StartedAt','FinishedAt']},
        'health_status':health if health in {'starting','healthy','unhealthy'} else None,
        'runtime_error_present':bool(state.get('Error')),
        'restart_count':raw.get('RestartCount'),
        'stop_signal':config.get('StopSignal') or 'SIGTERM',
        'stop_timeout_seconds':config.get('StopTimeout'),
        'limits':{k:host.get(k) for k in ['Memory','MemorySwap','OomKillDisable','PidsLimit']},
        'mounts':[{'type':m.get('Type'),'name':m.get('Name'),'destination':m.get('Destination')}
                  for m in raw.get('Mounts',[])]}


def event_view(raw):
    attrs=raw.get('Actor',{}).get('Attributes',{})
    # Docker embeds the full exec command after a colon in Action. It can
    # contain credentials; keep only the event kind, never the command.
    action=raw.get('Action',raw.get('status'))
    action=action.split(':',1)[0] if isinstance(action,str) else ''
    action=action if re.fullmatch(r'[a-z_]+',action) else 'OTHER'
    return {'action':action,'time':raw.get('time'),
        'time_nano':raw.get('timeNano'),'signal':attrs.get('signal'),'exit_code':attrs.get('exitCode')}


def log_view(raw):
    markers={'CSE started':'STARTED','CSE shutting down':'SHUTDOWN_STARTED',
        'CSE shut down complete':'SHUTDOWN_COMPLETE','Using default secret key':'DEFAULT_SECRET_WARNING'}
    events=[]
    for line in raw.splitlines():
        line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line)
        for marker,name in markers.items():
            if marker in line:
                first=line.split(' ',1)[0]
                stamp=first if re.fullmatch(r'[0-9T:.+Z-]+',first) else None
                events.append({'timestamp':stamp,'event':name})
    return {'events':events,'raw_log_sha256':hashlib.sha256(raw.encode()).hexdigest(),
        'raw_line_count':len(raw.splitlines()),'raw_log_retained':False}


SOURCE_PROBE = '''import ast,hashlib,json
from importlib.metadata import distribution
d=distribution('acmecse');records=[];count=0
for name in d.files or []:
 if not str(name).startswith('acmecse/') or not str(name).endswith('.py'):continue
 path=d.locate_file(name)
 try:body=path.read_bytes();tree=ast.parse(body)
 except (OSError,SyntaxError):continue
 count+=1;signals=[];interrupts=[]
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='signal' and node.func.attr=='signal' and len(node.args)>=2:
   arg=node.args[0];handler=node.args[1]
   if isinstance(arg,ast.Attribute) and arg.attr in {'SIGTERM','SIGINT'}:
    label=handler.id if isinstance(handler,ast.Name) else handler.attr if isinstance(handler,ast.Attribute) else type(handler).__name__
    signals.append({'line':node.lineno,'signal':arg.attr,'handler_identifier':label})
  if isinstance(node,ast.ExceptHandler) and isinstance(node.type,ast.Name) and node.type.id=='KeyboardInterrupt':interrupts.append(node.lineno)
 if signals or interrupts:records.append({'path':str(name),'sha256':hashlib.sha256(body).hexdigest(),'signal_registrations':signals,'keyboard_interrupt_lines':interrupts})
print(json.dumps({'installed_version':d.version,'python_files_scanned':count,'records':records,'scope':'STATIC_INSTALLED_SOURCE_NOT_RUNTIME_HANDLER_STATE'}))'''


def collect(*,container_id=None,since=None,run=command):
    cid=container_id or run(['docker','compose','ps','--all','--quiet','cse']).strip()
    if not re.fullmatch(r'[0-9a-f]{12,64}',cid):raise DockerUnavailable('No unique local CSE container found')
    raw=json.loads(run(['docker','inspect',cid]))
    if not isinstance(raw,list) or len(raw)!=1:raise DockerUnavailable('Unexpected Docker inspect result')
    observed=inspect_view(raw[0]);now=datetime.now(timezone.utc);logs_since=since
    if since is None:
        ended=observed['state'].get('FinishedAt')
        # Docker reports nanoseconds; Python 3.10's fromisoformat accepts only
        # microseconds. Preserve the real exit time instead of falling back to now.
        if isinstance(ended,str):
            ended=re.sub(r'(\.\d{6})\d+(?=Z$|[+-]\d{2}:\d{2}$)',r'\1',ended)
        try:point=datetime.fromisoformat(ended.replace('Z','+00:00')) if ended and not ended.startswith('0001-') else now
        except ValueError:point=now
        since=(point-timedelta(seconds=90)).isoformat()
    observed['event_window']={'since':since,'until':now.isoformat()}
    for key,args,decode in [
        ('events',['docker','events','--since',since,'--until',now.isoformat(),'--filter','container='+cid,'--format','{{json .}}'],lambda s:[event_view(json.loads(line)) for line in s.splitlines() if line.strip()]),
        ('logs',['docker','logs','--timestamps','--tail','300']+
            (['--since',logs_since] if logs_since else [])+[cid],log_view),
    ]:
        try:observed[key]=decode(run(args))
        except (DockerUnavailable,ValueError):observed[key]={'state':'UNAVAILABLE'}
    if observed['state']['Running']:
        try:
            stats=json.loads(run(['docker','stats','--no-stream','--format','{{json .}}',cid]))
            observed['memory_sample']={k:stats.get(k) for k in ['MemUsage','MemPerc','PIDs','CPUPerc']}
            observed['memory_sample']['scope']='ONE_SAMPLE_NOT_PEAK_OR_HISTORY'
        except (DockerUnavailable,ValueError):observed['memory_sample']={'state':'UNAVAILABLE'}
        try:observed['installed_signal_source']=json.loads(run(['docker','exec',cid,'python','-c',SOURCE_PROBE]))
        except (DockerUnavailable,ValueError):observed['installed_signal_source']={'state':'UNAVAILABLE'}
    else:
        observed['memory_sample']={'state':'NOT_RUN','reason':'Container is stopped; no historical peak inferred'}
    observed['observed_at_utc']=now.isoformat()
    return observed


def classify(observation,*,controlled_stop_elapsed=None,grace_seconds=None):
    state=observation['state'];events=observation.get('events',[])
    events=events if isinstance(events,list) else []
    if state.get('OOMKilled') is True or any(e.get('action')=='oom' for e in events):return 'OOM_OBSERVED'
    if state.get('Running'):return 'RUNNING'
    if state.get('ExitCode')==137:
        signals={str(e.get('signal')) for e in events if e.get('action')=='kill'}
        expected={'SIGTERM':{'15','SIGTERM'},'15':{'15','SIGTERM'},
            'SIGINT':{'2','SIGINT'},'2':{'2','SIGINT'}}.get(observation.get('stop_signal','SIGTERM'),set())
        if (state.get('OOMKilled') is False and signals & expected and signals & {'9','SIGKILL'}
                and controlled_stop_elapsed is not None and grace_seconds is not None
                and controlled_stop_elapsed>=grace_seconds-1):return 'CONTROLLED_STOP_TIMEOUT_SUPPORTED'
        return 'EXIT_137_UNDETERMINED'
    if state.get('ExitCode')==0:return 'EXIT_ZERO_OBSERVED'
    return 'OTHER_EXIT'


def main():
    from pathlib import Path
    from backend.evidence import Evidence
    out=Evidence(Path('evidence'));summary={'test':'CSE_READ_ONLY_DIAGNOSTICS','state':'NOT_RUN'}
    try:
        data=collect();data['classification']=classify(data);out.write('docker-observation.json',data)
        summary.update(state='PASS',classification=data['classification'],scope='OBSERVATION_NOT_SHUTDOWN_OR_PERSISTENCE_PASS')
    except (DockerUnavailable,ValueError,KeyError):summary.update(state='BLOCKED',reason='Local Docker observation unavailable')
    out.write('summary.json',summary);print(json.dumps({'evidence':str(out.path),**summary}))
    return 0 if summary['state']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
