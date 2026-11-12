"""Long-running local simulated incident with actual CSE and device processes."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import queue
import signal
import sys
from threading import Event,Lock,Thread
import time
from uuid import uuid4

from backend.auth import AuthStore
from backend.config import Settings
from backend.delivery import DeliverySession,display_callbacks
from backend.evidence import Evidence,source_identity
from backend.http_api import api_server
from backend.incidents import IncidentStore,canonical
from backend.notifications import NotificationService,NotificationStore,notification_server
from backend.p0 import default_fixture,subscription_refs,wait_for_cse
from backend.views import LiveViews
from mec.risk.routing import BuildingGraph
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient,ProtocolError,strict_json
from onem2m.decisions import publish_pending
from simulator.events import SensorEvent,utc_now
from simulator.occupancy import OccupancyObservation

ROOT=Path(__file__).resolve().parents[1]


class DemoContext:
    def __init__(self,settings):
        self.settings=settings
        self.evidence=Evidence(settings.evidence_root,secret_values=(settings.admin_originator,))
        self.namespace='fr_'+uuid4().hex[:16]
        self.incident_id='inc-'+uuid4().hex
        self.server=self.thread=self.delivery=None
        self.sequences={};self.sensors={}
        self.version=0
        self.graph=BuildingGraph.load(default_fixture())
        self.admin=CSEClient(settings.cse_url,settings.admin_originator,settings.release,timeout=settings.request_timeout,evidence=self.evidence)

    def start(self):
        cb=wait_for_cse(self.admin,self.settings)
        self.cb=cb
        self.evidence.write('meta.json',{'started_at_utc':utc_now(),'test':'P1_APP','input':'SYNTHETIC',
            'real_CSE':True,'real_MEC':False,'deployment_option':'standalone_dev_IN_CSE_NOT_MEC',
            'namespace':self.namespace,'incident_id':self.incident_id,'settings':self.settings.public(),
            'observed_cse_runtime':strict_json(self.settings.runtime_info.read_bytes()) if self.settings.runtime_info else None,
            **source_identity(ROOT)})
        self.inbox=NotificationStore(self.evidence.path/'notifications.sqlite3')
        service=NotificationService(self.inbox,cb['csi'],self.settings.release,self.graph.nodes,self.evidence)
        self.server=notification_server(self.settings.bind_host,self.settings.bind_port,service)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.resources=bootstrap(self.admin,self.settings.cse_base,self.namespace,self.settings.notification_url,
            self.settings.retention_seconds,decision_policies=True,display_callbacks=display_callbacks(self.settings),dashboard=True)
        self.clients={role:self.admin.for_actor(actor['ae_id'],role) for role,actor in self.resources['actors'].items()}
        self.controller=self.clients['controller']
        parent=self.resources['containers']['sensor/telemetry']['path']
        sub=self.controller.ensure(parent,23,{'rn':'controller-sub','nu':[self.settings.notification_url],'nct':1,'enc':{'net':[3]}})
        refs=subscription_refs(cb['csi'],parent+'/controller-sub',sub)
        if not refs&self.inbox.verified_refs():raise ProtocolError('Live sensor SUB verification missing')
        service.approve(refs)
        self.store=IncidentStore(self.evidence.path/'incidents.sqlite3',self.graph,self.namespace+':controller',
                                sensor_ttl=self.settings.sensor_ttl,max_clock_skew=self.settings.max_clock_skew)
        self.delivery=DeliverySession(self.settings,self.admin,self.controller,self.resources,cb,service,self.inbox,self.graph,self.incident_id,self.evidence)
        self.delivery.start()
        self.views=LiveViews(self.clients,self.resources,self.graph,self.incident_id,self.settings)
        self.evidence.write('resources.json',self.resources)

    def observe(self,action):
        # Reconcile earlier partial decision persistence before accepting fresh work.
        # Old pending decisions are not replayed as actuator commands.
        publish_pending(self.store,self.controller,self.resources['containers'],self.evidence)
        node='F2_A' if action=='fire_a' else 'F2_B' if action=='fire_b' else 'F3_ROOM1'
        smoke=action in {'fire_a','fire_b'}
        sensor=('smoke:' if smoke else 'temperature:')+node
        self.sequences[sensor]=self.sequences.get(sensor,0)+1
        event=SensorEvent.parse({'schema_version':1,'event_id':'e-'+uuid4().hex,'incident_id':self.incident_id,
            'sensor_id':sensor,'sensor_type':'synthetic_smoke_index' if smoke else 'temperature_celsius',
            'location_node':node,'value':90 if smoke else 22.5,'unit':'unitless_0_100' if smoke else 'degC',
            'sequence':self.sequences[sensor],'timestamp_utc':utc_now(),'source':self.namespace+':sensor','data_origin':'SYNTHETIC'},self.graph.nodes)
        parent=self.resources['containers']['sensor/telemetry']['path']
        attrs={'rn':'event-'+event.event_id,'cnf':'application/json:0','con':canonical(event.to_dict())}
        cin=self.clients['sensor'].ensure(parent,4,attrs)
        deadline=time.monotonic()+self.settings.notification_timeout
        while not self.inbox.find(event.event_id) and time.monotonic()<deadline:time.sleep(.05)
        rows=self.inbox.find(event.event_id)
        if len(rows)!=1 or rows[0]['cin_ri']!=cin['ri'] or rows[0]['event']!=event.to_dict():
            raise ProtocolError('Live actual sensor notification missing/mismatched')
        actual=SensorEvent.parse(rows[0]['event'],self.graph.nodes)
        update=self.store.accept(actual)
        if update['state']!='ACCEPTED':raise ProtocolError('Live observation rejected')
        records=publish_pending(self.store,self.controller,self.resources['containers'],self.evidence)
        if len(records)!=1:raise ProtocolError('Live route publication differs')
        route=records[0]['route']['content']
        delivery=self.delivery.dispatch(route,allow_incomplete=True)
        self.sensors[sensor]=actual.to_dict()
        self.publish_occupants()
        common={'schema_version':1,'event_id':event.event_id,'incident_id':self.incident_id,
                'route_version':route['route_version'],'timestamp_utc':utc_now(),'source':self.namespace+':controller','data_origin':'SYNTHETIC'}
        detail={**common,'devices':[{'device':role,'status':'APPLIED' if role in delivery['acks'] else 'MISSING',
            'ack_timestamp_utc':delivery['acks'][role]['ack']['timestamp_utc'] if role in delivery['acks'] else None} for role in self.delivery.configs],
            'sensors':list(self.sensors.values())}
        self.write_snapshot('controller/diagnostics','diagnostics-'+str(route['route_version']),detail)
        self.write_snapshot('controller/status','status-'+str(route['route_version']),{**common,
            'observed_at_utc':event.timestamp_utc,'delivery':{'state':delivery['state'],'ack_count':delivery['ack_count'],'expected_ack_count':3}})
        self.version=route['route_version']
        # Keep only bounded in-memory history; immutable wire/event logs retain proof.
        del self.delivery.results[:-20]

    def write_snapshot(self,key,name,value,*,actor='controller'):
        client=self.clients[actor];parent=self.resources['containers'][key]['path']
        attrs={'rn':name,'cnf':'application/json:0','con':canonical(value)}
        cin=client.ensure(parent,4,attrs)
        read=client.resource(client.retrieve(parent+'/'+name),4)
        if cin['ri']!=read['ri'] or strict_json(read['con'])!=value:raise ProtocolError('Snapshot actual read-back differs')

    def publish_occupants(self):
        stamp=utc_now();event_id='occ-'+uuid4().hex
        entries=[OccupancyObservation.parse({'schema_version':1,'event_id':event_id+'-'+zone,'incident_id':self.incident_id,
            'zone_id':zone,'remaining_count':count,'sequence':sum(self.sequences.values()),'timestamp_utc':stamp,
            'source':self.namespace+':occupancy','data_origin':'SYNTHETIC'},self.graph.nodes).to_dict()
            for zone,count in [('F3_ROOM1',2),('F2_B',None)]]
        self.write_snapshot('occupancy/observations',event_id,{'schema_version':1,'incident_id':self.incident_id,
            'timestamp_utc':stamp,'data_origin':'SYNTHETIC','observations':entries},actor='occupancy')

    def close(self):
        if self.delivery:self.delivery.close()
        if self.server and self.thread and self.thread.is_alive():
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)


class DemoApp:
    def __init__(self,settings,*,heartbeat=5):
        self.settings=settings;self.heartbeat=heartbeat
        self.building=json.loads(default_fixture().read_text())
        self.lock=Lock();self.jobs=queue.Queue(maxsize=1);self.stop=Event()
        self.context=None;self.busy=True;self.paused=False;self.state='INITIALIZING'
        self.audit_evidence=Evidence(settings.evidence_root)

    def audit(self,method,path,status,role):
        self.audit_evidence.append('http.jsonl',{'method':method,'path':path,'http_status':status,'role':role})

    def status(self):
        with self.lock:
            return {'state':self.state,'incident_id':self.context.incident_id if self.context else None,
                    'route_version':self.context.version if self.context else None,
                    'busy':self.busy,'paused':self.paused,'data_origin':'SYNTHETIC','MEC':'UNAVAILABLE'}

    def view(self,incident,role,*,diagnostics=False):
        with self.lock:context,busy=self.context,self.busy
        if context is None or context.incident_id!=incident:raise LookupError('Unknown incident')
        result=context.views.read(role,diagnostics=diagnostics)
        with self.lock:changed=self.busy or context is not self.context or result['route_version']!=context.version
        if busy or changed:result.update(guidance_status='PENDING',route=None)
        return result

    def enqueue(self,action):
        with self.lock:
            if self.busy:raise RuntimeError('Busy')
            self.busy=True
            job='job-'+uuid4().hex
            self.jobs.put_nowait((job,action))
            return job

    def reset(self):
        with self.lock:old=self.context;self.context=None;self.state='INITIALIZING'
        if old:old.close()
        context=DemoContext(self.settings)
        try:context.start();context.observe('baseline')
        except Exception:context.close();raise
        with self.lock:self.context=context;self.paused=False;self.state='READY'

    def run(self):
        action='reset'
        while not self.stop.is_set():
            try:
                if action=='reset':self.reset()
                elif action=='pause':self.paused=True
                elif action=='resume':self.paused=False;self.context.observe('baseline')
                elif action=='stop_display_c':
                    if self.context.delivery.processes['display-c'].is_alive():self.context.delivery.stop_device('display-c')
                    self.context.observe('baseline')
                else:self.context.observe(action)
                with self.lock:self.state='READY'
            except Exception as exc:
                self.audit_evidence.event(hop='app_action_failed',action=action,error=type(exc).__name__)
                with self.lock:self.state='DEGRADED'
            finally:
                with self.lock:self.busy=False
            self.next_heartbeat=time.monotonic()+self.heartbeat
            while not self.stop.is_set():
                try:_,action=self.jobs.get(timeout=.25);break
                except queue.Empty:
                    if not self.paused and time.monotonic()>=getattr(self,'next_heartbeat',0):
                        action='baseline' if self.context else 'reset'
                        with self.lock:self.busy=True
                        break
        if self.context:self.context.close()


def main():
    if sys.version_info<(3,11):
        print(json.dumps({'state':'BLOCKED','reason':'Use Python >=3.11 or the app Compose profile'}));return 2
    settings=Settings.load();auth=AuthStore.load(Path(os.getenv('APP_AUTH_FILE','.runtime/auth.json')))
    origin=os.getenv('APP_PUBLIC_ORIGIN','http://127.0.0.1:3000')
    app=DemoApp(settings)
    static_root=ROOT/'frontend'
    if not static_root.is_dir():static_root=Path(sys.prefix)/'share/fire-route/frontend'
    server=api_server(os.getenv('APP_BIND_HOST','127.0.0.1'),int(os.getenv('APP_PORT','3000')),app,auth,origin,static_root)
    worker=Thread(target=app.run,daemon=True);worker.start()
    def shutdown(signum,frame):
        app.stop.set();Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
    print(json.dumps({'state':'APP_LISTENING','origin':origin,'input':'SYNTHETIC','MEC':'UNAVAILABLE'}),flush=True)
    try:server.serve_forever()
    finally:app.stop.set();server.server_close();worker.join(timeout=settings.ack_timeout+settings.request_timeout+10)
    return 0


if __name__=='__main__':raise SystemExit(main())
