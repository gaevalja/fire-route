"""Synthetic instrumentation collaborators; never real CSE benchmark evidence."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from onem2m.client import ProtocolError,TransportError
from tests.integration.latency_report import PRIMARY,summarize
from tests.integration.selected_latency import measure_attempt,observe_dispatch,run
from tests.unit.test_latency_report import DOMAIN,plan


class UnitDelivery:
    def __init__(self,state='ALL_ACKED'):
        self.state=state;self.calls=0

    def dispatch(self,route,**kwargs):
        self.calls+=1;count=3 if self.state=='ALL_ACKED' else 2
        return {'state':self.state,'ack_count':count,'command':{'command_id':'unit-command','event_id':route['event_id'],
            'route_version':route['route_version'],'incident_id':route['incident_id']},
            'acks':{r:{'ri':'unit-ack-'+r} for r in ['display-a','display-b','display-c'][:count]}}


def unit_session(state='ALL_ACKED'):
    session=SimpleNamespace(incident_id='unit-incident',delivery=UnitDelivery(state),model=SimpleNamespace(last=None),
        inbox=Mock(),evidence=Mock())
    session.inbox.find.return_value=[{'cin_ri':'unit-sensor-ci'}]
    def accept(raw):session.model.last={'sequence':raw['simulation_second']+1,'event_id':'unit-event'}
    def publish():
        result={'incident_id':session.incident_id,'route_version':session.model.last['sequence'],'event_id':'unit-event'}
        return result,session.delivery.dispatch(result,allow_incomplete=True)
    session.accept_raw=accept;session.publish=publish;return session


class ObserverTests(unittest.TestCase):
    def test_exact_boundaries_original_dispatch_once_and_restore_lookup(self):
        session=unit_session();original=session.delivery.dispatch;clock=Mock(side_effect=[100,200,300,500,600,700])
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=clock)
        self.assertIsNone(error);self.assertEqual(row['state'],'SUCCESS');self.assertEqual(session.delivery.calls,1)
        self.assertEqual(row['timings'],{'started_ns':100,'input_accepted_ns':200,'dispatch_started_ns':300,
            'dispatch_finished_ns':500,'pipeline_committed_ns':600,'finished_ns':700})
        self.assertEqual(session.delivery.dispatch,original);self.assertNotIn('dispatch',session.delivery.__dict__)
        session.evidence.append.assert_called_once();self.assertEqual(row['sensor_cin_ri'],'unit-sensor-ci')

    def test_transport_failure_is_recorded_without_invented_ACK_or_retry(self):
        session=unit_session();session.accept_raw=Mock(side_effect=TransportError('unit offline'))
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=Mock(side_effect=[100,700]))
        self.assertIsInstance(error,TransportError);self.assertEqual(row['state'],'FAILURE');self.assertIsNone(row['ack_count'])
        self.assertNotIn(PRIMARY,row['durations_ms']);self.assertEqual(session.delivery.calls,0)
        session.accept_raw.assert_called_once();session.evidence.append.assert_called_once()

    def test_operator_interrupt_retains_actual_started_attempt_without_success_metric(self):
        session=unit_session();session.accept_raw=Mock(side_effect=KeyboardInterrupt())
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=Mock(side_effect=[100,700]))
        self.assertIsInstance(error,KeyboardInterrupt);self.assertEqual(row['error_kind'],'KeyboardInterrupt')
        self.assertEqual(row['state'],'FAILURE');session.evidence.append.assert_called_once()
        self.assertEqual(summarize(plan(),[row])['counts']['warmup']['failed'],1)

    def test_incomplete_delivery_remains_incomplete_without_success_metric(self):
        session=unit_session('INCOMPLETE')
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=Mock(side_effect=[100,200,300,500,600,700]))
        self.assertIsNone(error);self.assertEqual(row['state'],'INCOMPLETE');self.assertEqual(row['ack_count'],2)
        self.assertNotIn(PRIMARY,row['durations_ms']);self.assertEqual(summarize(plan(),[row])['counts']['warmup']['incomplete'],1)

    def test_failure_after_ACK_before_public_commit_is_not_a_successful_pipeline(self):
        session=unit_session();original=session.publish
        def fail():original();raise TransportError('unit public commit failed')
        session.publish=fail
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=Mock(side_effect=[100,200,300,500,700]))
        self.assertIsInstance(error,TransportError);self.assertEqual(row['state'],'FAILURE');self.assertEqual(row['ack_count'],3)
        self.assertNotIn('pipeline_committed_ns',row['timings']);self.assertNotIn(PRIMARY,row['durations_ms'])
        self.assertNotIn('dispatch',session.delivery.__dict__)

    def test_wrapper_restores_instance_override_even_when_original_raises(self):
        delivery=UnitDelivery();override=Mock(side_effect=ProtocolError('unit invalid'))
        delivery.dispatch=override
        with self.assertRaises(ProtocolError):
            with observe_dispatch(delivery,{}, {},lambda:100):delivery.dispatch({})
        self.assertIs(delivery.dispatch,override);override.assert_called_once()

    def test_second_dispatch_in_one_attempt_rejected_before_duplicate_network_call(self):
        delivery=UnitDelivery();route={'event_id':'unit','route_version':1,'incident_id':'unit'}
        with observe_dispatch(delivery,{}, {},Mock(side_effect=[100,200])):
            delivery.dispatch(route)
            with self.assertRaises(ProtocolError):delivery.dispatch(route)
        self.assertEqual(delivery.calls,1)

    def test_invalid_source_callback_cannot_be_counted_as_success(self):
        session=unit_session();session.inbox.find.return_value=[]
        row,error=measure_attempt(session,{'simulation_second':0},1,plan(),clock=Mock(side_effect=[100,200,300,500,600,700]))
        self.assertIsInstance(error,ProtocolError);self.assertEqual(row['state'],'FAILURE')

    def test_unavailable_runtime_or_remote_target_is_blocked_with_null_statistics(self):
        for version,settings in [((3,10),SimpleNamespace()),((3,12),SimpleNamespace(cse_url='https://remote.invalid'))]:
            session=Mock();session.evidence.path=Path('unit-unused');session.close.return_value=True
            with patch('tests.integration.selected_latency.ScenarioSession',return_value=session), \
                    patch('tests.integration.selected_latency.sys',SimpleNamespace(version_info=version)):
                summary,_=run(settings,Path('unit-unused'))
            self.assertEqual(summary['state'],'BLOCKED');self.assertEqual(summary['latency_samples'],0)
            self.assertIsNone(summary['Observer_verified_all_acks_p50_ms']);session.start.assert_not_called()


if __name__=='__main__':unittest.main()
