"""Isolated real CSE + certificate-bound originators. Never contacts the demo.

Gateway denials are HTTP transport denials, not invented oneM2M ACP responses.
The callback relay is private HTTP and explicitly outside this TLS claim.
"""
import json
import os
from pathlib import Path
import socket
import ssl
import sys
from threading import Thread
import time
from urllib.error import URLError
from uuid import uuid4

from backend.config import Settings
from backend.evidence import Evidence,source_identity
from backend.notifications import NotificationService,NotificationStore,notification_server
from backend.p0 import ROOT,IntegrationBlocked,default_fixture,subscription_refs,wait_for_cse
from infra.cse.pki import prepare,issue
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient,CSEError,HTTPTransport,TransportError,strict_json
from onem2m.security import MutualTLSTransport
from simulator.events import fixture_nodes,synthetic_smoke


def tls_cause(exc):
    cause=exc.__cause__
    if isinstance(cause,URLError):cause=cause.reason
    if isinstance(cause,ssl.SSLCertVerificationError):return True
    # EOF/reset, DNS failure or a generic TLS error is not certificate-denial
    # evidence. Only explicit peer authentication alerts qualify here.
    return isinstance(cause,ssl.SSLError) and getattr(cause,'reason','') in {
        'TLSV13_ALERT_CERTIFICATE_REQUIRED','TLSV1_ALERT_UNKNOWN_CA',
        'SSLV3_ALERT_BAD_CERTIFICATE','TLSV1_ALERT_BAD_CERTIFICATE',
        'TLSV1_ALERT_ACCESS_DENIED'}


def gateway_rejection(response):
    return response.status in {400,403,495,496} and not any(k.lower()=='x-m2m-rsc' for k in response.headers)


def run():
    evidence=Evidence(Path(os.getenv('EVIDENCE_ROOT','evidence')))
    summary={'test':'LOCAL_CERTIFICATE_BOUND_CSE','state':'NOT_RUN','Hosted':'NOT_CONTACTED','MEC':'unavailable',
             'real_CSE':False,'gateway':'NGINX_MTLS_NOT_A_CSE','callback_transport':'PRIVATE_HTTP_NOT_TLS',
             'main_demo':'NOT_CONTACTED','MQTT':'NOT_RUN'}
    checks={};server=thread=None;metadata=source_identity(ROOT)
    def phase(name):
        summary['phase']=name
        print(json.dumps({'test':summary['test'],'phase':name}),flush=True)
    try:
        phase('PRECHECK')
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 security profile')
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
        except OSError:raise IntegrationBlocked('Network sockets unavailable') from None
        url=os.getenv('CSE_SECURITY_URL','https://gateway:8443')
        if url!='https://gateway:8443':raise ValueError('Security gate requires the isolated gateway')
        directory=prepare(Path(os.getenv('CSE_PKI_DIRECTORY','.runtime/cse-mtls')))
        # Only this privileged enrollment runner can mint actor credentials.
        def actor_transport(originator,actor):
            if originator=='C' and actor!='ae-registration':raise ValueError('Enrollment identity is reserved')
            cert=issue(directory,originator)
            return MutualTLSTransport(directory/'ca.crt',cert/'certificate.crt',cert/'private.key')
        transport=actor_transport('CAdmin','bootstrap')
        admin=CSEClient(url,'CAdmin','4',transport=transport,evidence=evidence,actor_transport=actor_transport)
        settings=Settings(cse_url=url,notification_url='http://gateway:8000/onem2m/notify',
                          bind_host='0.0.0.0',bind_port=8000,startup_timeout=60,evidence_root=evidence.path)
        phase('WAIT_AUTHENTICATED_ACTUAL_CSE')
        cb=wait_for_cse(admin,settings);summary['real_CSE']=True
        metadata['cse_runtime']=strict_json(Path('/metadata/cse.json').read_bytes())
        checks['authenticated_actual_CSEBase']=cb['cst']==1
        store=NotificationStore(evidence.path/'notifications.sqlite3')
        nodes=fixture_nodes(default_fixture())
        service=NotificationService(store,cb['csi'],'4',nodes,evidence)
        server=notification_server('0.0.0.0',8000,service)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        phase('REGISTER_REAL_AEs_AND_CERTIFICATES')
        resources=bootstrap(admin,settings.cse_base,'fr_'+uuid4().hex[:16],settings.notification_url,
                            settings.retention_seconds,decision_policies=True)
        evidence.write('resources.json',resources)
        clients={role:admin.for_actor(data['ae_id'],role) for role,data in resources['actors'].items()}
        checks['eight_actual_AEs_have_distinct_IDs']=len(clients)==8 and len({v['ae_id'] for v in resources['actors'].values()})==8
        controller,sensor,resident=(clients[k] for k in ['controller','sensor','resident'])
        telemetry=resources['containers']['sensor/telemetry']['path']
        phase('ACTUAL_CIN_AND_SUBSCRIPTION')
        sub=controller.ensure(telemetry,23,{'rn':'secure-sub','nu':[settings.notification_url],
            'enc':{'net':[3]},'nct':1,'lbl':['fire-route']})
        refs=subscription_refs(cb['csi'],telemetry+'/secure-sub',sub)
        checks['actual_private_callback_verification']=bool(store.verified_refs()&refs);service.approve(refs)
        event=synthetic_smoke(nodes,resources['namespace']);name='secure-'+uuid4().hex
        cin=sensor.resource(sensor.create(telemetry,4,{'rn':name,'cnf':'application/json:0','con':json.dumps(event.to_dict())}),4)
        readback=controller.resource(controller.retrieve(telemetry+'/'+name),4)
        checks['certificate_sensor_CREATE_controller_GET_same_CIN']=readback['ri']==cin['ri'] and strict_json(readback['con'])==event.to_dict()
        end=time.monotonic()+15
        while not store.find(event.event_id) and time.monotonic()<end:time.sleep(.05)
        found=store.find(event.event_id)
        checks['actual_CIN_subscription_event']=len(found)==1 and found[0]['cin_ri']==cin['ri']
        phase('REAL_ACP_AND_CERTIFICATE_NEGATIVES')
        try:
            resident.retrieve(telemetry+'/'+name);checks['real_CSE_ACP_denies_resident']=False
        except CSEError as exc:checks['real_CSE_ACP_denies_resident']=exc.http_status==403 and exc.rsc==4103
        denials=[]
        for forged in ['CAdmin',resources['actors']['controller']['ae_id']]:
            response=sensor.transport('GET',url+telemetry+'/'+name,
                {'X-M2M-Origin':forged,'X-M2M-RI':'fr-'+uuid4().hex,'X-M2M-RVI':'4'},None,5)
            denials.append({'http_status':response.status,'CSE_RSC_present':any(k.lower()=='x-m2m-rsc' for k in response.headers)})
        checks['sensor_certificate_cannot_claim_admin_or_other_AE']=all(d['http_status']==403 and not d['CSE_RSC_present'] for d in denials)
        evidence.write('gateway-denials.json',denials)
        context=ssl.create_default_context(cafile=str(directory/'ca.crt'))
        no_certificate=HTTPTransport(tls_context=context)
        # Otherwise a missing request ID could make the CSE reject the request
        # and falsely appear to demonstrate a gateway authentication denial.
        headers={'X-M2M-Origin':'CAdmin','X-M2M-RI':'fr-'+uuid4().hex,'X-M2M-RVI':'4','Accept':'application/json'}
        try:
            response=no_certificate('GET',url+'/'+settings.cse_base,headers,None,5)
            checks['missing_client_certificate_rejected']=gateway_rejection(response)
        except TransportError as exc:checks['missing_client_certificate_rejected']=tls_cause(exc)
        other_ca=prepare(directory/'untrusted-CA')
        cert=issue(other_ca,'CAdmin')
        wrong_client=MutualTLSTransport(directory/'ca.crt',cert/'certificate.crt',cert/'private.key')
        try:
            response=wrong_client('GET',url+'/'+settings.cse_base,headers,None,5)
            checks['untrusted_client_CA_rejected']=gateway_rejection(response)
        except TransportError as exc:checks['untrusted_client_CA_rejected']=tls_cause(exc)
        cert=issue(directory,'CAdmin')
        wrong_server=MutualTLSTransport(other_ca/'ca.crt',cert/'certificate.crt',cert/'private.key')
        try:
            wrong_server('GET',url+'/'+settings.cse_base,headers,None,5)
            checks['untrusted_server_CA_rejected']=False
        except TransportError as exc:checks['untrusted_server_CA_rejected']=tls_cause(exc)
        try:
            transport('GET','https://wrong-certificate-host:8443/'+settings.cse_base,headers,None,5)
            checks['wrong_server_hostname_rejected']=False
        except TransportError as exc:checks['wrong_server_hostname_rejected']=tls_cause(exc)
        metadata.update(actual_cse_base=cb,security_scope='CLIENT_TO_GATEWAY_MTLS_IDENTITY_BINDING',
                        cse_runtime=strict_json(Path('/metadata/cse.json').read_bytes()))
        summary.update(state='PASS' if all(checks.values()) else 'FAIL',checks=len(checks),cin_ri=cin['ri'],
                       failed_checks=[k for k,v in checks.items() if not v],phase='COMPLETE')
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',reason=str(exc))
    except Exception as exc:
        summary.update(state='FAIL',reason=type(exc).__name__)
        for key in ['http_status','rsc']:
            value=getattr(exc,key,None)
            if type(value) is int:summary[key]=value
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=3)
        evidence.write('meta.json',metadata);evidence.write('assertions.json',checks);evidence.write('summary.json',summary)
    return summary,evidence.path


if __name__=='__main__':
    result,path=run();print(json.dumps({**result,'evidence':str(path)}))
    sys.exit(0 if result['state']=='PASS' else 1)
