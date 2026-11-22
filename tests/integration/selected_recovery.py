"""Actual controlled CSE outage before source CREATE; app/devices stay alive."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import socket
import sys
from threading import Thread
import time

from backend.config import Settings
from backend.p0 import IntegrationBlocked
from backend.scenario_core import ScenarioSession
from backend.scenario_demo import ScenarioApp
from onem2m.client import CSEError,ProtocolError,strict_json
from simulator.commands import utc_time
from simulator.displays import DisplayState
from simulator.scenario_frames import read_trace,trace_digest
from tests.integration.selected_faults import RoleProbe,fingerprint,records


def signal(control,run_id,name,**data):
    value={'run_id':run_id,'phase':name,**data}
    path=control/(name+'.json');temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,allow_nan=False)+'\n');temporary.replace(path)


def wait_signal(control,run_id,name,timeout):
    deadline=time.monotonic()+timeout;path=control/(name+'.json')
    while time.monotonic()<deadline:
        if path.exists():
            data=strict_json(path.read_bytes())
            if not isinstance(data,dict) or data.get('run_id')!=run_id or data.get('phase')!=name:
                raise AssertionError('Recovery control correlation differs')
            return data
        time.sleep(.1)
    raise AssertionError('Recovery control phase deadline: '+name)


def run(settings,trace,control,run_id):
    session=ScenarioSession(settings);out=session.evidence;app=None;worker=None;probe=None;checks={}
    summary={'test':'P1_SELECTED_CSE_RECOVERY','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
        'MEC':'unavailable','Hosted':'NOT_CONTACTED','browser':'NOT_RUN','latency_samples':0,
        'fault_scope':'CONTROLLED_LOCAL_CSE_STOP_START_BEFORE_INPUT_CREATE_APPLICATION_PROCESSES_SURVIVE',
        'process_restart_recovery':'NOT_RUN','partial_fanout_recovery':'NOT_RUN',
        'ambiguous_CREATE_network_fault':'NOT_RUN','input':'SYNTHETIC_SOURCE_REPLAY','model_provenance':'ASSUMED_NOT_CALIBRATED'}
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    def phase(name):
        print(json.dumps({'test':summary['test'],'phase':name}),flush=True)
        signal(control,run_id,'progress',detail=name)
    try:
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 recovery Compose profile')
        if settings.cse_url!='http://cse:8080' or settings.cse_base!='fire-route-dev':
            raise IntegrationBlocked('Recovery gate requires the pinned local Compose CSE')
        if (not re.fullmatch(r'\d{8}-\d{6}Z-[0-9a-f]{8}',run_id)
                or control.name!='control' or control.parent.name!=run_id or not control.is_dir()):
            raise IntegrationBlocked('Run with the local host recovery orchestrator')
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
        except OSError:raise IntegrationBlocked('Actual CSE recovery sockets unavailable') from None
        session.start();meta=strict_json((out.path/'meta.json').read_bytes())
        out.write('meta.json',{**meta,'test':summary['test'],'host_run_id':run_id,'fault_scope':summary['fault_scope']})
        out.write('replay-source.json',{'kind':'SYNTHETIC_SOURCE_REPLAY','trace_sha256':trace_digest(trace),
            'source_bundle_sha256':session.hash})
        source=iter(read_trace(trace,session.hash))
        for raw in source:
            session.accept_raw(raw)
            if raw['simulation_second'] in {0,466}:
                _,delivery=session.publish()
                check('before_'+str(raw['simulation_second'])+'_three_ACKs',delivery['state']=='ALL_ACKED' and delivery['ack_count']==3)
            if raw['simulation_second']%60==0:phase('SOURCE_SECOND_'+str(raw['simulation_second']))
            if raw['simulation_second']==466:break
        check('known_stair_hazard_before_outage',session.frames==467 and 'F4-SA' in session.model.navigation.blocked
            and 'F4-SA' not in session.model.fixed()['path'])
        before=fingerprint(session.model.snapshot());blocked=set(session.model.navigation.blocked)
        retained={k:v['ri'] for k,v in session.resources['containers'].items()}
        route_path=session.resources['containers']['controller/routes']['path']+'/la'
        original_route=session.controller.resource(session.controller.retrieve(route_path),4)
        original_callback_refs=session.inbox.verified_refs()
        original_devices={r:d['pid'] for r,d in session.delivery.ready.items()}
        sub_paths={'source':(session.controller,session.resources['containers']['sensor/telemetry']['path']+'/scenario-sub')}
        for role in session.delivery.configs:
            sub_paths[role+'-command']=(session.clients[role],session.resources['containers'][role+'/commands']['path']+'/display-sub')
            sub_paths[role+'-ack']=(session.controller,session.resources['containers'][role+'/acks']['path']+'/controller-sub')
        old_subs={name:client.resource(client.retrieve(path),23)['ri'] for name,(client,path) in sub_paths.items()}
        out.write('subscriptions-before-stop.json',{name:{'path':sub_paths[name][1],'ri':ri} for name,ri in old_subs.items()})
        app=ScenarioApp(settings,trace);app.context=session;app.iterator=source
        app.busy=False;app.state='READY';app.paused=True
        probe=RoleProbe(session,app=app,actions={'step'})
        check('private_probe_action_preflight',probe.actions==frozenset({'step'}))
        worker=Thread(target=app.run,kwargs={'initial_action':'pause'},daemon=True);worker.start()
        phase('READY_FOR_CONTROLLED_CSE_STOP')
        signal(control,run_id,'ready',evidence=str(out.path),incident_id=session.incident_id,
            allowed_actions=sorted(probe.actions))
        stopped=wait_signal(control,run_id,'stopped',120)['observation']
        out.write('host-controlled-stop.json',stopped)
        check('actual_host_stop_is_graceful_without_OOM',stopped['state']['Running'] is False
            and stopped['state']['ExitCode']==0 and stopped['state']['OOMKilled'] is False
            and any(e['event']=='SHUTDOWN_COMPLETE' for e in stopped.get('logs',{}).get('events',[])))
        phase('REQUEST_NEXT_FRAME_WHILE_ACTUAL_CSE_IS_STOPPED')
        probe.call('/api/v1/scenario','responder','POST',{'action':'step'},expected=202)
        deadline=time.monotonic()+settings.request_timeout+5
        while time.monotonic()<deadline and app.status()['state']!='RECOVERING':
            if app.status()['state']=='DEGRADED':raise AssertionError('Unexpected degraded source before recovery')
            time.sleep(.05)
        check('production_worker_enters_RECOVERING',app.status()['state']=='RECOVERING')
        pending=session.pending_input.frame.to_dict();out.write('pending-input.json',pending)
        check('pending_sequence_is_not_skipped',pending['sequence']==468 and app.pending_raw['simulation_second']==467)
        unknown=probe.views('actual-cse-down',expected=503)
        check('both_roles_unknown_no_route_or_people',all(v['guidance_status']=='UNKNOWN' and v['route'] is None
            and not {'population','residents','occupants'}&set(v) for v in unknown.values()))
        phase('ACTUAL_CSE_DOWN_WAIT_FOR_SOURCE_AND_DISPLAY_EXPIRY')
        wait=max(0,settings.sensor_ttl-(datetime.now(timezone.utc)-utc_time(pending['timestamp_utc'])).total_seconds())+1
        time.sleep(wait)
        check('model_clock_hazards_and_people_frozen_while_CSE_down',session.frames==467
            and fingerprint(session.model.snapshot())==before and set(session.model.navigation.blocked)==blocked)
        check('pending_emission_not_restamped_without_CSE_evidence',session.pending_input.frame.to_dict()==pending)
        expired={r:DisplayState.snapshot(c['state_path']) for r,c in session.delivery.configs.items()}
        out.write('expired-device-states.json',expired)
        check('three_surviving_devices_expire_old_guidance',all(p.is_alive() for p in session.delivery.processes.values())
            and all(s['guidance_status']=='STALE' and s['route_exit'] is None for s in expired.values()))
        check('outage_does_not_dispatch_or_ACK_extra_commands',len(session.delivery.results)==2)
        signal(control,run_id,'outage-observed',evidence=str(out.path))
        restarted=wait_signal(control,run_id,'restarted',120)['observation'];out.write('host-restarted.json',restarted)
        check('same_actual_CSE_container_healthy_after_start',restarted['container_id']==stopped['container_id']
            and restarted['health_status']=='healthy' and restarted['state']['Running'] is True)
        runtime=strict_json(settings.runtime_info.read_bytes())
        original_runtime=meta['observed_cse_runtime']
        check('same_verified_CSE_runtime_config_and_patch',runtime['config_sha256']==original_runtime['config_sha256']
            and runtime['installed_version']==original_runtime['installed_version']
            and runtime['shutdown_patch']==original_runtime['shutdown_patch'] and runtime['shutdown_patch']['verified'] is True)
        phase('WAIT_AUTOMATIC_SAME_INCIDENT_RECOVERY')
        deadline=time.monotonic()+settings.startup_timeout+settings.ack_timeout+15
        while time.monotonic()<deadline:
            state=app.status()
            if state['state']=='DEGRADED':raise AssertionError('Production worker recovery failed closed; inspect child evidence')
            if state['state']=='READY' and not state['busy'] and session.frames==468:break
            time.sleep(.1)
        check('recovered_same_incident_version_once_and_paused',app.status()['state']=='READY' and app.status()['paused']
            and app.status()['incident_id']==session.incident_id and session.frames==468 and session.pending_input is None
            and app.pending_raw is None and app.remaining==0)
        recovered=probe.views('recovered')
        check('both_real_role_views_recovered_fresh',all(v['route_version']==468 and v['guidance_status']=='ROUTE_AVAILABLE'
            and v['incident_id']==session.incident_id for v in recovered.values()))
        check('known_hazards_retained_after_actual_CSE_outage',blocked<=set(session.model.navigation.blocked)
            and not set(session.model.fixed()['path'])&set(session.model.navigation.blocked))
        check('new_delivery_has_three_independent_ACKs',len(session.delivery.results)==3
            and session.delivery.results[-1]['state']=='ALL_ACKED' and session.delivery.results[-1]['ack_count']==3)
        for key,value in session.resources['containers'].items():
            owner=session.clients[key.split('/')[0]]
            check('retained_CNT_'+key,owner.resource(owner.retrieve(value['path']),3)['ri']==retained[key])
        for role,value in session.resources['actors'].items():
            actual=session.admin.resource(session.admin.retrieve(value['path']),2)
            check('retained_AE_'+role,actual['ri']==value['ri'] and actual['aei']==value['ae_id'])
        historical=session.controller.resource(session.controller.retrieve(
            session.resources['containers']['controller/routes']['path']+'/'+original_route['rn']),4)
        check('old_route_CIN_not_recreated_or_rewritten',historical==original_route)
        actual_group=session.controller.resource(session.controller.retrieve(session.delivery.group['path']),9)
        check('original_CSE_Group_and_SUBs_retained',actual_group['ri']==session.delivery.group['ri']
            and set(actual_group['mid'])==set(session.delivery.group['resource']['mid'])
            and original_callback_refs<=session.inbox.verified_refs()
            and all(session.delivery.processes[r].pid==pid and session.delivery.processes[r].is_alive()
                for r,pid in original_devices.items()))
        for name,(client,path) in sub_paths.items():
            check('retained_SUB_'+name,client.resource(client.retrieve(path),23)['ri']==old_subs[name])
        for key in ['controller/diagnostics','occupancy/observations']:
            try:session.clients['resident'].retrieve(session.resources['containers'][key]['path']+'/la')
            except CSEError as exc:
                check('restored_ACP_denies_'+key,not isinstance(exc,ProtocolError) and exc.http_status==403 and exc.rsc==4103)
            else:raise AssertionError('Resident private read permitted after CSE restart')
        resampled=records(out.path/'source-recovery.jsonl')
        check('only_proven_absent_synthetic_observation_is_resampled',len(resampled)==1
            and resampled[0]['previous_event_id']==pending['event_id'] and resampled[0]['previous_timestamp_utc']==pending['timestamp_utc']
            and resampled[0]['actual_http_status']==404 and resampled[0]['actual_rsc']==4004
            and resampled[0]['event_id']==session.model.last['event_id'] and pending['event_id']!=session.model.last['event_id'])
        requests=records(out.path/'requests.jsonl');source_path=session.resources['containers']['sensor/telemetry']['path']
        check('one_CREATE_for_recovered_source_no_POST_replay',len([r for r in requests if r['method']=='POST'
            and r['path']==source_path and (r.get('request_body') or {}).get('m2m:cin',{}).get('rn')=='frame-468'])==1)
        check('actual_input_transport_failure_is_recorded',any(r.get('actor')=='sensor' and r.get('error')=='TransportError' for r in requests))
        out.write('last-model.json',session.model.snapshot())
        summary.update(state='PASS',**{'pass':1},checks=len(checks),actual_CSE='PASS',controlled_outage='PASS',
            source_recovery='PASS',frame_CINs=session.frames,group_operations=len(session.delivery.results),
            independent_ACKs=sum(d['ack_count'] for d in session.delivery.results),recovery_route_version=468)
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',blocked=1,reason=str(exc))
    except Exception as exc:summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        try:
            if probe:probe.close()
            if worker:
                app.stop.set();worker.join(timeout=30)
                if worker.is_alive() or any(p.is_alive() or p.exitcode!=0 for p in session.delivery.processes.values()):
                    raise AssertionError('Recovery worker/device shutdown failed')
            elif not session.close():raise AssertionError('Recovery device cleanup failed')
        except Exception:summary.update(state='FAIL',fail=1,**{'pass':0},reason='Recovery gate cleanup failed')
        out.write('assertions.json',checks);out.write('summary.json',summary)
        if control.is_dir() and control.parent.name==run_id:
            signal(control,run_id,'finished',evidence=str(out.path),summary=summary)
    return summary,out.path


def main():
    summary,path=run(Settings.load(),Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-recovery.jsonl')),
        Path(os.getenv('RECOVERY_CONTROL','.runtime/not-active')),os.getenv('RECOVERY_RUN_ID',''))
    output=json.dumps({'evidence':str(path),**summary});(path/'tests.txt').write_text('command: '+json.dumps(sys.argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
