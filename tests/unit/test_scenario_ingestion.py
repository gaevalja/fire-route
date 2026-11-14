"""Synthetic live-input/consumer fixtures; never actual CSE evidence."""
import copy
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import Mock

from backend.config import Settings
from backend.scenario_core import ScenarioSession
from backend.scenario_ingestion import accept_live_frame
from onem2m.client import ProtocolError
from simulator.evacuation import Evacuation
from simulator.scenario_frames import ScenarioFrame
from tests.unit.test_evacuation import HASH,config,frame

NOW=datetime(2026,11,14,10,tzinfo=timezone.utc)


class LiveIngestionTests(unittest.TestCase):
    def setUp(self):
        self.model=Evacuation(config());self.settings=Settings()
        self.first=self.input(0)
        self.assertEqual(self.accept(self.first).state,'ACCEPTED')

    def input(self,second,**changes):
        value=frame(second);value.data.update(timestamp_utc=NOW.isoformat(),**changes)
        return value

    def accept(self,value,now=NOW):
        return accept_live_frame(self.model,value,self.settings,HASH,now=now)

    def test_next_frame_advances_once_and_exact_replay_keeps_time_and_people(self):
        value=self.input(1);self.assertEqual(self.accept(value).state,'ACCEPTED')
        before=copy.deepcopy(self.model.snapshot())
        self.assertEqual(self.accept(value,now=NOW+timedelta(minutes=10)).state,'DUPLICATE')
        self.assertEqual(self.model.snapshot(),before)

    def test_expired_future_and_regressing_clocks_reject_without_mutation(self):
        for age,reason in [(30,'EXPIRED'),(300,'EXPIRED'),(-6,'FUTURE'),(1,'TIMESTAMP_REGRESSION')]:
            value=self.input(1);value.data['timestamp_utc']=(NOW-timedelta(seconds=age)).isoformat()
            before=copy.deepcopy(self.model.snapshot())
            result=self.accept(value)
            self.assertEqual((result.state,result.reason),('REJECTED',reason))
            self.assertEqual(self.model.snapshot(),before)

    def test_stale_sequence_gap_and_changed_context_do_not_refresh_observation(self):
        cases=[self.input(0,event_id='new-old-frame'),self.input(2),
            self.input(1,incident_id='other-incident'),self.input(1,source='other-source')]
        for value in cases:
            before=copy.deepcopy(self.model.snapshot())
            self.assertEqual(self.accept(value).reason,'ORDER_OR_CONTEXT')
            self.assertEqual(self.model.snapshot(),before)

    def test_malformed_constructed_dataclass_is_revalidated_before_accept(self):
        value=self.input(1);value.data['zones'][0]['fire_index']=101
        before=copy.deepcopy(self.model.snapshot())
        with self.assertRaises(ValueError):self.accept(ScenarioFrame(value.data))
        self.assertEqual(self.model.snapshot(),before)

    def test_rejection_does_not_erase_existing_hazards(self):
        blocked=frame(1,changes={'F1-R1':{'fire_index':80}});blocked.data['timestamp_utc']=NOW.isoformat()
        self.accept(blocked);before=set(self.model.navigation.blocked)
        self.assertIn('F1-R1',before)
        self.accept(self.input(0,event_id='other-old-frame'))
        self.assertEqual(set(self.model.navigation.blocked),before)

    def test_implementation_fault_is_not_mislabeled_rejected_input(self):
        self.model.accept=Mock(side_effect=RuntimeError('synthetic invariant failure'))
        with self.assertRaises(RuntimeError):self.accept(self.input(1))

    def test_live_clock_requires_aware_UTC(self):
        with self.assertRaises(ValueError):self.accept(self.input(1),now=NOW.replace(tzinfo=None))


class DurableConsumerTests(unittest.TestCase):
    def session(self,value,ri='unit-cin'):
        session=object.__new__(ScenarioSession);session.settings=Settings();session.hash=HASH
        session.incident_id='inc-unit';session.namespace='unit'
        session.model=Evacuation(config());session.frames=0;session.evidence=Mock()
        session.inbox=Mock();session.inbox.find.return_value=[{'cin_ri':ri,'event':value.to_dict()}]
        return session

    def test_actual_callback_binding_is_required_before_any_model_advance(self):
        value=frame();value.data['source']='unit:scenario-replay';session=self.session(value)
        with self.assertRaises(ProtocolError):session.consume_received(value,'different-cin')
        self.assertIsNone(session.model.last);self.assertEqual(session.frames,0)

    def test_replay_does_not_add_a_frame_or_refresh_source_time(self):
        value=frame();value.data['source']='unit:scenario-replay';session=self.session(value)
        self.assertEqual(session.consume_received(value,'unit-cin').state,'ACCEPTED')
        before=copy.deepcopy(session.model.snapshot())
        self.assertEqual(session.consume_received(value,'unit-cin').state,'DUPLICATE')
        self.assertEqual(session.frames,1);self.assertEqual(session.model.snapshot(),before)
        calls=session.evidence.append.call_args_list
        self.assertEqual(sum(c.args[0]=='frames.jsonl' for c in calls),1)
        self.assertEqual(sum(c.args[0]=='ingestion.jsonl' for c in calls),2)

    def test_first_actual_callback_cannot_choose_another_incident_or_source(self):
        for field,value in [('incident_id','inc-other'),('source','other:source')]:
            sample=frame();sample.data['source']='unit:scenario-replay';sample.data[field]=value
            session=self.session(sample)
            receipt=session.consume_received(sample,'unit-cin')
            self.assertEqual((receipt.state,receipt.reason),('REJECTED','BOUND_CONTEXT'))
            self.assertIsNone(session.model.last);self.assertEqual(session.frames,0)


if __name__=='__main__':unittest.main()
