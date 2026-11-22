"""Actual local controller/discovered risk/project-IPE/CSE/Group acceptance gate."""
import json
import os
from pathlib import Path
from uuid import uuid4

from backend.config import Settings
from backend.hazard_checks import HazardCoverage, verify_delivery
from backend.scenario_core import ScenarioSession
from mec.interworking.worker import digest
from mec.interworking.client import Requester, VerifiedRemoteSnapshot, verified_result
from mec.service_client import LocalHTTP, discover_risk
from onem2m.client import CSEError, ProtocolError, strict_json
from simulator.commands import utc_time
from simulator.events import utc_now
from simulator.scenario_frames import read_trace, trace_digest



def run():
    settings=Settings(cse_url='http://mec-cse:8080',notification_url='http://mec-services-check:8000/onem2m/notify',
        bind_host='0.0.0.0',evidence_root=Path(os.getenv('EVIDENCE_ROOT','evidence')))
    session=ScenarioSession(settings);ev=session.evidence;checks={};requester=None
    summary={'test':'LOCAL_MEC_RISK_IPE_E2E','state':'NOT_RUN','Hosted':'NOT_CONTACTED',
        'MEC':'NOT_VERIFIED','MEC_IPE':'FIREROUTE_PROJECT_IPE_V1','official_meep_ipe':'NOT_EXECUTED',
        'placement':'EXTERNAL_COMPOSE_APP_NOT_VM_OR_OPTION_C','browser':'NOT_RUN',
        'input':'SYNTHETIC_SOURCE_REPLAY','model_provenance':'ASSUMED_NOT_CALIBRATED'}
    phase='INITIALISE'
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    try:
        connection=strict_json(Path('/ipe-state/connection.json').read_bytes())
        platform=LocalHTTP('http://mec-platform',aliases=('mec-platform',),evidence=ev)
        controller=LocalHTTP('http://mec-controller',aliases=('mec-controller',),evidence=ev)
        registration=connection['registration']
        app=controller.call('GET','/sandbox-ctrl/v1/applications/'+registration['app_id'])
        check('native_controller_assigned_app_readback',app.get('id')==registration['app_id'] and app.get('name')=='FireRoute Risk v1')
        item=discover_risk(platform,'FireRoute Risk v1',registration['service_id'])
        check('actual_nonempty_service_catalog_and_endpoint',item['state']=='ACTIVE')
        session.start()
        meta=strict_json((ev.path/'meta.json').read_bytes())
        meta.update(test=summary['test'],real_MEC=True,deployment_option=summary['placement'],
                    interworking=summary['MEC_IPE'],ipe_evidence=connection['evidence'])
        ev.write('meta.json',meta);ev.write('mec-connection.json',connection)
        requester=Requester(session.admin,connection,ev,'http://mec-services-check:8010/onem2m/notify',8010)
        requester.start()
        producer,reader=requester.producer,requester.reader
        request_parent,result_parent=requester.requests,requester.results
        check('actual_result_SUB_verification',True)
        request_frame=requester.submit
        coverage=HazardCoverage(session.model.navigation);count=0
        trace=Path(os.environ['SCENARIO_TRACE'])
        ev.write('replay-source.json',{'trace_sha256':trace_digest(trace),'source_bundle_sha256':session.hash})
        phase='SOURCE_CSE_IPE_RISK_CSE_GROUP'
        for raw in read_trace(trace,session.hash):
            session.accept_raw(raw);local=session.model.snapshot()
            reply=request_frame(session.model.last)
            check('all_remote_results_equal_original_model',reply.get('state')=='ACCEPTED'
                and reply.get('result_sha256')==digest(local)
                and reply['analysis']['fixed_route']==local['fixed_route']
                and reply['analysis']['population']==local['population']
                and reply.get('service_id')==registration['service_id'])
            check('accepted_result_still_fresh',utc_time(utc_now())<utc_time(reply['valid_until_utc']))
            remote=verified_result(reply,session.model.last,local)
            if count==0 or raw['simulation_second']==180:
                policy=remote['comparison']
                check('ppo_and_dijkstra_correlated_to_actual_result_'+str(count),
                      policy==local['comparison'] and policy['model_id']=='FIRE_EVAC_0015'
                      and set(policy['policies'])=={'dijkstra','ppo'})
            stages=coverage.observe(session.model.last,remote)
            if stages:
                model=session.model
                try:
                    session.model=VerifiedRemoteSnapshot(model,remote)
                    result,delivery=session.publish();verify_delivery(result,delivery)
                finally:session.model=model
                private=session.clients['responder'];container=session.resources['containers']['controller/diagnostics']
                cin=private.resource(private.retrieve(container['path']+'/la'),4)
                recorded=strict_json(cin['con'])
                check('comparison_published_and_read_by_responder',
                      recorded['comparison']==remote['comparison'] and recorded['event_id']==raw['event_id'])
                for stage in stages:ev.append('mec-hazard-stages.jsonl',stage)
            if count==0:
                duplicate=request_frame(session.model.last)
                check('duplicate_frame_no_extra_movement',duplicate.get('result_sha256')==reply['result_sha256'])
            count+=1
            if raw['simulation_second']%60==0:
                print(json.dumps({'test':summary['test'],'phase':phase,'simulation_second':raw['simulation_second']}),flush=True)
            if coverage.complete:break
        check('four_natural_hazard_stages',coverage.complete)
        check('actual_three_device_ACKs_at_each_stage',len(session.delivery.results)>=4 and all(x['ack_count']==3 for x in session.delivery.results))
        phase='EXPIRY_AND_ACP'
        expired={**session.model.last,'timestamp_utc':'2020-01-01T00:00:00Z'}
        rejected=request_frame(expired)
        check('expired_frame_yields_UNKNOWN_without_previous_route',rejected['state']=='UNKNOWN' and rejected['route'] is None and rejected['analysis'] is None)
        for actor,path in [(reader,request_parent),(producer,result_parent)]:
            try:actor.create(path,4,{'rn':'forbidden-'+uuid4().hex,'cnf':'application/json:0','con':'{}'})
            except CSEError as exc:
                check('actual_forbidden_write_'+actor.actor,not isinstance(exc,ProtocolError) and exc.http_status==403 and exc.rsc==4103)
            else:raise AssertionError('Forbidden cross-role write allowed')
        for role in ('resident','responder'):
            # The existing scenario's resident/responder ACP remains in force.
            if role=='resident':
                try:session.clients[role].retrieve(session.resources['containers']['controller/diagnostics']['path']+'/la')
                except CSEError as exc:check('resident_private_detail_denied',exc.http_status==403 and exc.rsc==4103)
                else:raise AssertionError('Resident read private detail')
        ev.write('hazard-coverage.json',{'stages':coverage.stages})
        summary.update(state='PASS',MEC='NATIVE_REGISTRATION_DISCOVERY_AND_RISK_CONSUMPTION',CSE='PASS',Group='PASS',
            source_frames=count,stage_seconds={k:v['simulation_second'] for k,v in coverage.stages.items()},
            group_operations=len(session.delivery.results),app_id=registration['app_id'],service_id=registration['service_id'])
    except Exception as exc:
        summary.update(state='FAIL',phase=phase,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
        for field in ('http_status','rsc','status'):
            value=getattr(exc,field,None)
            if type(value) is int:summary[field]=value
    finally:
        if requester:
            try:
                if not requester.close():summary.update(state='FAIL',reason='Observer cleanup unconfirmed')
            except Exception as exc:summary.update(state='FAIL',reason='Observer cleanup '+type(exc).__name__)
        try:
            if not session.close():summary.update(state='FAIL',reason='Device shutdown incomplete')
        except Exception as exc:summary.update(state='FAIL',reason='Shutdown '+type(exc).__name__)
        summary.update(checks=len(checks),failed_checks=[k for k,v in checks.items() if not v])
        ev.write('assertions.json',checks);ev.write('summary.json',summary)
    print(json.dumps({**summary,'evidence':str(ev.path)}),flush=True)
    return 0 if summary['state']=='PASS' else 1


if __name__=='__main__':raise SystemExit(run())
