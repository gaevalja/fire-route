"""Standalone JSONL analysis boundary; no CSE, HTTP or MEC client is created."""
import argparse
import json
import os
from pathlib import Path
import sys

from mec.risk.evacuation import load_assumptions
from onem2m.client import strict_json
from simulator.evacuation import Evacuation
from simulator.scenario_frames import ScenarioFrame

MAX_LINE=65536


def emit(stream,state,*,result=None,reason=None):
    data={'schema_version':1,'kind':'FireRouteRiskResult','processing_state':state,
        'result':result,'CSE':'NOT_CONTACTED','MEC':'NOT_CONTACTED'}
    if reason:data.update(reason=reason,guidance_status='UNKNOWN',route=None)
    stream.write(json.dumps(data,sort_keys=True,allow_nan=False)+'\n');stream.flush()


def run_stream(source,destination,*,assumptions=None):
    """One incident, consecutive validated frames. Reject and stop on invalid input."""
    accepted=duplicates=0
    try:
        model=Evacuation(assumptions)
        while True:
            line=source.readline(MAX_LINE+1)
            if not line:break
            if len(line)>MAX_LINE or not line.endswith(b'\n'):
                raise ValueError('Invalid bounded JSONL input')
            frame=ScenarioFrame.parse(strict_json(line))
            if model.accept(frame):
                emit(destination,'ACCEPTED',result=model.snapshot());accepted+=1
            else:
                # No result or new observation timestamp is fabricated for a duplicate.
                emit(destination,'DUPLICATE');duplicates+=1
        if not accepted:raise ValueError('No accepted frame')
    except (ValueError,KeyError,TypeError,RecursionError):
        emit(destination,'REJECTED',reason='INVALID_INPUT_OR_SEQUENCE')
        return {'state':'FAIL','accepted':accepted,'duplicates':duplicates,
            'CSE':'NOT_CONTACTED','MEC':'NOT_CONTACTED'}
    return {'state':'PASS','accepted':accepted,'duplicates':duplicates,
        'CSE':'NOT_CONTACTED','MEC':'NOT_CONTACTED'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assumptions',type=Path,default=os.getenv('RISK_ASSUMPTIONS_FILE') or None)
    args=parser.parse_args()
    try:
        if args.assumptions is not None and not args.assumptions.is_file():
            raise ValueError('Assumptions file unavailable')
        assumptions=load_assumptions(args.assumptions) if args.assumptions else None
    except (OSError,ValueError):
        emit(sys.stdout,'REJECTED',reason='INVALID_ASSUMPTIONS')
        print(json.dumps({'state':'FAIL','reason':'INVALID_ASSUMPTIONS'}),file=sys.stderr);return 2
    result=run_stream(sys.stdin.buffer,sys.stdout,assumptions=assumptions)
    print(json.dumps({'test':'STANDALONE_RISK_WORKER',**result}),file=sys.stderr)
    return 0 if result['state']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
