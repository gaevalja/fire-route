"""Synthetic verification fixtures, with no network or actual-CSE PASS claim."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.hazard_checks import HazardCoverage,verify_delivery
from simulator.evacuation import Evacuation
from tests.unit.test_evacuation import frame,raw


class HazardCoverageTests(unittest.TestCase):
    def setUp(self):
        self.model=Evacuation();self.model.accept(frame())
        self.coverage=HazardCoverage(self.model.navigation)
        self.coverage.observe(self.model.last,self.model.snapshot())

    def advance(self,changes):
        self.model.accept(frame(1,changes=changes))
        result=self.model.snapshot()
        return result,self.coverage.observe(self.model.last,result)

    def test_blocked_baseline_has_computed_alternative_even_when_exit_is_same(self):
        result,stages=self.advance({'F4-SA':{'fire_index':60}})
        self.assertIn('alternative',[x['stage'] for x in stages])
        self.assertNotIn('F4-SA',result['fixed_route']['path'])
        self.assertEqual(result['fixed_route']['target_exit'],'EXIT_A')

    def test_cost_or_queue_path_change_without_blocked_baseline_does_not_count(self):
        baseline=self.model.snapshot();other=copy.deepcopy(baseline)
        other['fixed_route']=self.model.navigation.route('F7-R3',occupied={tuple(sorted(('F1-L','EXIT_A'))):100})
        self.assertNotEqual(other['fixed_route']['path'],baseline['fixed_route']['path'])
        stages=self.coverage.observe(self.model.last,other)
        self.assertNotIn('alternative',[x['stage'] for x in stages])

    def test_no_route_requires_unblocked_origin_and_BFS_disconnection(self):
        result,stages=self.advance({'F7-SA':{'fire_index':60},'F7-SB':{'fire_index':60}})
        self.assertIn('isolated',[x['stage'] for x in stages])
        self.assertEqual(result['fixed_route']['path'],[])
        self.assertEqual(result['population']['total'],170)

    def test_blocked_origin_alone_does_not_satisfy_isolation_case(self):
        _,stages=self.advance({'F7-R3':{'fire_index':60}})
        self.assertNotIn('isolated',[x['stage'] for x in stages])

    def test_collapse_excludes_traversal_without_removing_residents(self):
        result,stages=self.advance({'F7-C1':{'collapsed':True}})
        self.assertIn('collapse',[x['stage'] for x in stages])
        self.assertNotIn('F7-C1',result['fixed_route']['path'])
        self.assertEqual(result['population']['total'],len(result['residents']))

    def test_fabricated_no_route_on_reachable_graph_fails(self):
        result=self.model.snapshot()
        result['fixed_route'].update(status='NO_VERIFIED_ROUTE',path=[],target_exit=None,routing_cost=None)
        with self.assertRaises(AssertionError):self.coverage.observe(self.model.last,result)

    def test_fabricated_route_through_blocked_baseline_fails(self):
        old=self.model.snapshot()['fixed_route']
        self.model.accept(frame(1,changes={'F4-SA':{'fire_index':60}}))
        result=self.model.snapshot();result['fixed_route']=old
        with self.assertRaises(AssertionError):self.coverage.observe(self.model.last,result)

    def test_lost_population_and_inconsistent_exit_state_fail(self):
        for mutate in [lambda r:r['residents'].pop(),
                       lambda r:r['population'].update(remaining=0),
                       lambda r:r['residents'][0].update(status='EVACUATED')]:
            result=self.model.snapshot();mutate(result)
            with self.assertRaises(AssertionError):self.coverage.observe(self.model.last,result)

    def test_wrong_event_version_or_policy_fails(self):
        for key,value in [('event_id','wrong'),('route_version',2),('policy_sha256','wrong')]:
            result=self.model.snapshot();result[key]=value
            with self.assertRaises(AssertionError):self.coverage.observe(self.model.last,result)

    def test_stage_reobservation_does_not_add_coverage(self):
        self.assertEqual(self.coverage.observe(self.model.last,self.model.snapshot()),[])


def delivery_fixture(result,missing=()):
    route=result['fixed_route'];command={k:result[k] for k in ['event_id','incident_id','route_version']}
    command.update(command_id='cmd-unit',route_exit=route['target_exit'],guidance_status=route['status'],
        action='DISPLAY_ROUTE' if route['target_exit'] else 'CLEAR_ROUTE')
    roles={'display-a','display-b','display-c'}-set(missing)
    return {'command':command,'ack_count':len(roles),'state':'INCOMPLETE' if missing else 'ALL_ACKED',
        'missing_devices':list(missing),
        'fanout':{'members':{r:{'ri':'cin-'+r} for r in ['display-a','display-b','display-c']}},
        'acks':{r:{'ack':{**command,'device_id':r,'status':'APPLIED'}} for r in roles},
        'display_states':{r:{k:command[k] for k in ['command_id','route_version','route_exit','guidance_status']} for r in roles}}


class HazardDeliveryTests(unittest.TestCase):
    def setUp(self):
        model=Evacuation();model.accept(frame());self.result=model.snapshot()

    def test_complete_and_expected_missing_device_are_distinct(self):
        verify_delivery(self.result,delivery_fixture(self.result))
        partial=delivery_fixture(self.result,{'display-c'})
        verify_delivery(self.result,partial,missing={'display-c'})
        with self.assertRaises(AssertionError):verify_delivery(self.result,partial)

    def test_aggregate_success_without_independent_ACKs_fails(self):
        delivery=delivery_fixture(self.result);delivery['acks']={}
        with self.assertRaises(AssertionError):verify_delivery(self.result,delivery)

    def test_repeated_device_identity_cannot_count_as_three(self):
        delivery=delivery_fixture(self.result)
        for record in delivery['acks'].values():record['ack']['device_id']='same-device'
        with self.assertRaises(AssertionError):verify_delivery(self.result,delivery)

    def test_unknown_repeated_or_missing_Group_member_fails(self):
        for mutate in [lambda d:d['fanout']['members'].pop('display-c'),
                       lambda d:d['fanout']['members']['display-c'].update(ri='cin-display-a')]:
            delivery=delivery_fixture(self.result);mutate(delivery)
            with self.assertRaises(AssertionError):verify_delivery(self.result,delivery)

    def test_wrong_ACK_version_or_uncleared_display_fails(self):
        for mutate in [lambda d:d['acks']['display-a']['ack'].update(route_version=900),
                       lambda d:d['display_states']['display-a'].update(route_exit=None)]:
            delivery=delivery_fixture(self.result);mutate(delivery)
            with self.assertRaises(AssertionError):verify_delivery(self.result,delivery)

    def test_no_route_requires_clear_command_and_null_device_direction(self):
        self.result['fixed_route'].update(status='NO_VERIFIED_ROUTE',target_exit=None,path=[],routing_cost=None)
        delivery=delivery_fixture(self.result);verify_delivery(self.result,delivery)
        delivery['display_states']['display-b']['route_exit']='EXIT_A'
        with self.assertRaises(AssertionError):verify_delivery(self.result,delivery)


class HazardPreviewTests(unittest.TestCase):
    def test_short_valid_source_cannot_pass_without_observed_hazard_stages(self):
        from simulator.hazard_preview import run
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/'short.jsonl'
            trace.write_text(json.dumps(raw())+'\n'+json.dumps(raw(1))+'\n')
            with patch.dict('os.environ',{'EVIDENCE_ROOT':str(Path(directory)/'evidence')}),patch('builtins.print'):
                summary,path=run(trace)
            self.assertEqual(summary['state'],'FAIL')
            self.assertIn('missing hazard stages',summary['reason'])
            self.assertEqual(summary['CSE'],'NOT_RUN');self.assertEqual(summary['ACKs'],'NOT_RUN')
            self.assertEqual(json.loads((path/'hazard-coverage.json').read_text())['missing_stages'],['alternative','collapse','isolated'])


if __name__=='__main__':unittest.main()
