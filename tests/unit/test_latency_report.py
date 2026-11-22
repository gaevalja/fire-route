"""Synthetic clock fixtures only; these values are not measured CSE latency."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tests.integration.latency_report import COMMIT,PRIMARY,durations,main,statistics,summarize

DOMAIN='unit-only-clock'


def plan(warmups=5,measured=30):
    return {'schema_version':1,'warmups':warmups,'measured':measured,'clock_domain':DOMAIN}


def sample(index,ns=1000000,*,warmups=5,state='SUCCESS'):
    start=index*1000000000
    return {'schema_version':1,'attempt_index':index,'phase':'warmup' if index<=warmups else 'measured',
        'state':state,'clock_domain':DOMAIN,'ack_count':3,'event_id':'unit-event-'+str(index),
        'incident_id':'unit-incident','command_id':'unit-command-'+str(index),'sensor_cin_ri':'unit-cin-'+str(index),
        'route_version':index,'simulation_second':index-1,
        'ack_cin_ris':{r:'unit-'+r+'-'+str(index) for r in ['display-a','display-b','display-c']},
        'timings':{'started_ns':start,'input_accepted_ns':start+ns//4,'dispatch_started_ns':start+ns//2,
            'dispatch_finished_ns':start+ns,'pipeline_committed_ns':start+ns+100000,'finished_ns':start+ns+200000}}


class LatencyReportTests(unittest.TestCase):
    def test_warmups_excluded_and_nearest_rank_uses_30_raw_measured_ticks(self):
        rows=[sample(i,999000000) for i in range(1,6)]+[sample(i+5,i*1000000) for i in range(1,31)]
        result=summarize(plan(),rows)
        self.assertEqual(result['statistics'][PRIMARY],{'N':30,'p50_ms':15.0,'p95_ms':29.0,'min_ms':1.0,'max_ms':30.0})
        self.assertEqual(result['statistics'][COMMIT]['p50_ms'],15.1)
        self.assertTrue(result['team_sample_target_met']);self.assertTrue(result['all_planned_attempts_successful'])

    def test_no_samples_have_null_percentiles_and_all_planned_attempts_unattempted(self):
        result=summarize(plan(),[])
        self.assertIsNone(result['statistics'][PRIMARY]['p50_ms']);self.assertEqual(result['counts']['measured']['not_attempted'],30)
        self.assertIsNone(result['counts']['measured']['completion_ratio']);self.assertFalse(result['team_sample_target_met'])

    def test_incomplete_failures_and_unattempted_are_retained_outside_percentiles(self):
        rows=[sample(1,warmups=0),sample(2,2000000,warmups=0),sample(3,warmups=0,state='INCOMPLETE'),sample(4,warmups=0,state='FAILURE')]
        rows[2]['ack_count']=2;rows[2]['ack_cin_ris'].pop('display-c')
        result=summarize(plan(0,30),rows);counts=result['counts']['measured']
        self.assertEqual((counts['attempted'],counts['complete'],counts['incomplete'],counts['failed'],counts['not_attempted']),(4,2,1,1,26))
        self.assertEqual(counts['completion_ratio'],.5);self.assertEqual(result['statistics'][PRIMARY]['N'],2)
        self.assertFalse(result['team_sample_target_met']);self.assertFalse(result['all_planned_attempts_successful'])

    def test_failure_with_no_verified_ACK_or_source_has_no_successful_metric(self):
        row=sample(1,state='FAILURE');row['timings']={'started_ns':1,'finished_ns':10}
        row.update(event_id=None,sensor_cin_ri=None,ack_count=None,ack_cin_ris={})
        self.assertNotIn(PRIMARY,durations(row));self.assertEqual(summarize(plan(),[row])['valid_measured_samples'],0)

    def test_success_without_three_distinct_ACKs_or_source_identity_is_invalid(self):
        for modify in [lambda r:r.update(ack_count=2),lambda r:r.update(sensor_cin_ri=None),
                       lambda r:r['ack_cin_ris'].update({'display-c':r['ack_cin_ris']['display-a']}),
                       lambda r:r.update(route_version=2),lambda r:r['timings'].pop('dispatch_started_ns')]:
            row=sample(1);modify(row)
            with self.assertRaises(ValueError):durations(row)

    def test_negative_regressing_boolean_and_missing_ticks_are_rejected(self):
        for key,value in [('started_ns',-1),('input_accepted_ns',False),('dispatch_finished_ns',0),('finished_ns',None)]:
            row=sample(1);row['timings'][key]=value
            with self.assertRaises(ValueError):durations(row)
        with self.assertRaises(ValueError):statistics([True])

    def test_wrong_phase_clock_domain_order_or_duplicate_identity_is_invalid(self):
        for field,value in [('phase','measured'),('clock_domain','foreign'),('attempt_index',2)]:
            row=sample(1);row[field]=value
            with self.assertRaises(ValueError):summarize(plan(),[row])
        rows=[sample(1),sample(2)];rows[1]['event_id']=rows[0]['event_id']
        with self.assertRaises(ValueError):summarize(plan(),rows)

    def test_invalid_budget_schema_or_extra_attempt_cannot_produce_green_counts(self):
        for p in [plan(True,30),plan(5,0),plan(5,1000),{**plan(),'schema_version':True}]:
            with self.assertRaises(ValueError):summarize(p,[])
        with self.assertRaises(ValueError):summarize(plan(0,1),[sample(1,warmups=0),sample(2,warmups=0)])
        row=sample(1);row['schema_version']=True
        with self.assertRaises(ValueError):durations(row)
        for value in [None,[],True]:
            with self.assertRaises(ValueError):durations(value)
            with self.assertRaises(ValueError):summarize(value,[])
        for key,value in [('timings',[]),('ack_cin_ris',['display-a','display-b','display-c'])]:
            row=sample(1);row[key]=value
            with self.assertRaises(ValueError):durations(row)

    def test_stage_durations_sum_to_committed_pipeline_and_cross_host_is_unavailable(self):
        d=durations(sample(1,4000000))
        self.assertEqual(d['input_accept_ms']+d['decision_persist_ms']+d['fanout_ACK_verify_ms']+d['public_commit_ms'],d[COMMIT])
        result=summarize(plan(),[sample(1)])
        self.assertIsNone(result['E2E_all_acks_ms']);self.assertEqual(result['cross_host_clock_sync'],'NOT_MEASURED')

    def test_report_CLI_recalculates_without_mutating_original_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'latency-plan.json';s=root/'latency-samples.jsonl'
            p.write_text(json.dumps(plan()));s.write_text(json.dumps(sample(1))+'\n');original=(p.read_bytes(),s.read_bytes())
            output=StringIO()
            with redirect_stdout(output):self.assertEqual(main([str(root)]),0)
            result=json.loads(output.getvalue());self.assertEqual(result['valid_measured_samples'],0)
            self.assertEqual((p.read_bytes(),s.read_bytes()),original);self.assertEqual(set(result['input_sha256']),{'plan','samples'})
            s.write_text(json.dumps(sample(1)))
            with redirect_stdout(StringIO()):self.assertEqual(main([str(root)]),1)


if __name__=='__main__':unittest.main()
