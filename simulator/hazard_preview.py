"""Offline unchanged-source hazard coverage. No CSE, device or MEC operation."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from backend.evidence import Evidence,source_identity
from backend.hazard_checks import HazardCoverage,STAGES
from simulator.evacuation import Evacuation
from simulator.scenario_frames import ROOT,emission,read_trace,source_manifest,trace_digest


def run(trace):
    out=Evidence(Path(os.getenv('EVIDENCE_ROOT','evidence')))
    model=Evacuation();coverage=HazardCoverage(model.navigation)
    digest=source_manifest()['bundle_sha256'];incident='inc-'+uuid4().hex;frames=0
    summary={'test':'SELECTED_HAZARDS_OFFLINE','state':'NOT_RUN','CSE':'NOT_RUN',
        'Group':'NOT_RUN','ACKs':'NOT_RUN','MEC':'unavailable','UI':'NOT_RUN',
        'model_provenance':'ASSUMED_NOT_CALIBRATED'}
    try:
        out.write('meta.json',{'test':summary['test'],'kind':'OFFLINE_SOURCE_MODEL_NOT_CSE','source_bundle_sha256':digest,
            'trace_sha256':trace_digest(trace),'assumptions':model.navigation.assumptions,**source_identity(ROOT)})
        for raw in read_trace(trace,digest):
            model.accept(emission(raw,incident,'offline:hazards',digest));frames+=1
            for stage in coverage.observe(model.last,model.snapshot()):
                out.append('hazard-stages.jsonl',stage)
                print(json.dumps({'kind':'OFFLINE_NOT_CSE','stage':stage['stage'],
                    'simulation_second':stage['simulation_second']}),flush=True)
            if coverage.complete:break
        missing=STAGES-set(coverage.stages)
        if missing:raise AssertionError('Trace missing hazard stages: '+', '.join(sorted(missing)))
        summary.update(state='PASS',frames=frames,
            stage_seconds={k:v['simulation_second'] for k,v in coverage.stages.items()})
    except Exception as exc:
        summary.update(state='FAIL',reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:
        out.write('hazard-coverage.json',{'stages':coverage.stages,'missing_stages':sorted(STAGES-set(coverage.stages))})
        out.write('summary.json',summary)
    return summary,out.path


def main():
    summary,path=run(Path(os.getenv('SCENARIO_TRACE','.runtime/fire-evac-hazards.jsonl')))
    output=json.dumps({'evidence':str(path),**summary},sort_keys=True)
    (path/'tests.txt').write_text('command: '+json.dumps(sys.orig_argv)+'\n'+output+'\n')
    print(output);return 0 if summary['state']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
