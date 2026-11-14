"""Real-CSE selected-scenario frame/controller/Group gate for both modes."""
import json
import os
from pathlib import Path
import sys
from threading import Thread
import time
from uuid import uuid4

from backend.config import Settings
from backend.delivery import DeliverySession,display_callbacks
from backend.evidence import Evidence,source_identity
from backend.notifications import NotificationService,NotificationStore,notification_server
from backend.p0 import IntegrationBlocked,ROOT,subscription_refs,wait_for_cse
from backend.scenario_ingestion import IngestionResult,accept_live_frame
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient,CSEError,ProtocolError,strict_json
from simulator.evacuation import Evacuation
from simulator.events import utc_now
from simulator.scenario_frames import ScenarioFrame,emission,read_trace,source_manifest,trace_digest


class ScenarioSession:
    def __init__(self,settings):
        self.settings = settings
        self.evidence = Evidence(settings.evidence_root,secret_values=(settings.admin_originator,))
        self.namespace = 'fr_'+uuid4().hex[:16]
        self.incident_id = 'inc-'+uuid4().hex
        self.hash = source_manifest()['bundle_sha256']
        self.model = Evacuation()
        self.server = self.worker = self.delivery = None
        self.frames = 0
        self.admin = CSEClient(settings.cse_url,settings.admin_originator,settings.release,
            timeout=settings.request_timeout,evidence=self.evidence)

    def start(self):
        cb = wait_for_cse(self.admin,self.settings)
        self.evidence.write('meta.json',{'test':'T23_DUAL_CORE','started_at_utc':utc_now(),
            'namespace':self.namespace,'incident_id':self.incident_id,'real_CSE':True,'real_MEC':False,
            'input':'SYNTHETIC_SOURCE_REPLAY','deployment_option':'standalone_dev_IN_CSE_NOT_MEC',
            'source_bundle_sha256':self.hash,'assumptions':self.model.navigation.assumptions,
            'policy_sha256':self.model.navigation.policy_hash,'settings':self.settings.public(),
            'observed_cse_runtime':strict_json(self.settings.runtime_info.read_bytes()) if self.settings.runtime_info else None,
            **source_identity(ROOT)})
        self.inbox = NotificationStore(self.evidence.path/'notifications.sqlite3')
        service = NotificationService(self.inbox,cb['csi'],self.settings.release,self.model.navigation.nodes,
            self.evidence,decoder=lambda data:ScenarioFrame.parse(data,self.hash))
        self.server = notification_server(self.settings.bind_host,self.settings.bind_port,service)
        self.worker = Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.resources = bootstrap(self.admin,self.settings.cse_base,self.namespace,self.settings.notification_url,
            self.settings.retention_seconds,decision_policies=True,display_callbacks=display_callbacks(self.settings),dashboard=True)
        self.clients = {role:self.admin.for_actor(actor['ae_id'],role) for role,actor in self.resources['actors'].items()}
        self.controller = self.clients['controller']
        parent = self.resources['containers']['sensor/telemetry']['path']
        sub = self.controller.ensure(parent,23,{'rn':'scenario-sub','nu':[self.settings.notification_url],
            'enc':{'net':[3]},'nct':1})
        refs = subscription_refs(cb['csi'],parent+'/scenario-sub',sub)
        if not refs & self.inbox.verified_refs():
            raise ProtocolError('Actual scenario SUB verification missing')
        service.approve(refs)
        self.delivery = DeliverySession(self.settings,self.admin,self.controller,self.resources,cb,service,
            self.inbox,self.model.navigation,self.incident_id,self.evidence)
        self.delivery.start()
        self.evidence.write('resources.json',self.resources)
        self.evidence.write('navigation.json',self.model.navigation.document())

    def accept_raw(self,raw):
        frame = emission(raw,self.incident_id,self.namespace+':scenario-replay',self.hash)
        parent = self.resources['containers']['sensor/telemetry']['path']
        name = 'frame-'+str(frame.data['sequence'])
        body = frame.to_dict()
        sensor = self.clients['sensor']
        cin = sensor.ensure(parent,4,{'rn':name,'cnf':'application/json:0','con':json.dumps(body,separators=(',',':'))})
        actual = sensor.resource(sensor.retrieve(parent+'/'+name),4)
        if actual['ri'] != cin['ri'] or strict_json(actual['con']) != body:
            raise ProtocolError('Actual scenario CIN read-back differs')
        receipt=self.consume_received(frame,cin['ri'])
        if receipt.state!='ACCEPTED':
            raise ProtocolError('New actual frame did not advance the controller')

    def consume_received(self,frame,cin_ri):
        """Consume a matching durable real callback; never publish on rejection/replay."""
        body=frame.to_dict()
        deadline = time.monotonic()+self.settings.notification_timeout
        while not self.inbox.find(frame.event_id) and time.monotonic() < deadline:
            time.sleep(.02)
        rows = self.inbox.find(frame.event_id)
        if len(rows) != 1 or rows[0]['cin_ri'] != cin_ri or rows[0]['event'] != body:
            raise ProtocolError('Matching durable actual scenario notification missing')
        received = ScenarioFrame.parse(rows[0]['event'],self.hash)
        if received.data['incident_id']!=self.incident_id or received.data['source']!=self.namespace+':scenario-replay':
            receipt=IngestionResult('REJECTED','BOUND_CONTEXT')
        else:
            receipt=accept_live_frame(self.model,received,self.settings,self.hash)
        self.evidence.append('ingestion.jsonl',{'event_id':frame.event_id,'cin_ri':cin_ri,
            'state':receipt.state,'reason':receipt.reason,'source_timestamp_utc':body['timestamp_utc'],
            'sequence':body['sequence'],'route_version':self.model.last['sequence'] if self.model.last else None})
        if receipt.state=='ACCEPTED':
            self.frames += 1
            self.evidence.append('frames.jsonl',{'event_id':frame.event_id,'cin_ri':cin_ri,
                'simulation_second':body['simulation_second'],'sequence':body['sequence'],'zones':len(body['zones'])})
        return receipt

    def write(self,key,name,value,actor='controller'):
        client = self.clients[actor]
        parent = self.resources['containers'][key]['path']
        cin = client.ensure(parent,4,{'rn':name,'cnf':'application/json:0','con':json.dumps(value,separators=(',',':'))})
        actual = client.resource(client.retrieve(parent+'/'+name),4)
        if actual['ri'] != cin['ri'] or strict_json(actual['con']) != value:
            raise ProtocolError('Actual scenario result read-back differs')
        return {'path':parent+'/'+name,'ri':actual['ri'],'content':value}

    def publish(self):
        result = self.model.snapshot()
        common = {k:result[k] for k in ['schema_version','event_id','incident_id','route_version','simulation_second','timestamp_utc','data_origin','policy_sha256']}
        common['source'] = self.namespace+':controller'
        version = str(result['route_version'])
        route = {**common,**result['fixed_route'],'blocked_nodes':sorted(self.model.navigation.blocked),'mode':'FIXED_ORIGIN'}
        record = self.write('controller/routes','route-'+version,route)
        # Full per-person state is deliberately in responder-only CSE records.
        detail = self.write('controller/diagnostics','moving-'+version,{**common,
            'model_provenance':'ASSUMED_NOT_CALIBRATED','population':result['population'],'residents':result['residents']})
        occupancy = self.write('occupancy/observations','occupancy-'+version,{**common,
            'assignment':'LAST_REACHED_NODE','zones':result['zones'],'population':result['population']},actor='occupancy')
        delivered = self.delivery.dispatch(route,allow_incomplete=True)
        self.write('controller/status','status-'+version,{**common,'observed_at_utc':common['timestamp_utc'],
            'delivery':{k:delivered[k] for k in ['state','ack_count']}})
        self.evidence.append('scenario-results.jsonl',{'simulation_second':result['simulation_second'],
            'fixed_route':record,'moving':detail,'occupancy':occupancy,'delivery_state':delivered['state'],
            'ack_count':delivered['ack_count']})
        return result,delivered

    def close(self):
        clean = self.delivery.close() if self.delivery else True
        if self.server:
            self.server.shutdown();self.server.server_close()
            if self.worker:self.worker.join(timeout=5)
        if self.delivery:self.delivery.check_workers()
        return clean


def run(settings,trace_path):
    session = ScenarioSession(settings)
    summary = {'test':'T23_DUAL_CORE','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
        'UI':'NOT_RUN','MEC':'unavailable','latency_samples':0,'model_provenance':'ASSUMED_NOT_CALIBRATED'}
    checks = {};results = []
    try:
        if sys.version_info < (3,11):
            raise IntegrationBlocked('Use the Python 3.12 scenario-core Compose profile')
        session.start()
        session.evidence.write('replay-source.json',{'kind':'SYNTHETIC_SOURCE_REPLAY',
            'trace_sha256':trace_digest(trace_path),'source_bundle_sha256':session.hash})
        for raw in read_trace(trace_path,session.hash):
            session.accept_raw(raw)
            second = raw['simulation_second']
            if second % 60 == 0 or raw['ended']:
                print(json.dumps({'test':'T23_DUAL_CORE','phase':'FRAME_AND_BOTH_MODES','simulation_second':second}),flush=True)
                result,delivery = session.publish()
                if delivery['ack_count'] != 3 or delivery['state'] != 'ALL_ACKED':
                    raise AssertionError('Expected three actual sign ACKs')
                pop = result['population']
                if pop['total'] != pop['evacuated']+pop['remaining']:
                    raise AssertionError('Synthetic population conservation differs')
                results.append(result)
            if session.frames >= 181:
                break
        if len(results) < 2 or session.frames < 61:
            raise AssertionError('Export at least 60 consecutive source seconds')
        last = session.model.last
        before = session.model.snapshot()
        if session.model.accept(ScenarioFrame.parse(last,session.hash)) or session.model.snapshot() != before:
            raise AssertionError('Controller replay is not idempotent')
        checks['actual_complete_frame_CINs_and_notifications'] = True
        checks['fixed_query_does_not_move_residents'] = True
        baseline = [p.to_dict() if hasattr(p,'to_dict') else vars(p).copy() for p in session.model.people]
        session.model.fixed('F10-R9')
        if baseline != [vars(p).copy() for p in session.model.people]:
            raise AssertionError('Fixed query changed resident state')
        checks['actual_Group_three_independent_ACKs'] = True
        checks['duplicate_frame_no_extra_movement'] = True
        checks['movement_and_departure_observed'] = any(p['distance_m'] > 0 for p in results[-1]['residents'])
        checks['some_synthetic_residents_evacuated'] = results[-1]['population']['evacuated'] > 0
        resident,responder = session.clients['resident'],session.clients['responder']
        for key in ['controller/diagnostics','occupancy/observations']:
            path = session.resources['containers'][key]['path']+'/la'
            try:resident.retrieve(path)
            except CSEError as exc:
                if isinstance(exc,ProtocolError) or exc.http_status != 403 or exc.rsc != 4103:raise
            else:raise AssertionError('Resident read private moving/occupancy data')
            responder.resource(responder.retrieve(path),4)
        resident.resource(resident.retrieve(session.resources['containers']['controller/routes']['path']+'/la'),4)
        checks['actual_role_ACP_denials_and_allowed_reads'] = True
        if not all(checks.values()):raise AssertionError('A dual-mode check failed')
        session.evidence.write('assertions.json',checks)
        session.evidence.write('last-model.json',session.model.snapshot())
        summary.update(state='PASS',**{'pass':1},frame_CINs=session.frames,notification_frames=session.frames,
            fixed_mode='PASS',moving_mode='PASS',Group='PASS',milestones=len(results),population=results[-1]['population'])
    except IntegrationBlocked as exc:
        summary.update(state='BLOCKED',blocked=1,reason=str(exc))
    except Exception as exc:
        summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        try:
            if not session.close() and summary['state']=='PASS':
                summary.update(state='FAIL',fail=1,**{'pass':0},reason='Independent devices did not shut down cleanly')
        except Exception as exc:
            summary.update(state='FAIL',fail=1,**{'pass':0},reason='Shutdown '+type(exc).__name__)
        session.evidence.write('summary.json',summary)
    return summary,session.evidence.path


def main():
    summary,path = run(Settings.load(),Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-trace.jsonl')))
    output = json.dumps({'evidence':str(path),**summary},sort_keys=True)
    (path/'tests.txt').write_text('command: '+json.dumps(sys.orig_argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
