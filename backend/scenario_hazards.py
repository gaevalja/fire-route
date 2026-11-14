"""Natural ten-floor hazards through actual CSE/SUB/Group/independent ACKs."""
import json
import os
from pathlib import Path
import sys

from backend.config import Settings
from backend.hazard_checks import HazardCoverage,STAGES,verify_delivery
from backend.p0 import IntegrationBlocked
from backend.scenario_core import ScenarioSession
from onem2m.client import CSEError,ProtocolError,strict_json
from simulator.scenario_frames import read_trace,trace_digest


def run(settings,trace):
    session=ScenarioSession(settings)
    summary={'test':'P1_SELECTED_HAZARDS','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,
        'actual_CSE':'NOT_RUN','MEC':'unavailable','UI':'NOT_RUN','latency_samples':0,
        'model_provenance':'ASSUMED_NOT_CALIBRATED'}
    checks={};coverage=HazardCoverage(session.model.navigation);fault_pending=False
    try:
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 scenario-hazards Compose profile')
        session.start();summary['actual_CSE']='CONNECTED'
        metadata=strict_json((session.evidence.path/'meta.json').read_bytes())
        metadata.update(test=summary['test'],verification_scope='NATURAL_SOURCE_HAZARDS_CORE_NO_UI')
        session.evidence.write('meta.json',metadata)
        session.evidence.write('replay-source.json',{'kind':'SYNTHETIC_SOURCE_REPLAY',
            'trace_sha256':trace_digest(trace),'source_bundle_sha256':session.hash})
        for raw in read_trace(trace,session.hash):
            session.accept_raw(raw)
            if raw['simulation_second']%60==0:
                print(json.dumps({'test':summary['test'],'phase':'ACTUAL_FRAME_REPLAY',
                    'simulation_second':raw['simulation_second']}),flush=True)
            current=session.model.snapshot()
            stages=coverage.observe(session.model.last,current)
            if stages or fault_pending:
                result,delivery=session.publish()
                verify_delivery(result,delivery,missing={'display-c'} if fault_pending else ())
                for stage in stages:
                    session.evidence.append('hazard-stages.jsonl',{**stage,
                        'command_id':delivery['command']['command_id'],'ack_count':delivery['ack_count']})
                    checks[stage['stage']+'_actual_CSE_Group_ACKs']=True
                    print(json.dumps({'test':summary['test'],'phase':stage['stage'].upper(),
                        'simulation_second':raw['simulation_second']}),flush=True)
                if fault_pending:
                    checks['stopped_device_incomplete_not_success']=True
                    break
            if coverage.complete and not fault_pending:
                # All three signs first receive the no-route command. A later
                # command still writes all Group members after one consumer stops.
                if current['fixed_route']['status']!='NO_VERIFIED_ROUTE':continue
                session.delivery.stop_device('display-c');fault_pending=True
        missing=STAGES-set(coverage.stages)
        if missing:raise AssertionError('Source trace missing hazard stages: '+', '.join(sorted(missing)))
        if not checks.get('stopped_device_incomplete_not_success'):
            raise AssertionError('Need one further source frame after all hazard stages')
        for key in ['controller/diagnostics','occupancy/observations']:
            path=session.resources['containers'][key]['path']+'/la'
            try:session.clients['resident'].retrieve(path)
            except CSEError as exc:
                if isinstance(exc,ProtocolError) or exc.http_status!=403 or exc.rsc!=4103:raise
            else:raise AssertionError('Resident read private hazard/population records')
            session.clients['responder'].resource(session.clients['responder'].retrieve(path),4)
        checks['actual_private_ACP_denials']=True
        checks['every_source_frame_has_actual_CIN_and_notification']=session.frames==session.model.last['sequence']
        if not all(checks.values()):raise AssertionError('A hazard gate assertion failed')
        summary.update(state='PASS',**{'pass':1},actual_CSE='PASS',Group='PASS',
            frame_CINs=session.frames,notification_frames=session.frames,
            group_operations=len(session.delivery.results),
            stage_seconds={name:record['simulation_second'] for name,record in coverage.stages.items()},
            missing_device='display-c',final_delivery='INCOMPLETE',final_ACKs=2)
    except IntegrationBlocked as exc:
        summary.update(state='BLOCKED',blocked=1,reason=str(exc))
    except Exception as exc:
        summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        try:
            if not session.close() and summary['state']=='PASS':
                summary.update(state='FAIL',fail=1,**{'pass':0},reason='Independent device shutdown failed')
        except Exception as exc:
            summary.update(state='FAIL',fail=1,**{'pass':0},reason='Shutdown '+type(exc).__name__)
        session.evidence.write('hazard-coverage.json',{'stages':coverage.stages,
            'missing_stages':sorted(STAGES-set(coverage.stages))})
        session.evidence.write('assertions.json',checks)
        session.evidence.write('summary.json',summary)
    return summary,session.evidence.path


def main():
    summary,path=run(Settings.load(),Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-hazards.jsonl')))
    output=json.dumps({'evidence':str(path),**summary},sort_keys=True)
    (path/'tests.txt').write_text('command: '+json.dumps(sys.orig_argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
