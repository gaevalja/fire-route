"""Actual authenticated HTTP/CSE smoke for the selected ten-floor dashboard."""
import json
import os
from pathlib import Path
import sys
import time
from urllib import request,error
from urllib.parse import urlsplit

from backend.evidence import Evidence,source_identity
from onem2m.client import strict_json


class UnexpectedHTTPStatus(AssertionError):
    def __init__(self,status,path):
        super().__init__('Unexpected HTTP status '+str(status)+' at '+path)
        self.status=status


def fresh_scenario(call,ready):
    """Start a new paused incident even when the target app was already in use."""
    before=ready()
    deadline=time.monotonic()+120
    while True:
        try:
            call('/api/v1/scenario','responder','POST',{'action':'reset'},expect=202)
            break
        except UnexpectedHTTPStatus as exc:
            # 409 means the action was rejected before enqueueing. Never replay an
            # accepted POST, transport error or another HTTP failure.
            if exc.status!=409 or time.monotonic()>=deadline:raise
            time.sleep(.2)
    after=ready(different=before['incident_id'])
    if after['incident_id']==before['incident_id'] or after.get('paused') is not True:
        raise AssertionError('Reset did not create a new paused incident')
    return before,after


def run():
    out=Evidence(Path(os.getenv('EVIDENCE_ROOT','evidence')))
    summary={'test':'P1_SELECTED_DASHBOARD','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
        'browser_rendering':'NOT_RUN','MEC':'unavailable','model_provenance':'ASSUMED_NOT_CALIBRATED'}
    cookies={};checks={}
    base=os.getenv('DASHBOARD_URL','http://127.0.0.1:3001')
    origin=os.getenv('APP_PUBLIC_ORIGIN','http://127.0.0.1:3001')
    def call(path,role=None,method='GET',body=None,expect=200):
        headers={'Host':urlsplit(origin).netloc,'Origin':origin,'Content-Type':'application/json'}
        if role in cookies:headers['Cookie']=cookies[role]
        req=request.Request(base+path,method=method,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:response=request.urlopen(req,timeout=15)
        except error.HTTPError as exc:response=exc
        with response:
            data=response.read(1024*1024)
            value=strict_json(data) if response.headers.get('Content-Type','').startswith('application/json') else data.decode()
            out.append('http.jsonl',{'method':method,'path':path,'role':role,'http_status':response.status})
            if response.status!=expect:raise UnexpectedHTTPStatus(response.status,path)
            if role and response.headers.get('Set-Cookie'):cookies[role]=response.headers['Set-Cookie'].split(';',1)[0]
            return value
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    def ready(*,different=None):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            value=call('/api/v1/status','responder')
            if value['state']=='DEGRADED':raise AssertionError('Selected app became degraded')
            if (value['state']=='READY' and not value['busy'] and value['incident_id']
                    and value['incident_id']!=different):return value
            time.sleep(.2)
        raise AssertionError('Selected app readiness deadline exceeded')
    def views(stage):
        state=ready();incident=state['incident_id']
        a=call(f'/api/v1/incidents/{incident}/resident','resident')
        b=call(f'/api/v1/incidents/{incident}/responder','responder')
        check(stage+'_correlated',a['incident_id']==b['incident_id'] and a['route_version']==b['route_version'])
        check(stage+'_resident_private_fields_absent',not {'population','residents','occupants','hazards'}&a.keys())
        out.write(stage+'-resident-view.json',a);out.write(stage+'-responder-view.json',b)
        return a,b
    try:
        out.write('meta.json',{'test':'P1_SELECTED_DASHBOARD',**source_identity(Path(__file__).resolve().parents[2])})
        if sys.version_info<(3,11):
            summary.update(state='BLOCKED',blocked=1,reason='Use the scenario-check Compose profile')
            return summary,out.path
        codes=strict_json(Path(os.getenv('ACCESS_CODES_FILE','.runtime/access-codes.json')).read_bytes())
        out.secret_values=tuple(codes.values())
        call('/api/v1/status',expect=401)
        for role in ['resident','responder']:
            call('/api/v1/session',role,'POST',{'role':role,'access_code':codes[role]})
            check(role+'_session',call('/api/v1/session',role)['role']==role)
        check('selected_static_assets','FireRoute' in call('/') and 'selectedResident' in call('/app.js'))
        print(json.dumps({'test':'P1_SELECTED_DASHBOARD','phase':'RESET_NEW_INCIDENT'}),flush=True)
        before,state=fresh_scenario(call,ready)
        out.write('before-reset-status.json',before);out.write('initial-status.json',state)
        check('fresh_paused_incident',state['incident_id']!=before['incident_id'] and state['paused'] is True)
        call(f"/api/v1/incidents/{state['incident_id']}/responder",'resident',expect=403)
        call(f"/api/v1/incidents/{state['incident_id']}/snapshot",'resident',expect=403)
        call('/api/v1/scenario','resident','POST',{'action':'step'},expect=403)
        call('/api/v1/scenario','responder','POST',{'action':'fire_a'},expect=400)
        a,b=views('initial')
        check('initial_both_modes_available',a['simulation_second']==0 and (a.get('route') or {}).get('source_node')=='F7-R3'
            and b['population']['total']==170 and len(b['residents'])==170 and a['delivery']['ack_count']==3)
        print(json.dumps({'test':'P1_SELECTED_DASHBOARD','phase':'ADVANCE_30_SECONDS'}),flush=True)
        call('/api/v1/scenario','responder','POST',{'action':'advance_30'},expect=202)
        ready();a,b=views('moving')
        check('moving_positions_progressed',a['simulation_second']==30 and any(p['distance_m']>0 for p in b['residents']))
        check('fixed_origin_stays_fixed',a['route']['source_node']=='F7-R3')
        pop=b['population'];check('population_conserved',pop['total']==pop['remaining']+pop['evacuated'])
        check('actual_group_ACKs',a['delivery']['ack_count']==3 and a['delivery']['state']=='ALL_ACKED')
        print(json.dumps({'test':'P1_SELECTED_DASHBOARD','phase':'EXPIRY_WAIT_31_SECONDS'}),flush=True)
        time.sleep(31);a,b=views('stale')
        check('stale_clears_direction_and_positions',a['guidance_status']=='STALE' and a['route'] is None and not {'population','residents','occupants'}&b.keys())
        snapshot=call(f"/api/v1/incidents/{state['incident_id']}/snapshot",'responder')
        out.write('paused-historical-snapshot.json',snapshot)
        check('paused_snapshot_explicitly_historical',snapshot['snapshot_kind']=='HISTORICAL' and snapshot['is_live'] is False
            and snapshot['route'] is None and snapshot['simulation_second']==30)
        check('paused_snapshot_people_still_selectable',len(snapshot['residents'])==170 and snapshot['population']['total']==170)
        summary.update(state='PASS',**{'pass':1},checks=len(checks),role_API='PASS',fixed_mode='PASS',moving_mode='PASS',Group='PASS')
        out.write('assertions.json',checks)
    except Exception as exc:
        summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        out.write('assertions.json',checks)
        out.write('summary.json',summary)
    return summary,out.path


def main():
    summary,path=run();output=json.dumps({'evidence':str(path),**summary},sort_keys=True)
    (path/'tests.txt').write_text('command: '+json.dumps(sys.orig_argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
