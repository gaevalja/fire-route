"""Host-controlled local CSE stop/start; never gives Docker access to the app."""
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import time

from backend.evidence import Evidence,source_identity
from infra.cse.diagnostics import DockerUnavailable,collect,command
from tests.integration.selected_recovery import signal,wait_signal

ROOT=Path(__file__).resolve().parents[1]


def runner_state(cid,run=command):
    if not re.fullmatch(r'[0-9a-f]{12,64}',cid):raise AssertionError('No unique recovery container ID')
    state=json.loads(run(['docker','inspect','--format','{{json .State}}',cid]))
    return {k:state[k] for k in ['Running','ExitCode','OOMKilled']}


def await_phase(control,run_id,name,cid,timeout,*,run=command):
    deadline=time.monotonic()+timeout;last_progress=None
    while time.monotonic()<deadline:
        path=control/(name+'.json')
        if path.exists():return wait_signal(control,run_id,name,.1)
        progress=control/'progress.json'
        if progress.exists():
            data=json.loads(progress.read_text())
            if data.get('run_id')!=run_id:raise AssertionError('Progress run identity differs')
            if data.get('detail')!=last_progress:
                last_progress=data.get('detail');print(json.dumps({'test':'LOCAL_CSE_SCENARIO_RECOVERY','child_phase':last_progress}),flush=True)
        if not runner_state(cid,run)['Running']:
            raise AssertionError('Recovery runner exited before '+name+'; inspect child evidence')
        time.sleep(.5)
    raise AssertionError('Host recovery phase deadline: '+name)


def main():
    out=Evidence(Path('evidence'));control=out.path/'control';control.mkdir()
    run_id=out.path.name;cid=None;stop_requested=False;restarted=False;started=False;checks={}
    summary={'test':'LOCAL_CSE_SCENARIO_RECOVERY','state':'NOT_RUN','MEC':'unavailable','Hosted':'NOT_CONTACTED',
        'scope':'CONTROLLED_CSE_STOP_START_BEFORE_SOURCE_CREATE_APP_AND_DEVICES_SURVIVE','latency_samples':0,
        'process_restart_recovery':'NOT_RUN','partial_fanout_recovery':'NOT_RUN','ambiguous_CREATE_network_fault':'NOT_RUN'}
    def phase(name):
        summary['phase']=name;print(json.dumps({'test':summary['test'],'phase':name}),flush=True)
    try:
        command(['docker','version','--format','{{.Server.Version}}'])
        phase('BUILD_LOCAL_IMAGES')
        command(['docker','compose','--profile','recovery','build','cse','scenario-recovery'],timeout=300)
        phase('WAIT_INITIAL_CSE_HEALTH');started=True
        command(['docker','compose','up','-d','--wait','--wait-timeout','90','cse'],timeout=150)
        before=collect();out.write('before-stop.json',before)
        if before['health_status']!='healthy':raise AssertionError('Initial CSE is not healthy')
        checks['initial_real_CSE_healthy']=True
        # Compose run needs its service alias for real SUB callback reachability.
        cid=command(['docker','compose','--profile','recovery','run','--detach','--no-deps','--use-aliases',
            '--name','fr-recovery-'+run_id,'-e','RECOVERY_RUN_ID='+run_id,
            '-e','RECOVERY_CONTROL=/app/'+str(control),'scenario-recovery'],timeout=60).strip()
        if not re.fullmatch(r'[0-9a-f]{12,64}',cid):raise AssertionError('Unexpected recovery runner identity')
        phase('WAIT_KNOWN_HAZARD_AND_READY_CHECKPOINT')
        ready=await_phase(control,run_id,'ready',cid,900);out.write('child-ready.json',ready)
        child_root=Path(ready['evidence'].removeprefix('/app/'))
        if child_root.parent!=Path('evidence') or not re.fullmatch(r'\d{8}-\d{6}Z-[0-9a-f]{8}',child_root.name):
            raise AssertionError('Unexpected child evidence location')
        summary['child_evidence']=str(child_root)
        checks['private_runner_action_preflight']=ready.get('allowed_actions')==['step']
        if not checks['private_runner_action_preflight']:
            raise AssertionError('Private recovery runner must explicitly allow only step before CSE stop')
        current=command(['docker','compose','ps','--all','--quiet','cse']).strip()
        if current!=before['container_id']:raise AssertionError('CSE container changed before controlled stop')
        phase('CONTROLLED_LOCAL_CSE_STOP');stop_requested=True
        since=datetime.now(timezone.utc).isoformat()
        command(['docker','compose','stop','--timeout','30','cse'],timeout=60)
        stopped=collect(container_id=current,since=since);out.write('controlled-stop.json',stopped)
        checks['stopped_exit_zero_without_OOM_and_shutdown_complete']=(stopped['state']['Running'] is False
            and stopped['state']['ExitCode']==0 and stopped['state']['OOMKilled'] is False
            and any(e['event']=='SHUTDOWN_COMPLETE' for e in stopped.get('logs',{}).get('events',[])))
        if not checks['stopped_exit_zero_without_OOM_and_shutdown_complete']:
            raise AssertionError('Controlled CSE shutdown did not pass')
        signal(control,run_id,'stopped',observation=stopped)
        phase('WAIT_ACTUAL_OUTAGE_OBSERVATION_AND_EXPIRY')
        await_phase(control,run_id,'outage-observed',cid,75)
        checks['runner_stays_alive_while_actual_CSE_is_down']=runner_state(cid)['Running']
        phase('START_SAME_CSE_AND_WAIT_HEALTH')
        command(['docker','compose','start','--wait','--wait-timeout','90','cse'],timeout=150)
        restarted=True;after=collect();out.write('after-restart.json',after)
        checks['same_container_image_healthy_after_start']=(after['container_id']==before['container_id']
            and after['image_id']==before['image_id'] and after['health_status']=='healthy')
        if not checks['same_container_image_healthy_after_start']:raise AssertionError('Restarted CSE identity/health differs')
        signal(control,run_id,'restarted',observation=after)
        phase('WAIT_APPLICATION_AUTO_RECOVERY_AND_INDEPENDENT_ACKS')
        finished=await_phase(control,run_id,'finished',cid,120);out.write('child-result.json',finished)
        checks['real_scenario_recovery_child_PASS']=finished.get('evidence')==ready['evidence'] and finished['summary']['state']=='PASS'
        child_assertions=json.loads((child_root/'assertions.json').read_text())
        checks['child_assertions_all_PASS']=(checks['real_scenario_recovery_child_PASS'] and isinstance(child_assertions,dict)
            and bool(child_assertions) and len(child_assertions)==finished['summary'].get('checks')
            and all(v is True for v in child_assertions.values())
            and json.loads((child_root/'summary.json').read_text())==finished['summary'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and runner_state(cid)['Running']:time.sleep(.2)
        ended=runner_state(cid);out.write('runner-exit.json',ended)
        checks['runner_exits_zero_no_OOM']=ended['Running'] is False and ended['ExitCode']==0 and ended['OOMKilled'] is False
        summary.update(state='PASS' if all(checks.values()) else 'FAIL',phase='COMPLETE',
            note='CSE remains running; runner retained for inspection; no volume reset or Hosted contact')
    except DockerUnavailable:
        summary.update(state='FAIL' if started else 'BLOCKED',reason='Local Docker operation unavailable; no success inferred')
    except (AssertionError,OSError,ValueError,KeyError) as exc:
        summary.update(state='FAIL',reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    except KeyboardInterrupt:
        summary.update(state='FAIL',reason='Operator interrupted controlled recovery test')
    finally:
        if stop_requested and not restarted:
            try:
                command(['docker','compose','start','cse'],timeout=90)
                summary['cleanup_CSE_start']='REQUESTED_NOT_HEALTH_VERIFIED'
            except DockerUnavailable:summary['cleanup_CSE_start']='UNAVAILABLE'
        if cid and re.fullmatch(r'[0-9a-f]{12,64}',cid):
            try:
                if runner_state(cid)['Running']:
                    command(['docker','stop','--time','35',cid],timeout=50)
                    summary['cleanup_runner_stop']='REQUESTED_AFTER_UNFINISHED_TEST'
            except (DockerUnavailable,ValueError,KeyError,AssertionError):summary['cleanup_runner_stop']='UNAVAILABLE'
        if summary['state']=='FAIL' and control.joinpath('finished.json').exists():
            try:
                failure=wait_signal(control,run_id,'finished',.1)
                out.write('failed-child-result.json',failure)
                summary['failed_child_reason']=failure.get('summary',{}).get('reason','Unspecified child failure')
            except (AssertionError,OSError,ValueError):pass
        out.write('assertions.json',checks);out.write('meta.json',{'test':summary['test'],**source_identity(ROOT)})
        out.write('summary.json',summary)
    print(json.dumps({'evidence':str(out.path),**summary}));return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
