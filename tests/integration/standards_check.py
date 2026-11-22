"""Actual isolated CSE discovery + MQTT-to-CSE-to-HTTP/SUB gate.

No broker PUBACK or fixture is accepted as a CSE operation. The main demo is
not contacted; compose.standards.yaml has its own CSE, metadata and volumes.
"""
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from uuid import uuid4

from backend.config import Settings
from backend.evidence import Evidence, source_identity
from backend.notifications import NotificationService, NotificationStore, notification_server
from backend.p0 import ROOT, IntegrationBlocked, default_fixture, subscription_refs, wait_for_cse
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient, CSEError, ProtocolError, strict_json
from onem2m.mqtt import OneM2MMQTT
from simulator.events import fixture_nodes, synthetic_smoke


def run(settings):
    evidence=Evidence(settings.evidence_root, secret_values=(settings.admin_originator,))
    summary={'test':'LOCAL_STANDARDS','state':'NOT_RUN','Hosted':'NOT_CONTACTED',
             'MEC':'unavailable','discovery':'NOT_RUN','MQTT':'NOT_RUN',
             'TLS':'NOT_RUN','originator_authentication':'HEADER_IDENTITY_DEV_ONLY'}
    metadata={'input':'SYNTHETIC','real_CSE':False,'real_MEC':False,
              'deployment':'ISOLATED_STANDALONE_IN_CSE_NOT_MEC',**source_identity(ROOT)}
    server=thread=None
    checks={}
    try:
        if sys.version_info < (3,11):raise IntegrationBlocked('Use Python 3.12 standards Compose image')
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
        if settings.cse_url != 'http://cse:8080':raise ValueError('Standards gate requires its isolated local CSE')
        admin=CSEClient(settings.cse_url,settings.admin_originator,settings.release,
                        timeout=settings.request_timeout,evidence=evidence)
        cb=wait_for_cse(admin,settings)
        metadata.update(real_CSE=True,actual_cse_base=cb,paho_mqtt=version('paho-mqtt'))
        if metadata['paho_mqtt'] != '2.1.0':raise ValueError('Unexpected MQTT client version')
        if settings.runtime_info:metadata['observed_cse_runtime']=strict_json(settings.runtime_info.read_bytes())
        nodes=fixture_nodes(default_fixture())
        store=NotificationStore(evidence.path/'notification-state.sqlite3')
        service=NotificationService(store,cb['csi'],settings.release,nodes,evidence)
        server=notification_server(settings.bind_host,settings.bind_port,service)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        namespace='fr_'+uuid4().hex[:16]
        resources=bootstrap(admin,settings.cse_base,namespace,settings.notification_url,
                            settings.retention_seconds,decision_policies=True)
        evidence.write('resources.json',resources)
        expected={a['ri'] for a in resources['actors'].values()}
        refs=admin.discover('/'+settings.cse_base,label='namespace:'+namespace,resource_type=2)
        found={r.rstrip('/').split('/')[-1] for r in refs}
        checks['actual_label_discovery_finds_exact_eight_AEs']=found==expected and len(refs)==8
        for actor in resources['actors'].values():
            actual=admin.resource(admin.retrieve(actor['path']),2)
            if actual['ri'] not in found or 'namespace:'+namespace not in actual.get('lbl',[]):
                raise ProtocolError('Discovered AE identity/label read-back mismatch')
        checks['each_discovered_AE_read_back_with_actual_identity']=True
        absent=admin.discover('/'+settings.cse_base,label='missing:'+uuid4().hex,resource_type=2)
        checks['nonmatching_label_has_actual_empty_discovery']=absent==[]
        evidence.write('discovery.json',{'query_label':'namespace:'+namespace,'refs':refs,
                                        'actual_AE_resource_IDs':sorted(expected),'negative_refs':absent})
        summary['discovery']='PASS' if all(checks.values()) else 'FAIL'
        controller=admin.for_actor(resources['actors']['controller']['ae_id'],'controller')
        sensor_id=resources['actors']['sensor']['ae_id']
        telemetry=resources['containers']['sensor/telemetry']['path']
        sub=controller.ensure(telemetry,23,{'rn':'controller-sub','nu':[settings.notification_url],
            'enc':{'net':[3]},'nct':1,'lbl':['fire-route','namespace:'+namespace]})
        subrefs=subscription_refs(cb['csi'],telemetry+'/controller-sub',sub)
        checks['actual_SUB_verification']=bool(store.verified_refs() & subrefs)
        service.approve(subrefs)
        mqtt=OneM2MMQTT('mqtt',cb['csi'],sensor_id,evidence=evidence)
        event=synthetic_smoke(nodes,namespace)
        attrs={'rn':'mqtt-'+uuid4().hex,'cnf':'application/json:0',
               'con':json.dumps(event.to_dict(),separators=(',',':'),allow_nan=False)}
        result=mqtt.exchange(telemetry,attributes=attrs)
        cin=CSEClient.resource(result['pc'],4)
        actual=controller.resource(controller.retrieve(telemetry+'/'+attrs['rn']),4)
        checks['MQTT_CREATE_HTTP_readback_same_actual_CIN']=actual==cin and strict_json(actual['con'])==event.to_dict()
        mqtt_get=CSEClient.resource(mqtt.exchange(telemetry+'/'+attrs['rn'])['pc'],4)
        checks['MQTT_RETRIEVE_matches_HTTP_CIN']=mqtt_get==actual
        deadline=time.monotonic()+settings.notification_timeout
        while not store.find(event.event_id) and time.monotonic()<deadline:time.sleep(.05)
        matches=store.find(event.event_id)
        checks['MQTT_created_CIN_triggers_actual_HTTP_SUB']=len(matches)==1 and matches[0]['cin_ri']==cin['ri'] and matches[0]['event']==event.to_dict()
        try:
            mqtt.exchange(resources['containers']['controller/routes']['path'],attributes=attrs)
            checks['MQTT_sensor_route_write_denied']=False
        except CSEError as exc:
            if isinstance(exc,ProtocolError):raise
            checks['MQTT_sensor_route_write_denied']=exc.rsc==4103
        try:
            admin.for_actor(resources['actors']['resident']['ae_id'],'resident').retrieve(telemetry+'/'+attrs['rn'])
            checks['HTTP_resident_sensor_read_denied']=False
        except CSEError as exc:
            if isinstance(exc,ProtocolError):raise
            checks['HTTP_resident_sensor_read_denied']=exc.http_status==403 and exc.rsc==4103
        summary.update(state='PASS' if all(checks.values()) else 'FAIL',MQTT='PASS' if all(checks.values()) else 'FAIL',
                       checks=len(checks),cin_ri=cin['ri'],event_id=event.event_id)
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',reason=str(exc))
    except (OSError,ValueError,CSEError,ImportError) as exc:
        summary.update(state='FAIL',reason=type(exc).__name__)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=3)
        evidence.write('meta.json',metadata);evidence.write('assertions.json',checks)
        evidence.write('summary.json',summary)
    return summary,evidence.path


def main():
    summary,path=run(Settings.load())
    print(json.dumps({**summary,'evidence':str(path)},sort_keys=True))
    return 0 if summary['state']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
