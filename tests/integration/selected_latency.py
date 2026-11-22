"""Actual CSE observer measurement; no fake service or device acknowledgements."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import urlsplit

from backend.config import Settings
from backend.p0 import IntegrationBlocked
from backend.scenario_core import ScenarioSession
from onem2m.client import CSEError,ProtocolError
from simulator.scenario_frames import read_trace,trace_digest
from tests.integration.latency_report import COMMIT,MEASURED,PRIMARY,WARMUPS,durations,summarize


@contextmanager
def observe_dispatch(delivery,marks,capture,clock):
    """Stamp the original real dispatch call; restore instance/class lookup."""
    original=delivery.dispatch;absent=object();previous=delivery.__dict__.get('dispatch',absent)
    def measured(route,**kwargs):
        if marks.get('dispatch_started_ns') is not None:raise ProtocolError('More than one dispatch per observation')
        marks['dispatch_started_ns']=clock()
        result=original(route,**kwargs)
        marks['dispatch_finished_ns']=clock();capture['delivery']=result
        return result
    delivery.dispatch=measured
    try:yield
    finally:
        if previous is absent:del delivery.dispatch
        else:delivery.dispatch=previous


def measure_attempt(session,raw,index,plan,*,clock=None):
    clock=time.perf_counter_ns if clock is None else clock
    marks={'started_ns':clock()};capture={};error=None
    row={'schema_version':1,'attempt_index':index,'phase':'warmup' if index<=plan['warmups'] else 'measured',
        'clock_domain':plan['clock_domain'],'simulation_second':raw['simulation_second'],'state':'FAILURE',
        'route_version':None,'event_id':None,'command_id':None,'sensor_cin_ri':None,
        'incident_id':session.incident_id,'ack_count':None,'ack_cin_ris':{},'timings':marks}
    try:
        session.accept_raw(raw);marks['input_accepted_ns']=clock()
        frame=session.model.last
        if frame['sequence']!=raw['simulation_second']+1:raise ProtocolError('Measured source cursor differs')
        row.update(event_id=frame['event_id'],route_version=frame['sequence'])
        with observe_dispatch(session.delivery,marks,capture,clock):
            result,delivered=session.publish()
        marks['pipeline_committed_ns']=clock()
        command=delivered['command']
        if (capture.get('delivery') is not delivered or result['event_id']!=row['event_id']
                or result['route_version']!=row['route_version'] or command['event_id']!=row['event_id']
                or command['route_version']!=row['route_version'] or command['incident_id']!=session.incident_id):
            raise ProtocolError('Measured delivery identity differs')
        if delivered['state']=='ALL_ACKED' and delivered['ack_count']==3:
            row['state']='SUCCESS'
        elif delivered['state']=='INCOMPLETE' and type(delivered['ack_count']) is int and 0<=delivered['ack_count']<3:
            row['state']='INCOMPLETE'
        else:raise ProtocolError('Invalid measured delivery outcome')
    except (Exception,KeyboardInterrupt) as exc:
        error=exc;row.update(state='FAILURE',error_kind=type(exc).__name__)
        if isinstance(exc,CSEError):row.update(http_status=exc.http_status,rsc=exc.rsc)
    finally:
        marks['finished_ns']=clock()
        delivered=capture.get('delivery')
        if delivered:
            row.update(command_id=delivered['command']['command_id'],ack_count=delivered['ack_count'],
                ack_cin_ris={role:a['ri'] for role,a in delivered['acks'].items()})
        if row['event_id']:
            try:
                records=session.inbox.find(row['event_id'])
                if len(records)!=1:raise ProtocolError('Measured input callback identity missing')
                row['sensor_cin_ri']=records[0]['cin_ri']
            except Exception as exc:
                error=error or exc;row.update(state='FAILURE',error_kind=type(exc).__name__)
        try:row['durations_ms']=durations(row)
        except (ValueError,KeyError,TypeError) as exc:
            error=error or exc;row.update(state='FAILURE',error_kind=type(exc).__name__)
        session.evidence.append('latency-samples.jsonl',row)
    return row,error


def run(settings,trace):
    session=ScenarioSession(settings);out=session.evidence;samples=[];checks={}
    info=time.get_clock_info('perf_counter')
    plan={'schema_version':1,'warmups':WARMUPS,'measured':MEASURED,'clock_domain':out.path.name+':coordinator-pid:'+str(os.getpid()),
        'clock':{'method':'perf_counter_ns','implementation':info.implementation,'monotonic':info.monotonic,
            'adjustable':info.adjustable,'resolution_seconds':info.resolution},
        'primary_metric':PRIMARY,'commit_metric':COMMIT,'input':'SYNTHETIC_SOURCE_REPLAY',
        'workload':'SEQUENTIAL_BASELINE_SIMULATION_SECONDS_0_TO_34_ONE_OUTSTANDING_FRAME_THREE_DISPLAYS',
        'start':'BEFORE_SESSION_ACCEPT_RAW','primary_end':'AFTER_REAL_DISPATCH_ACK_READBACK_DEVICE_STATE_AND_JOURNAL',
        'commit_end':'AFTER_PUBLISH_PUBLIC_STATUS_COMMIT','cross_host_clock_sync':'NOT_MEASURED',
        'excluded':'BOOTSTRAP_PER_SAMPLE_REPORT_SERIALIZATION_AND_BROWSER_POLL_RENDER','MEC':'unavailable'}
    summary={'test':'P1_SELECTED_LATENCY','state':'NOT_RUN','pass':0,'fail':0,'blocked':0,'Hosted':'NOT_CONTACTED',
        'MEC':'unavailable','input':'SYNTHETIC_SOURCE_REPLAY','browser':'NOT_RUN','latency_samples':0,
        'primary_metric':PRIMARY,'Observer_verified_all_acks_p50_ms':None,'Observer_verified_all_acks_p95_ms':None,
        'E2E_all_acks_ms':None,'cross_host_clock_sync':'NOT_MEASURED','latency_SLO':'NOT_CLAIMED'}
    out.write('latency-plan.json',plan)
    try:
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 latency Compose profile')
        if urlsplit(settings.cse_url).hostname not in {'cse','localhost','127.0.0.1'}:
            raise IntegrationBlocked('This measurement profile is limited to the actual local CSE')
        if not info.monotonic or info.adjustable:raise IntegrationBlocked('Monotonic observer clock unavailable')
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
        except OSError:raise IntegrationBlocked('Actual CSE measurement sockets unavailable') from None
        session.start()
        meta=json.loads((out.path/'meta.json').read_text());out.write('meta.json',{**meta,'test':summary['test'],'measurement':plan})
        out.write('replay-source.json',{'kind':'SYNTHETIC_SOURCE_REPLAY','trace_sha256':trace_digest(trace),
            'source_bundle_sha256':session.hash})
        source=iter(read_trace(trace,session.hash))
        for index in range(1,WARMUPS+MEASURED+1):
            try:raw=next(source)
            except StopIteration:raise AssertionError('Export all planned source frames before measuring') from None
            row,error=measure_attempt(session,raw,index,plan);samples.append(row)
            print(json.dumps({'test':summary['test'],'phase':row['phase'].upper(),'attempt':index,'state':row['state'],
                PRIMARY:row.get('durations_ms',{}).get(PRIMARY)}),flush=True)
            if error:raise error  # No unsafe replay or invented future attempts.
        report=summarize(plan,samples)
        checks['all_35_attempts_successful']=report['all_planned_attempts_successful']
        checks['five_warmups_and_30_verified_measured_samples']=report['team_sample_target_met']
        checks['35_consecutive_real_CSE_frames']=session.frames==WARMUPS+MEASURED
        checks['35_real_Group_deliveries_105_independent_ACKs']=(len(session.delivery.results)==WARMUPS+MEASURED
            and all(d['state']=='ALL_ACKED' and d['ack_count']==3 for d in session.delivery.results))
        if not all(checks.values()):raise AssertionError('Measured completion/sample target failed; inspect counts')
        summary.update(state='PASS',**{'pass':1},actual_CSE='PASS',Group='PASS')
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',blocked=1,reason=str(exc))
    except KeyboardInterrupt:
        summary.update(state='FAIL',fail=1,reason='Operator interrupted measurement; attempted samples retained')
    except Exception as exc:
        summary.update(state='FAIL',fail=1,reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        try:
            report=summarize(plan,samples);out.write('latency-report.json',report)
            stats=report['statistics'][PRIMARY]
            summary.update(latency_samples=stats['N'],counts=report['counts'],
                Observer_verified_all_acks_p50_ms=stats['p50_ms'],Observer_verified_all_acks_p95_ms=stats['p95_ms'])
        except Exception:
            summary.update(state='FAIL',fail=1,**{'pass':0},reason='Invalid measurement evidence; no percentile inferred')
        try:
            if not session.close():raise ProtocolError('Independent display cleanup failed')
        except Exception:summary.update(state='FAIL',fail=1,**{'pass':0},reason='Measurement cleanup failed')
        out.write('assertions.json',checks);out.write('summary.json',summary)
    return summary,out.path


def main():
    summary,path=run(Settings.load(),Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-latency.jsonl')))
    output=json.dumps({'evidence':str(path),**summary});(path/'tests.txt').write_text('command: '+json.dumps(sys.argv)+'\n'+output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
