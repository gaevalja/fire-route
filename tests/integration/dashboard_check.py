"""Actual HTTP/role/CSE dashboard gate. No mock switch or fabricated PASS."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib import request,error
from urllib.parse import urlsplit
from uuid import uuid4

from backend.evidence import Evidence,source_identity
from onem2m.client import CSEClient,CSEError,ProtocolError,strict_json


def run():
    evidence=Evidence(Path(os.getenv('EVIDENCE_ROOT','evidence')))
    summary={'test':'P1_DASHBOARD','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
             'browser_rendering':'NOT_RUN','MEC':'unavailable','latency_samples':0}
    base=os.getenv('DASHBOARD_URL','http://127.0.0.1:3000').rstrip('/')
    origin=os.getenv('APP_PUBLIC_ORIGIN','http://127.0.0.1:3000').rstrip('/')
    sessions={};checks={}
    evidence.write('meta.json',{'test':'P1_DASHBOARD','started_at_utc':datetime.now(timezone.utc).isoformat(),
        'python':sys.version.split()[0],'input':'SYNTHETIC','browser_rendering':'NOT_RUN',
        **source_identity(Path(__file__).resolve().parents[2])})
    def phase(name):
        print(json.dumps({'test':'P1_DASHBOARD','phase':name}),flush=True)
    def call(path,*,role=None,method='GET',body=None,expect=200,other_origin=None):
        headers={'Host':urlsplit(origin).netloc,'Origin':other_origin or origin,'Content-Type':'application/json'}
        if role in sessions:headers['Cookie']=sessions[role]
        req=request.Request(base+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:response=request.urlopen(req,timeout=15)
        except error.HTTPError as exc:response=exc
        with response:
            raw=response.read(1024*1024)
            value=strict_json(raw) if response.headers.get('Content-Type','').startswith('application/json') else raw.decode()
            # Never record cookies, login request bodies, codes or tokens.
            evidence.append('http.jsonl',{'method':method,'path':path,'role':role,'http_status':response.status})
            if response.status!=expect:raise AssertionError('Unexpected HTTP status at '+path)
            cookie=response.headers.get('Set-Cookie')
            if cookie and role:sessions[role]=cookie.split(';',1)[0]
            return value
    def check(name,condition):
        checks[name]=bool(condition)
        if not condition:raise AssertionError(name)
    def ready(*,different=None,timeout=90):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            state=call('/api/v1/status',role='responder')
            if state['state']=='READY' and not state['busy'] and state['incident_id'] and (different is None or state['incident_id']!=different):return state
            time.sleep(.2)
        raise AssertionError('App never reached a verified ready state')
    def views(stage):
        deadline=time.monotonic()+90
        while True:
            state=ready();incident=state['incident_id']
            resident=call(f'/api/v1/incidents/{incident}/resident',role='resident')
            responder=call(f'/api/v1/incidents/{incident}/responder',role='responder')
            if resident['guidance_status']!='PENDING' and responder['guidance_status']!='PENDING':break
            if time.monotonic()>deadline:raise AssertionError('Role view correlation stayed pending')
            time.sleep(.2)
        check('same_incident_and_version',resident['incident_id']==responder['incident_id'] and resident['route_version']==responder['route_version'])
        check('resident_no_private_fields',not {'occupants','sensors','devices','hazards'}&resident.keys())
        evidence.write('last-resident-view.json',resident);evidence.write('last-responder-view.json',responder)
        evidence.write(stage+'-resident-view.json',resident);evidence.write(stage+'-responder-view.json',responder)
        return resident,responder
    def action(value):
        deadline=time.monotonic()+90
        while True:
            ready()
            try:result=call('/api/v1/scenario',role='responder',method='POST',body={'action':value},expect=202);break
            except AssertionError:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        ready();return result
    try:
        if sys.version_info<(3,11):
            summary.update(state='BLOCKED',blocked=1,reason='Use the Python 3.12 dashboard-check Compose profile')
            return summary,evidence.path
        codes=strict_json(Path(os.getenv('ACCESS_CODES_FILE','.runtime/access-codes.json')).read_bytes())
        evidence.secret_values=tuple(codes.values())
        phase('ROLE_ACCESS')
        call('/api/v1/status',expect=401)
        for role in ['resident','responder']:
            call('/api/v1/session',role=role,method='POST',body={'role':role,'access_code':codes[role]})
            check(role+'_session_bound',call('/api/v1/session',role=role)['role']==role)
        check('static_assets_served','FireRoute' in call('/') and 'guidance' in call('/app.js'))
        state=ready()
        call(f"/api/v1/incidents/{state['incident_id']}/responder",role='resident',expect=403)
        call('/api/v1/scenario',role='resident',method='POST',body={'action':'fire_a'},expect=403)
        call('/api/v1/scenario',role='responder',method='POST',body={'action':'fire_a'},other_origin='https://foreign.invalid',expect=403)
        call('/api/v1/session',method='POST',body={'role':'responder','access_code':codes['resident']},expect=401)
        action('pause')
        phase('BASELINE')
        a,b=views('baseline');check('baseline_actual_EXIT_A',a['route']['target_exit']=='EXIT_A' and a['delivery']['ack_count']==3)
        check('synthetic_occupant_known_and_unknown',any(x['remaining_count']==2 for x in b['occupants']) and any(x['remaining_count'] is None for x in b['occupants']))
        phase('FIRE_A_REROUTE')
        action('fire_a');a,b=views('fire-a');check('actual_reroute_EXIT_B',a['route']['target_exit']=='EXIT_B' and 'F2_A' not in a['route']['path'])
        phase('NO_ROUTE')
        action('fire_b');a,b=views('no-route');check('actual_no_route',a['guidance_status']=='NO_VERIFIED_ROUTE' and a['route'] is None and a['delivery']['ack_count']==3)
        phase('STOP_DISPLAY_C')
        action('stop_display_c');a,b=views('incomplete');check('actual_missing_ACK_visible',a['delivery']['state']=='INCOMPLETE' and a['delivery']['ack_count']==2 and any(d['device']=='display-c' and d['status']=='MISSING' for d in b['devices']))
        # Use actual registered read-only role identities from this private run's metadata.
        active=ready()['incident_id']
        matches=[]
        for meta_path in Path(os.getenv('EVIDENCE_ROOT','evidence')).glob('*/meta.json'):
            meta=strict_json(meta_path.read_bytes())
            if meta.get('test')=='P1_APP' and meta.get('incident_id')==active:matches.append(meta_path.parent)
        check('actual_app_evidence_found',len(matches)==1)
        evidence.write('app-runs.json',{'initial':matches[0].name,'initial_incident_id':active})
        resources=strict_json((matches[0]/'resources.json').read_bytes())
        resident_cse=CSEClient(os.getenv('CSE_BASE_URL','http://cse:8080'),resources['actors']['resident']['ae_id'],'4',evidence=evidence,actor='resident-CSE-check')
        parent=resources['containers']['occupancy/observations']['path']
        try:resident_cse.retrieve(parent+'/la')
        except CSEError as exc:check('actual_resident_CSE_occupants_denied',not isinstance(exc,ProtocolError) and exc.rsc==4103 and exc.http_status==403)
        else:raise AssertionError('Resident CSE occupant read was allowed')
        responder_cse=resident_cse.for_actor(resources['actors']['responder']['ae_id'],'responder-CSE-check')
        actual=responder_cse.resource(responder_cse.retrieve(parent+'/la'),4)
        snapshot=strict_json(actual['con']) if isinstance(actual['con'],str) else actual['con']
        check('actual_responder_CSE_occupants_match_API',[x['remaining_count'] for x in snapshot['observations']]==[x['remaining_count'] for x in b['occupants']])
        phase('OBSERVATION_EXPIRY_WAIT_31_SECONDS')
        time.sleep(31)
        a,b=views('stale');check('expired_observation_has_no_direction',a['guidance_status']=='STALE' and a['route'] is None)
        check('expired_occupants_unknown',all(x['status']=='UNKNOWN' and x['remaining_count'] is None for x in b['occupants']))
        phase('RESET_NEW_INCIDENT')
        action('reset');ready(different=active);a,b=views('reset');check('explicit_reset_new_incident',a['incident_id']!=active and a['route']['target_exit']=='EXIT_A')
        call('/api/v1/session',role='resident',method='DELETE')
        call('/api/v1/status',role='resident',expect=401)
        check('logout_revokes_session',True)
        summary.update(state='PASS',**{'pass':1},checks=len(checks),role_API='PASS',actual_CSE='PASS',occupants='SYNTHETIC',Group='PASS',stale='PASS')
        evidence.write('assertions.json',checks)
    except Exception as exc:
        summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:evidence.write('summary.json',summary)
    return summary,evidence.path


def main():
    summary,path=run();output=json.dumps({'evidence':str(path),**summary},sort_keys=True)
    (path/'tests.txt').write_text('command: '+json.dumps(sys.orig_argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
