"""Actual CSE bad-input/expiry/read-link recovery gate; no simulated CSE replies."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import sys
from threading import Thread
import time
from urllib import request,error
from urllib.parse import urlsplit
from uuid import uuid4

from backend.auth import AuthStore,digest
from backend.config import Settings
from backend.http_api import api_server
from backend.p0 import IntegrationBlocked
from backend.scenario_core import ScenarioSession
from backend.scenario_demo import ScenarioApp
from onem2m.client import CSEClient,ProtocolError,strict_json
from simulator.commands import utc_time
from simulator.displays import DisplayState
from simulator.scenario_frames import ROOT,ScenarioFrame,emission,read_trace,trace_digest


def records(path):
    if not path.exists():return []
    # A concurrently appended final line is read on the next poll.
    return [strict_json(line) for line in path.read_bytes().splitlines(keepends=True) if line.endswith(b'\n')]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def callback(session,ri):
    deadline=time.monotonic()+session.settings.notification_timeout
    while time.monotonic()<deadline:
        for row in records(session.evidence.path/'notifications.jsonl'):
            cin=row.get('body',{}).get('m2m:sgn',{}).get('nev',{}).get('rep',{}).get('m2m:cin',{})
            if cin.get('ri')==ri and row['sender_matches_expected_cse']:
                return row
        time.sleep(.02)
    raise AssertionError('Actual CSE callback was not observed for fault CIN')


class DisconnectEndpoint:
    """Accept and close TCP only; never emit a REST/oneM2M response."""
    def __enter__(self):
        class Handler(socketserver.BaseRequestHandler):
            def handle(handler):
                handler.server.disconnections+=1
                try:handler.request.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        self.server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True;self.server.disconnections=0
        self.worker=Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.url='http://127.0.0.1:'+str(self.server.server_address[1]);return self

    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=5)


@contextmanager
def disconnected_read_clients(session,url):
    original={role:session.clients[role] for role in ['resident','responder']}
    try:
        for role,client in original.items():
            session.clients[role]=CSEClient(url,client.originator,client.release,timeout=2,
                evidence=session.evidence,actor=role+'-read-link-fault')
        yield
    finally:session.clients.update(original)


class RoleProbe:
    def __init__(self,session):
        self.session=session;self.cookies={};self.origin='http://127.0.0.1'
        self.app=ScenarioApp(session.settings,Path('unused-test-trace'))
        self.app.context=session;self.app.busy=False;self.app.state='READY';self.app.paused=True
        codes={role:secrets.token_urlsafe(24) for role in ['resident','responder']}
        session.evidence.secret_values+=tuple(codes.values())
        auth=AuthStore({role:digest(code) for role,code in codes.items()})
        self.server=api_server('127.0.0.1',0,self.app,auth,self.origin,ROOT/'frontend/scenario',actions=set(),snapshots=True)
        self.url=self.origin+':'+str(self.server.server_address[1])
        self.worker=Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        session.evidence.write('linked-http-audit.json',{'evidence':str(self.app.audit_evidence.path)})
        try:
            for role,code in codes.items():self.call('/api/v1/session',role,'POST',{'role':role,'access_code':code})
        except Exception:
            self.close();raise

    def call(self,path,role,method='GET',body=None,expected=200):
        headers={'Host':'127.0.0.1','Origin':self.origin,'Content-Type':'application/json'}
        if role in self.cookies:headers['Cookie']=self.cookies[role]
        req=request.Request(self.url+path,method=method,headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        try:response=request.urlopen(req,timeout=15)
        except error.HTTPError as exc:response=exc
        with response:
            data=strict_json(response.read(1024*1024))
            self.session.evidence.append('http.jsonl',{'method':method,'path':path,'role':role,'http_status':response.status})
            if response.status!=expected:raise AssertionError('Unexpected fault-check HTTP status')
            if response.headers.get('Set-Cookie'):
                self.cookies[role]=response.headers['Set-Cookie'].split(';',1)[0]
            return data

    def views(self,label,expected=200):
        result={role:self.call('/api/v1/incidents/'+self.session.incident_id+'/'+role,role,expected=expected)
            for role in ['resident','responder']}
        self.session.evidence.write(label+'-views.json',result);return result

    def close(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=5)


def run(settings,trace):
    session=ScenarioSession(settings);out=session.evidence;probe=None;checks={};fault_cins=[]
    summary={'test':'P1_SELECTED_FAULTS','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
        'MEC':'unavailable','Hosted':'NOT_CONTACTED','browser':'NOT_RUN',
        'input':'SYNTHETIC_WITH_INTENTIONAL_APPLICATION_FAULTS','model_provenance':'ASSUMED_NOT_CALIBRATED',
        'fault_scope':'INJECTED_APPLICATION_PAYLOAD_AND_API_CSE_READ_LINK_ONLY',
        'full_CSE_outage_recovery':'NOT_RUN','latency_samples':0}
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    def phase(name):print(json.dumps({'test':summary['test'],'phase':name}),flush=True)
    try:
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 scenario-faults Compose profile')
        if urlsplit(settings.cse_url).hostname not in {'cse','localhost','127.0.0.1'}:
            raise IntegrationBlocked('Fault injection requires the explicit local CSE endpoint')
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
        except OSError:
            raise IntegrationBlocked('Network sockets unavailable; real CSE fault gate not run') from None
        session.start();meta=strict_json((out.path/'meta.json').read_bytes())
        out.write('meta.json',{**meta,'test':summary['test'],'fault_scope':summary['fault_scope']})
        out.write('replay-source.json',{'trace_sha256':trace_digest(trace),'source_bundle_sha256':session.hash,
            'fault_payloads':'EXPLICITLY_MUTATED_APPLICATION_ENVELOPES_NOT_SOURCE_ENGINE_FRAMES'})
        source=iter(read_trace(trace,session.hash));phase('REPLAY_TO_KNOWN_STAIR_HAZARD')
        for raw in source:
            session.accept_raw(raw)
            if raw['simulation_second']==30:
                state=fingerprint(session.model.snapshot());current=ScenarioFrame.parse(session.model.last,session.hash)
                ri=records(out.path/'frames.jsonl')[-1]['cin_ri']
                receipt=session.consume_received(current,ri)
                check('active_movement_replay_no_extra_progress',receipt.state=='DUPLICATE' and session.frames==31
                    and any(p['distance_m']>0 for p in session.model.snapshot()['residents'])
                    and fingerprint(session.model.snapshot())==state)
            if raw['simulation_second'] in {0,466}:
                _,delivery=session.publish()
                check('source_'+str(raw['simulation_second'])+'_three_actual_ACKs',
                    delivery['state']=='ALL_ACKED' and delivery['ack_count']==3)
            if raw['simulation_second']%60==0:phase('SOURCE_SECOND_'+str(raw['simulation_second']))
            if raw['simulation_second']==466:break
        check('known_hazard_and_alternative','F4-SA' in session.model.navigation.blocked
            and 'F4-SA' not in session.model.fixed()['path'] and session.frames==467)
        next_raw=next(source);last=session.model.last.copy()
        last_ri=records(out.path/'frames.jsonl')[-1]['cin_ri']
        blocked=set(session.model.navigation.blocked);before=fingerprint(session.model.snapshot())
        route_path=session.resources['containers']['controller/routes']['path']+'/la'
        route_before=session.controller.resource(session.controller.retrieve(route_path),4)
        phase('ACTUAL_CSE_MALFORMED_AND_ORDERING_FAULTS')
        sensor=session.clients['sensor'];parent=session.resources['containers']['sensor/telemetry']['path']
        def inject(label,body,kind):
            name='fault-'+uuid4().hex;payload=body if isinstance(body,str) else json.dumps(body,allow_nan=False)
            cin=sensor.resource(sensor.create(parent,4,{'rn':name,'cnf':'application/json:0','con':payload}),4)
            actual=sensor.resource(sensor.retrieve(parent+'/'+name),4)
            check(label+'_actual_CIN_readback',actual['ri']==cin['ri'] and actual['con']==payload)
            row=callback(session,cin['ri']);check(label+'_callback_kind',row['processing_kind']==kind)
            out.append('fault-cases.jsonl',{'case':label,'cin_ri':cin['ri'],'path':parent+'/'+name,
                'callback_http_status':row['handler_http_status'],'callback_rsc':row['handler_rsc'],
                'processing_kind':kind,'source':'INTENTIONAL_APPLICATION_FAULT'})
            fault_cins.append(cin['ri'])
            return cin,row
        malformed=emission(next_raw,session.incident_id,last['source'],session.hash).to_dict()
        malformed['zones'][0]['fire_index']=101
        for label,body in [('bad_index',malformed),('missing_frame_fields',{})]:
            cin,row=inject(label,body,'invalid_notification')
            check(label+'_rejected',row['handler_http_status']==400 and row['handler_rsc']==4000)
            check(label+'_not_applied',fingerprint(session.model.snapshot())==before)
        cin,row=inject('conflicting_event_identity',last,'conflicting_duplicate')
        check('conflict_rejected',row['handler_http_status']==409 and row['handler_rsc']==4105)
        variants=[('old_sequence',{'simulation_second':465,'sequence':466}),
            ('skipped_frame',{'simulation_second':468,'sequence':469}),
            ('wrong_incident',{'incident_id':'inc-fault-'+uuid4().hex}),
            ('regressing_clock',{'timestamp_utc':(utc_time(last['timestamp_utc'])-timedelta(seconds=1)).isoformat()}),
            ('future_clock',{'timestamp_utc':(datetime.now(timezone.utc)+timedelta(seconds=60+settings.max_clock_skew)).isoformat()}),
            ('expired_clock',{'timestamp_utc':(datetime.now(timezone.utc)-timedelta(seconds=60+settings.sensor_ttl)).isoformat()})]
        for label,changes in variants:
            body=emission(next_raw,session.incident_id,last['source'],session.hash).to_dict();body.update(changes)
            cin,row=inject(label,body,'event')
            check(label+'_durable_receipt_accepted',row['handler_http_status']==200 and row['handler_rsc']==2000)
            receipt=session.consume_received(ScenarioFrame.parse(body,session.hash),cin['ri'])
            expected={'future_clock':'FUTURE','expired_clock':'EXPIRED',
                'regressing_clock':'TIMESTAMP_REGRESSION','wrong_incident':'BOUND_CONTEXT'}.get(label,'ORDER_OR_CONTEXT')
            check(label+'_controller_rejected',receipt.state=='REJECTED' and receipt.reason==expected)
            check(label+'_model_and_hazards_unchanged',fingerprint(session.model.snapshot())==before
                and set(session.model.navigation.blocked)==blocked)
        replay=session.consume_received(ScenarioFrame.parse(last,session.hash),last_ri)
        check('durable_controller_replay_is_idempotent',replay.state=='DUPLICATE' and session.frames==467
            and fingerprint(session.model.snapshot())==before)
        route_after=session.controller.resource(session.controller.retrieve(route_path),4)
        check('faults_do_not_publish_new_guidance',route_after==route_before and len(session.delivery.results)==2)
        probe=RoleProbe(session);phase('INTENTIONAL_API_READ_LINK_DISCONNECT')
        with DisconnectEndpoint() as endpoint:
            with disconnected_read_clients(session,endpoint.url):
                views=probe.views('disconnected',expected=503)
                check('read_disconnect_returns_UNKNOWN_without_private_data',all(v['guidance_status']=='UNKNOWN'
                    and v['route'] is None and not {'population','residents','occupants'}&set(v) for v in views.values()))
                expiry=utc_time(session.delivery.results[-1]['command']['expires_at_utc'])
                wait=max(0,(expiry-datetime.now(timezone.utc)).total_seconds())+1
                phase('SENSOR_SILENCE_WAIT_'+str(round(wait,1))+'_SECONDS');time.sleep(wait)
            check('real_TCP_connections_were_closed',endpoint.server.disconnections>=2)
        phase('READ_LINK_RESTORED_WITHOUT_NEW_SENSOR_DATA')
        stale=probe.views('restored-stale')
        check('reconnect_does_not_freshen_old_observation',all(v['guidance_status']=='STALE' and v['route'] is None
            and v['observed_at_utc']==last['timestamp_utc'] for v in stale.values()))
        check('stale_people_are_omitted',not {'population','residents','occupants'}&set(stale['responder']))
        history=probe.call('/api/v1/incidents/'+session.incident_id+'/snapshot','responder')
        out.write('restored-historical-snapshot.json',history)
        check('history_stays_nonlive_at_original_observation',history['snapshot_kind']=='HISTORICAL'
            and history['is_live'] is False and history['route'] is None
            and history['snapshot_at_utc']==last['timestamp_utc'])
        expired_states={role:DisplayState.snapshot(cfg['state_path']) for role,cfg in session.delivery.configs.items()}
        out.write('expired-device-states.json',expired_states)
        check('independent_displays_expire_old_directions',all(s['route_exit'] is None and s['guidance_status']=='STALE' for s in expired_states.values()))
        session.consume_received(ScenarioFrame.parse(last,session.hash),last_ri)
        check('replay_after_reconnect_keeps_STALE',probe.views('replayed-stale')['resident']['guidance_status']=='STALE')
        phase('FRESH_NEXT_FRAME_RECOVERY_SAME_INCIDENT')
        session.accept_raw(next_raw);result,delivery=session.publish();recovered=probe.views('recovered')
        check('fresh_recovery_same_incident_three_ACKs',delivery['state']=='ALL_ACKED' and delivery['ack_count']==3
            and all(v['incident_id']==session.incident_id and v['route_version']==468 and v['guidance_status']=='ROUTE_AVAILABLE' for v in recovered.values()))
        check('recovery_retains_known_hazards',blocked<=set(session.model.navigation.blocked)
            and not set(result['fixed_route']['path'])&set(session.model.navigation.blocked))
        out.write('last-model.json',session.model.snapshot())
        summary.update(state='PASS',**{'pass':1},checks=len(checks),actual_CSE='PASS',Group='PASS',
            accepted_frames=session.frames,fault_CINs=len(set(fault_cins)),group_operations=len(session.delivery.results),
            recovery_route_version=result['route_version'],sensor_timeout='PASS',read_link_recovery='PASS')
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',blocked=1,reason=str(exc))
    except Exception as exc:summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        if probe:
            try:probe.close()
            except Exception:summary.update(state='FAIL',fail=1,**{'pass':0},reason='Fault-gate HTTP cleanup failed')
        try:
            if not session.close() and summary['state']=='PASS':summary.update(state='FAIL',fail=1,**{'pass':0},reason='Independent display shutdown failed')
        except Exception:summary.update(state='FAIL',fail=1,**{'pass':0},reason='Fault-gate cleanup failed')
        out.write('assertions.json',checks);out.write('summary.json',summary)
    return summary,out.path


def main():
    summary,path=run(Settings.load(),Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-faults.jsonl')))
    output=json.dumps({'evidence':str(path),**summary});(path/'tests.txt').write_text('command: '+json.dumps(sys.argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
