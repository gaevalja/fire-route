"""Actual CSE request SUB -> discovered FireRoute provider -> actual result CIN.

This is the FireRoute project IPE, not upstream meep-ipe or TR-0086 certification.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
from threading import Event, Thread
import time
from uuid import uuid4

from backend.evidence import Evidence, source_identity
from backend.notifications import NotificationService, NotificationStore, notification_server
from backend.p0 import probe, subscription_refs
from mec.occupancy.estimator import validate_estimate
from mec.occupancy.service import fresh_batch, parse_unit
from mec.risk.evacuation import Navigation
from mec.risk.service import fresh
from mec.service_client import LocalHTTP, OCCUPANCY_ENDPOINT, OCCUPANCY_SERVICE, ServiceError, discover_risk, discover_service
from onem2m.client import CSEClient, CSEError, ProtocolError, TransportError, strict_json
from simulator.commands import utc_time
from simulator.scenario_frames import ScenarioFrame, source_manifest

NAVIGATION = Navigation()
REFERENCE_FIELDS = {'path','ri','content_sha256','event_id','incident_id','sequence_from','sequence_to','timestamp_utc','presence'}


def cin_reference(value):
    return (isinstance(value,dict) and set(value)=={'path','ri','content_sha256'}
            and all(isinstance(value[k],str) and value[k] and len(value[k])<=512 for k in ('path','ri'))
            and value['path'].startswith('/') and bool(re.fullmatch('[0-9a-f]{64}',str(value['content_sha256']))))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Message:
    event_id:str
    document:dict
    def to_dict(self):return self.document


def decode_request(data):
    if (not isinstance(data,dict) or set(data)!={'schema_version','kind','event_id','frame'}
            or type(data['schema_version']) is not int or data['schema_version']!=1
            or data['kind']!='FireRouteRiskRequest'
            or not isinstance(data['event_id'],str) or not re.fullmatch('req-[0-9a-f]{32}',data['event_id'])):
        raise ValueError('INVALID_RISK_REQUEST')
    ScenarioFrame.parse(data['frame'],source_manifest()['bundle_sha256'])
    return Message(data['event_id'],data)


def decode_occupancy_request(data):
    """References to actual access-gateway CINs; the IPE retrieves their content itself."""
    if (not isinstance(data,dict) or set(data)!={'schema_version','kind','event_id','batches'}
            or type(data['schema_version']) is not int or data['schema_version']!=1
            or data['kind']!='FireRouteOccupancyRequest'
            or not isinstance(data['event_id'],str) or not re.fullmatch('occ-[0-9a-f]{32}',data['event_id'])
            or not isinstance(data['batches'],list) or not 1<=len(data['batches'])<=64):
        raise ValueError('INVALID_OCCUPANCY_REQUEST')
    previous=None
    for ref in data['batches']:
        if (not isinstance(ref,dict) or set(ref)!=REFERENCE_FIELDS
                or any(not isinstance(ref[k],str) or not ref[k] or len(ref[k])>512 for k in ('event_id','incident_id','timestamp_utc'))
                or not cin_reference({k:ref[k] for k in ('path','ri','content_sha256')}) or not cin_reference(ref['presence'])
                or any(type(ref[k]) is not int or ref[k]<1 for k in ('sequence_from','sequence_to'))
                or ref['sequence_from']>ref['sequence_to']):
            raise ValueError('INVALID_OCCUPANCY_REFERENCE')
        if previous and (ref['incident_id']!=previous['incident_id'] or ref['sequence_from']!=previous['sequence_to']+1):
            raise ValueError('NONCONSECUTIVE_OCCUPANCY_REFERENCES')
        previous=ref
    utc_time(previous['timestamp_utc'])
    return Message(data['event_id'],data)


def provision(admin, base, namespace):
    parent='/'+base;labels=['fire-route','namespace:'+namespace,'fire-route:project-ipe-v1']
    actors={}
    for role in ('ipe','producer','reader'):
        name=namespace+'__'+role
        attrs={'rn':name,'api':'Nfire-route.project-ipe','srv':['4'],'rr':False,'lbl':labels}
        ae=admin.ensure(parent,2,attrs,creator=admin.for_actor('C','register-'+role))
        actors[role]={'ae_id':ae['aei'],'ri':ae['ri'],'path':parent+'/'+name}
    if len({a['ae_id'] for a in actors.values()})!=3:raise ProtocolError('Distinct IPE actors required')
    containers={}
    for kind,writer,reader in [('requests','producer','ipe'),('results','ipe','reader'),
                               ('occupancy-requests','producer','ipe'),('occupancy-results','ipe','reader')]:
        rules=[{'acor':[actors[writer]['ae_id']],'acop':3},
               {'acor':[actors[reader]['ae_id']],'acop':2},
               {'acor':[actors[reader]['ae_id']],'acop':1,'acod':[{'ty':3,'chty':[23]}]},
               {'acor':[admin.originator],'acop':63}]
        acp=admin.ensure(parent,1,{'rn':namespace+'__'+kind+'-policy','lbl':labels,
            'pv':{'acr':rules},'pvs':{'acr':[{'acor':[admin.originator],'acop':63}]}})
        actual=admin.ensure(actors['ipe']['path'],3,{'rn':kind,'lbl':labels,'mni':10000,'acpi':[acp['ri']]})
        containers[kind]={'path':actors['ipe']['path']+'/'+kind,'ri':actual['ri'],'policy_ri':acp['ri']}
    return {'namespace':namespace,'actors':actors,'containers':containers}


def analyse(document, platform, provider, registration):
    raw=document['frame'];frame=ScenarioFrame.parse(raw)
    identity={k:raw[k] for k in ('incident_id','sequence','timestamp_utc')}
    result={'schema_version':1,'kind':'FireRouteRiskResponse','event_id':document['event_id'],
        'source_event_id':raw['event_id'],**identity,'state':'UNKNOWN','analysis':None,
        'guidance_status':'UNKNOWN','route':None,'interworking':'FIREROUTE_PROJECT_IPE_V1',
        'model_provenance':'ASSUMED_NOT_CALIBRATED'}
    try:
        fresh(frame)
        item=discover_risk(platform,'FireRoute Risk v1',registration['service_id'])
        reply=provider.call('POST','/v1/frames',raw)
        full=reply.get('result')
        if (reply.get('state')!='ACCEPTED' or not isinstance(full,dict)
                or full.get('event_id')!=raw['event_id'] or full.get('incident_id')!=raw['incident_id']
                or full.get('route_version')!=raw['sequence'] or full.get('timestamp_utc')!=raw['timestamp_utc']):
            raise ServiceError()
        fresh(frame)  # A slow result cannot revive expired guidance.
        route=full['fixed_route']
        if route.get('status') not in {'ROUTE_AVAILABLE','NO_VERIFIED_ROUTE'}:raise ServiceError()
        expires=utc_time(raw['timestamp_utc'])+timedelta(seconds=30)
        analysis={k:full[k] for k in ('event_id','incident_id','route_version','simulation_second','timestamp_utc',
                                    'policy_sha256','fixed_route','population')}
        if 'comparison' in full:
            analysis['comparison']=full['comparison']
        result.update(state='ACCEPTED',guidance_status=route['status'],route=route,
            analysis=analysis,
            result_sha256=digest(full),service_id=item['serInstanceId'],app_id=registration['app_id'],
            valid_until_utc=expires.isoformat().replace('+00:00','Z'))
    except (ServiceError,ValueError,KeyError,TypeError):
        result['reason']='SERVICE_UNAVAILABLE_INVALID_OR_EXPIRED'
    return result


def retrieve_verified(client, ref):
    cin=client.resource(client.retrieve(ref['path']),4)
    content=strict_json(cin['con']) if isinstance(cin['con'],str) else cin['con']
    if cin['ri']!=ref['ri'] or digest(content)!=ref['content_sha256']:
        raise ServiceError()
    return content


def resolve_batches(document, client):
    """Retrieve each referenced access and presence-scan CIN with the IPE's own ACP grant and verify them."""
    units=[]
    for ref in document['batches']:
        unit=parse_unit({'access':retrieve_verified(client,ref),'presence':retrieve_verified(client,ref['presence'])},NAVIGATION)
        if any(unit['access'][k]!=ref[k] for k in ('event_id','incident_id','sequence_from','sequence_to','timestamp_utc')):
            raise ServiceError()
        units.append(unit)
    return units


def analyse_occupancy(document, client, platform, provider, cache):
    last=document['batches'][-1]
    result={'schema_version':1,'kind':'FireRouteOccupancyResponse','event_id':document['event_id'],
        'source_event_id':last['event_id'],'incident_id':last['incident_id'],'sequence_to':last['sequence_to'],
        'timestamp_utc':last['timestamp_utc'],'state':'UNKNOWN','estimate':None,
        'interworking':'FIREROUTE_PROJECT_IPE_V1','provenance':'ASSUMED_NOT_CALIBRATED'}
    try:
        batches=resolve_batches(document,client)
        fresh_batch(batches[-1]['access'])
        registration=cache.get('registration')
        if registration is None:
            registration=provider.call('GET','/health').get('registration')
            if not isinstance(registration,dict) or not registration.get('service_id') or not registration.get('app_id'):
                raise ServiceError()
            cache['registration']=registration
        item=discover_service(platform,OCCUPANCY_SERVICE,registration['service_id'],OCCUPANCY_ENDPOINT)
        reply=provider.call('POST','/v1/batches',{'batches':batches})
        estimate=reply.get('estimate')
        if (reply.get('state')!='ACCEPTED' or not isinstance(estimate,dict)
                or estimate.get('incident_id')!=last['incident_id']
                or estimate.get('applied_through_sequence')!=last['sequence_to']
                or estimate.get('source_event_id')!=last['event_id']):
            raise ServiceError()
        validate_estimate(estimate,NAVIGATION)
        fresh_batch(batches[-1]['access'])  # A slow estimate cannot revive expired input.
        expires=utc_time(last['timestamp_utc'])+timedelta(seconds=30)
        result.update(state='ACCEPTED',estimate=estimate,estimate_sha256=digest(estimate),
            service_id=item['serInstanceId'],app_id=registration['app_id'],
            valid_until_utc=expires.isoformat().replace('+00:00','Z'))
    except TransportError:
        raise  # CSE unreachable: leave the request unprocessed for the next loop.
    except (ServiceError,ValueError,KeyError,TypeError,CSEError):
        result['reason']='SERVICE_UNAVAILABLE_INVALID_OR_EXPIRED'
    return result


class Outbox:
    def __init__(self,path):
        self.path=path
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS output (id TEXT PRIMARY KEY, request_hash TEXT, payload TEXT, state TEXT, cin_ri TEXT)')
            self.completed={row[0] for row in db.execute("SELECT id FROM output WHERE state='DONE'")}

    def process(self, document, calculate, client, parent):
        identity=document['event_id'];name='result-'+identity
        fingerprint=digest(document)
        with sqlite3.connect(self.path) as db:
            row=db.execute('SELECT request_hash,payload,state,cin_ri FROM output WHERE id=?',(identity,)).fetchone()
            if row and row[0]!=fingerprint:raise ProtocolError('Conflicting IPE request identity')
            if row and row[2]=='DONE':return strict_json(row[1])
            if row is None:
                payload=calculate(document)
                db.execute('INSERT INTO output VALUES (?,?,?,?,?)',
                           (identity,fingerprint,json.dumps(payload,sort_keys=True),'PREPARED',None));db.commit()
                row=(fingerprint,json.dumps(payload,sort_keys=True),'PREPARED',None)
            payload=strict_json(row[1]);path=parent+'/'+name
            if (row[2]=='PREPARED' and payload.get('state')=='ACCEPTED'
                    and datetime.now(timezone.utc)>=utc_time(payload['valid_until_utc'])):
                if payload.get('kind')=='FireRouteOccupancyResponse':
                    payload.update(state='UNKNOWN',estimate=None,reason='RESULT_EXPIRED_BEFORE_CSE_PUBLISH')
                else:
                    payload.update(state='UNKNOWN',guidance_status='UNKNOWN',analysis=None,route=None,
                                   reason='RESULT_EXPIRED_BEFORE_CSE_PUBLISH')
                db.execute('UPDATE output SET payload=? WHERE id=?',(json.dumps(payload,sort_keys=True),identity));db.commit()
            try:
                actual=client.resource(client.retrieve(path),4)
            except CSEError as exc:
                if isinstance(exc,ProtocolError) or exc.http_status!=404 or exc.rsc!=4004:raise
                if row[2]=='ATTEMPTED':
                    # An uncertain CREATE may still commit. Only GET reconciliation
                    # is allowed for this identity; no hidden replay on next loop.
                    return None
                db.execute("UPDATE output SET state='ATTEMPTED' WHERE id=?",(identity,));db.commit()
                actual=client.resource(client.create(parent,4,{'rn':name,'cnf':'application/json:0',
                    'con':json.dumps(payload,separators=(',',':'),allow_nan=False)}),4)
                actual=client.resource(client.retrieve(path),4)
            if strict_json(actual['con'])!=payload:raise ProtocolError('IPE output read-back differs')
            db.execute("UPDATE output SET state='DONE',cin_ri=? WHERE id=?",(actual['ri'],identity));db.commit()
            self.completed.add(identity)
            return payload


def main():
    state=Path(os.environ.get('FR_IPE_STATE','/state'));state.mkdir(parents=True,exist_ok=True)
    ev=Evidence(Path(os.environ.get('EVIDENCE_ROOT','evidence')),
        secret_values=(os.environ.get('FR_RISK_ACCESS_KEY',''),'CAdmin'))
    stop=Event();server=thread=None
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    try:
        connection=state/'connection.json'
        previous=strict_json(connection.read_bytes()) if connection.exists() else None
        namespace=previous['namespace'] if previous else 'fr_ipe_'+uuid4().hex[:16]
        admin=CSEClient('http://mec-cse:8080','CAdmin','4',evidence=ev)
        cb=probe(admin,'fire-route-dev')
        inbox=NotificationStore(state/'inbox.sqlite3')
        service=NotificationService(inbox,cb['csi'],'4',frozenset(),ev,decoder=decode_request)
        server=notification_server('0.0.0.0',8000,service)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        resources=provision(admin,'fire-route-dev',namespace)
        actor=admin.for_actor(resources['actors']['ipe']['ae_id'],'project-ipe')
        req=resources['containers']['requests']['path']
        sub=actor.ensure(req,23,{'rn':'risk-sub','nu':['http://mec-ipe:8000/onem2m/notify'],'enc':{'net':[3]},'nct':1})
        refs=subscription_refs(cb['csi'],req+'/risk-sub',sub)
        if not refs & inbox.verified_refs():raise ProtocolError('Actual IPE SUB verification missing')
        service.approve(refs)
        occ=resources['containers']['occupancy-requests']['path']
        occ_sub=actor.ensure(occ,23,{'rn':'occupancy-sub','nu':['http://mec-ipe:8000/onem2m/notify'],'enc':{'net':[3]},'nct':1})
        occ_refs=subscription_refs(cb['csi'],occ+'/occupancy-sub',occ_sub)
        if not occ_refs & inbox.verified_refs():raise ProtocolError('Actual occupancy IPE SUB verification missing')
        service.approve(occ_refs,decoder=decode_occupancy_request)
        occupancy=LocalHTTP('http://mec-occupancy:8082',aliases=('mec-occupancy',),evidence=ev,
                            access_key=os.environ.get('FR_RISK_ACCESS_KEY'))
        occupancy_cache={}
        provider=LocalHTTP('http://mec-risk:8081',aliases=('mec-risk',),evidence=ev,
                           access_key=os.environ.get('FR_RISK_ACCESS_KEY'))
        platform=LocalHTTP('http://mec-platform',aliases=('mec-platform',),evidence=ev)
        registration=provider.call('GET','/health')['registration']
        discover_risk(platform,'FireRoute Risk v1',registration['service_id'])
        public={**resources,'registration':{k:registration[k] for k in ('app_id','service_id','name')},
                'evidence':str(ev.path),'interworking':'FIREROUTE_PROJECT_IPE_V1'}
        temp=connection.with_suffix('.tmp');temp.write_text(json.dumps(public));temp.replace(connection)
        ev.write('resources.json',resources);ev.write('meta.json',source_identity(Path.cwd()))
        outbox=Outbox(state/'outbox.sqlite3')
        print(json.dumps({'state':'PROJECT_IPE_READY','namespace':namespace,'evidence':str(ev.path),
            'Hosted':'NOT_CONTACTED','MEC_IPE':'FIREROUTE_PROJECT_IPE_V1'}),flush=True)
        while not stop.is_set():
            try:
                for row in inbox.records():
                    if row['event']['event_id'] in outbox.completed:continue
                    if row['event'].get('kind')=='FireRouteOccupancyRequest':
                        # Isolated from risk: an occupancy failure yields UNKNOWN estimates only.
                        outbox.process(row['event'],lambda doc:analyse_occupancy(doc,actor,platform,occupancy,occupancy_cache),
                                       actor,resources['containers']['occupancy-results']['path'])
                        continue
                    outbox.process(row['event'],lambda doc:analyse(doc,platform,provider,registration),actor,
                                   resources['containers']['results']['path'])
                heartbeat=state/'heartbeat.tmp';heartbeat.write_text(str(time.time()));heartbeat.replace(state/'heartbeat')
            except CSEError as exc:
                ev.append('outages.jsonl',{'state':'CSE_UNAVAILABLE_OR_AMBIGUOUS','reason':type(exc).__name__})
            stop.wait(.05)
        return 0
    except Exception as exc:
        ev.write('summary.json',{'state':'FAIL','reason':type(exc).__name__,'Hosted':'NOT_CONTACTED'})
        print(json.dumps({'state':'FAIL','reason':type(exc).__name__,'evidence':str(ev.path)}),flush=True)
        return 1
    finally:
        if server:
            if thread and thread.is_alive():server.shutdown()
            server.server_close()
        if thread:thread.join(timeout=3)


if __name__=='__main__':raise SystemExit(main())
