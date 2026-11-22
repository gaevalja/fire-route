"""Read-only raw-tick statistics; not independent proof of real CSE operation."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from onem2m.client import strict_json

WARMUPS=5
MEASURED=30
PRIMARY='Observer_verified_all_acks_ms'
COMMIT='Observer_pipeline_commit_ms'
TICKS=('started_ns','input_accepted_ns','dispatch_started_ns','dispatch_finished_ns','pipeline_committed_ns','finished_ns')


def integer(value,minimum=0):
    if type(value) is not int or value<minimum:raise ValueError('Invalid measurement integer')
    return value


def durations(row):
    if not isinstance(row,dict) or type(row.get('schema_version')) is not int or row['schema_version']!=1 or row.get('state') not in {'SUCCESS','INCOMPLETE','FAILURE'}:
        raise ValueError('Invalid latency sample schema/state')
    ticks=row['timings']
    if not isinstance(ticks,dict):raise ValueError('Invalid observer timestamp object')
    present=[integer(ticks[k]) for k in TICKS if ticks.get(k) is not None]
    if ticks.get('started_ns') is None or ticks.get('finished_ns') is None or present!=sorted(present):
        raise ValueError('Missing or non-monotonic observer ticks')
    result={'attempt_elapsed_ms':round((ticks['finished_ns']-ticks['started_ns'])/1e6,3)}
    if row['state']=='INCOMPLETE':
        count=integer(row.get('ack_count'));ids=row.get('ack_cin_ris',{})
        if count>=3 or not isinstance(ids,dict) or len(ids)!=count:
            raise ValueError('Incomplete outcome/count differs')
    if row['state']=='SUCCESS':
        if any(ticks.get(k) is None for k in TICKS):raise ValueError('Complete pipeline timestamps required')
        if row.get('ack_count')!=3 or type(row.get('ack_count')) is not int:
            raise ValueError('Three verified ACKs required for successful sample')
        if not isinstance(row.get('ack_cin_ris'),dict) or set(row['ack_cin_ris'])!={'display-a','display-b','display-c'}:
            raise ValueError('Independent ACK identities required')
        ids=list(row['ack_cin_ris'].values())
        if any(not isinstance(v,str) or not v for v in ids) or len(set(ids))!=3:
            raise ValueError('ACK resource IDs must be distinct')
        for key in ['event_id','incident_id','command_id','sensor_cin_ri']:
            if not isinstance(row.get(key),str) or not row[key]:raise ValueError('Successful correlation missing')
        if integer(row['route_version'],1)!=integer(row['simulation_second'])+1:
            raise ValueError('Successful sample source/version differs')
        result[PRIMARY]=round((ticks['dispatch_finished_ns']-ticks['started_ns'])/1e6,3)
        result[COMMIT]=round((ticks['pipeline_committed_ns']-ticks['started_ns'])/1e6,3)
        result.update(input_accept_ms=round((ticks['input_accepted_ns']-ticks['started_ns'])/1e6,3),
            decision_persist_ms=round((ticks['dispatch_started_ns']-ticks['input_accepted_ns'])/1e6,3),
            fanout_ACK_verify_ms=round((ticks['dispatch_finished_ns']-ticks['dispatch_started_ns'])/1e6,3),
            public_commit_ms=round((ticks['pipeline_committed_ns']-ticks['dispatch_finished_ns'])/1e6,3))
    return result


def statistics(nanoseconds):
    values=sorted(integer(value) for value in nanoseconds);n=len(values)
    def at(p):return round(values[math.ceil(p*n)-1]/1e6,3) if n else None
    return {'N':n,'p50_ms':at(.5),'p95_ms':at(.95),
        'min_ms':round(values[0]/1e6,3) if n else None,'max_ms':round(values[-1]/1e6,3) if n else None}


def summarize(plan,samples):
    if not isinstance(plan,dict) or type(plan.get('schema_version')) is not int or plan['schema_version']!=1:
        raise ValueError('Invalid measurement plan version')
    warmups=integer(plan['warmups']);measured=integer(plan['measured'],1)
    if warmups+measured>1000 or len(samples)>warmups+measured:raise ValueError('Measurement budget exceeded')
    if not isinstance(plan.get('clock_domain'),str) or not plan['clock_domain']:raise ValueError('Observer domain required')
    phase_rows={'warmup':[],'measured':[]};seen={key:set() for key in ['event_id','command_id','sensor_cin_ri','route_version']}
    incident=None
    for index,row in enumerate(samples,1):
        if integer(row['attempt_index'],1)!=index:raise ValueError('Attempt ordering/gap differs')
        phase='warmup' if index<=warmups else 'measured'
        if row['phase']!=phase or row['clock_domain']!=plan['clock_domain']:raise ValueError('Phase/clock domain differs')
        durations(row)
        if row['state'] in {'SUCCESS','INCOMPLETE'}:
            for key,values in seen.items():
                value=row.get(key)
                if value is None or value=='' or value in values:raise ValueError('Duplicate or missing attempt identity')
                values.add(value)
            if incident is None:incident=row['incident_id']
            if row['incident_id']!=incident:raise ValueError('Measurement incident differs')
        phase_rows[phase].append(row)
    counts={}
    for phase,planned in [('warmup',warmups),('measured',measured)]:
        data=phase_rows[phase];complete=sum(r['state']=='SUCCESS' for r in data)
        counts[phase]={'planned':planned,'attempted':len(data),'complete':complete,
            'incomplete':sum(r['state']=='INCOMPLETE' for r in data),'failed':sum(r['state']=='FAILURE' for r in data),
            'not_attempted':planned-len(data),'completion_ratio':complete/len(data) if data else None}
    valid=[r for r in phase_rows['measured'] if r['state']=='SUCCESS']
    stats={PRIMARY:statistics([r['timings']['dispatch_finished_ns']-r['timings']['started_ns'] for r in valid]),
        COMMIT:statistics([r['timings']['pipeline_committed_ns']-r['timings']['started_ns'] for r in valid])}
    return {'schema_version':1,'scope':'STATISTICAL_RECALCULATION_ONLY_NOT_INDEPENDENT_CSE_PROOF',
        'percentile_method':'NEAREST_RANK_FROM_INTEGER_NS_ROUND_MS_3_DECIMALS','clock_domain':plan['clock_domain'],
        'counts':counts,'statistics':stats,'valid_measured_samples':len(valid),
        'team_sample_target_met':counts['warmup']['complete']>=WARMUPS and counts['measured']['complete']>=MEASURED,
        'all_planned_attempts_successful':all(c['complete']==c['planned'] for c in counts.values()),
        'E2E_all_acks_ms':None,'cross_host_clock_sync':'NOT_MEASURED'}


def main(argv=None):
    parser=argparse.ArgumentParser(description='Recompute local observer statistics without changing evidence')
    parser.add_argument('evidence',type=Path);args=parser.parse_args(argv)
    try:
        plan_path=args.evidence/'latency-plan.json';samples_path=args.evidence/'latency-samples.jsonl'
        plan=strict_json(plan_path.read_bytes())
        raw=samples_path.read_bytes() if samples_path.exists() else b''
        if raw and not raw.endswith(b'\n'):raise ValueError('Truncated measurement evidence')
        data=[strict_json(line) for line in raw.splitlines()]
        result=summarize(plan,data)
        result['input_sha256']={'plan':hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            'samples':hashlib.sha256(raw).hexdigest()}
        print(json.dumps(result,sort_keys=True));return 0
    except (OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'state':'INVALID','scope':'READ_ONLY_RECALCULATION','reason':'Invalid or unavailable plan/sample evidence'}));return 1


if __name__=='__main__':raise SystemExit(main())
