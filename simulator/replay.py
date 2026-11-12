"""Offline dual-mode model preview. This command never calls a CSE or MEC."""
import json
import os
from pathlib import Path
from uuid import uuid4

from backend.evidence import Evidence,source_identity
from simulator.evacuation import Evacuation
from simulator.scenario_frames import ROOT,emission,read_trace,source_manifest,trace_digest


def main():
    out = Evidence(Path('evidence'))
    model = Evacuation()
    digest = source_manifest()['bundle_sha256']
    incident = 'inc-'+uuid4().hex
    frames = 0
    trace_hash = None
    try:
        trace_hash = trace_digest(Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-trace.jsonl')))
        for raw in read_trace(Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-trace.jsonl')),digest):
            model.accept(emission(raw,incident,'offline:source-replay',digest));frames += 1
            if raw['simulation_second'] % 30 == 0 or raw['ended']:
                value = model.snapshot()
                out.append('model-samples.jsonl',value)
                print(json.dumps({'kind':'OFFLINE_MODEL_NOT_CSE','simulation_second':raw['simulation_second'],
                    'fixed_origin':value['fixed_route']['source_node'],'fixed_exit':value['fixed_route']['target_exit'],
                    'fixed_status':value['fixed_route']['status'],'population':value['population']}),flush=True)
        if not frames:raise ValueError('Empty source trace')
        out.write('last-model.json',model.snapshot())
        summary = {'test':'DUAL_MODE_OFFLINE','state':'PASS','frames':frames,'population':model.snapshot()['population'],
            'CSE':'NOT_RUN','UI':'NOT_RUN','MEC':'unavailable','model_provenance':'ASSUMED_NOT_CALIBRATED'}
    except Exception as exc:
        summary = {'test':'DUAL_MODE_OFFLINE','state':'FAIL','reason':type(exc).__name__,'CSE':'NOT_RUN','UI':'NOT_RUN'}
    out.write('meta.json',{'source_bundle_sha256':digest,'trace_sha256':trace_hash,'assumptions':model.navigation.assumptions,
        'policy_sha256':model.navigation.policy_hash,**source_identity(ROOT)})
    out.write('summary.json',summary)
    print(json.dumps({'evidence':str(out.path),**summary},sort_keys=True))
    return 0 if summary['state']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
