"""Synthetic transport/state fixtures only; never actual CSE recovery evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from backend.config import Settings
from backend.scenario_demo import ScenarioApp
from backend.scenario_input import PendingInput
from onem2m.client import CSEClient,CSEError,ProtocolError,ResourceConflict,TransportError
from tests.unit.test_evacuation import HASH,raw


class PendingInputTests(unittest.TestCase):
    def setUp(self):
        self.pending=PendingInput(raw(),'inc-unit','unit:scenario-replay',HASH)
        self.settings=Settings();self.evidence=Mock();self.parent='/base/owned/telemetry'
        self.client=Mock();self.client.resource.side_effect=CSEClient.resource

    def absent(self):return CSEError('unit missing',http_status=404,rsc=4004)

    def resource(self):
        return {'m2m:cin':{'ty':4,'ri':'unit-cin','rn':'frame-1','cnf':'application/json:0',
            'con':json.dumps(self.pending.frame.to_dict(),separators=(',',':'))}}

    def deliver(self):return self.pending.deliver(self.client,self.parent,self.settings,self.evidence)

    def expire(self):
        self.pending.frame.data['timestamp_utc']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()

    def test_failed_lookup_preserves_exact_input_without_POST_or_restamp(self):
        before=self.pending.frame.to_dict();self.client.retrieve.side_effect=TransportError('unit disconnect')
        for _ in range(2):
            with self.assertRaises(TransportError):self.deliver()
        self.assertEqual(self.pending.frame.to_dict(),before);self.client.create.assert_not_called()

    def test_uncertain_POST_is_reconciled_by_GET_without_repeating_CREATE(self):
        value=self.resource();self.client.retrieve.side_effect=[self.absent(),value,value]
        self.client.create.side_effect=TransportError('unit response lost after server commit')
        before=self.pending.frame.to_dict()
        with self.assertRaises(TransportError):self.deliver()
        frame,cin=self.deliver()
        self.assertEqual(frame.to_dict(),before);self.assertEqual(cin['ri'],'unit-cin')
        self.assertEqual(self.client.create.call_count,1)

    def test_expired_observation_is_resampled_only_after_actual_not_found(self):
        self.expire();old=self.pending.frame.to_dict();raw_before=deepcopy(self.pending.raw)
        self.client.create.side_effect=lambda *args:self.resource()
        def lookup(path):
            if self.client.create.called:return self.resource()
            raise self.absent()
        self.client.retrieve.side_effect=lookup
        frame,_=self.deliver()
        self.assertNotEqual(frame.event_id,old['event_id']);self.assertNotEqual(frame.data['timestamp_utc'],old['timestamp_utc'])
        self.assertEqual(self.pending.raw,raw_before);self.assertEqual(self.client.create.call_count,1)
        record=self.evidence.append.call_args.args[1]
        self.assertEqual((record['state'],record['actual_http_status'],record['actual_rsc']),('RESAMPLED_ABSENT_SYNTHETIC_INPUT',404,4004))

    def test_expired_stored_observation_never_restamped_or_reposted(self):
        self.expire();before=self.pending.frame.to_dict();self.client.retrieve.return_value=self.resource()
        with self.assertRaisesRegex(ProtocolError,'expired'):self.deliver()
        self.assertEqual(before,self.pending.frame.to_dict());self.client.create.assert_not_called()

    def test_permission_protocol_or_wrong_HTTP_not_found_never_permit_CREATE(self):
        for exc in [CSEError('unit denial',http_status=403,rsc=4103),ProtocolError('unit malformed',http_status=404,rsc=4004),
                    CSEError('unit inconsistent',http_status=500,rsc=4004)]:
            self.client.retrieve.side_effect=exc
            with self.assertRaises(CSEError):self.deliver()
        self.client.create.assert_not_called()

    def test_conflicting_named_content_is_never_overwritten(self):
        value=self.resource();value['m2m:cin']['con']='{}';self.client.retrieve.return_value=value
        with self.assertRaises(ResourceConflict):self.deliver()
        self.client.create.assert_not_called()

    def test_CREATE_conflict_requires_matching_actual_readback(self):
        value=self.resource();self.client.retrieve.side_effect=[self.absent(),value,value]
        self.client.create.side_effect=CSEError('unit race',http_status=409,rsc=4105)
        frame,cin=self.deliver();self.assertEqual(cin['ri'],'unit-cin');self.assertEqual(self.client.create.call_count,1)
        self.assertEqual(frame.to_dict(),self.pending.frame.to_dict())

    def test_pending_raw_is_copied_and_different_next_frame_cannot_match(self):
        sample=raw();pending=PendingInput(sample,'inc-unit','unit:source',HASH)
        sample['zones'][0]['fire_index']=5
        self.assertFalse(pending.matches(sample));self.assertTrue(pending.matches(raw()))


class AppRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=ScenarioApp(Settings(evidence_root=Path(self.tmp.name)),Path('unit-unused'))
        self.app.context=Mock();self.app.context.incident_id='inc-unit';self.app.context.model.last={'sequence':1}
        self.app.iterator=iter([{'simulation_second':i} for i in range(31)])
        self.app.busy=False;self.app.state='READY';self.app.paused=True

    def test_transport_loss_retains_source_cursor_and_resumes_once(self):
        self.app.context.accept_raw.side_effect=[TransportError('unit offline'),None]
        self.assertEqual(self.app.advance(),'RECOVERING');pending=deepcopy(self.app.pending_raw)
        self.assertEqual(self.app.remaining,1);self.app.context.publish.assert_not_called()
        self.assertEqual(self.app.advance(recovering=True),'READY')
        self.assertEqual([c.args[0] for c in self.app.context.accept_raw.call_args_list],[pending,pending])
        self.app.context.publish.assert_called_once();self.assertIsNone(self.app.pending_raw)
        self.assertTrue(self.app.paused);self.assertIsNone(self.app.recovery_deadline)

    def test_partial_batch_recovery_neither_skips_nor_replays_accepted_rows(self):
        self.app.context.accept_raw.side_effect=[None,None,TransportError('unit offline')]+[None]*28
        self.assertEqual(self.app.advance(30),'RECOVERING');self.assertEqual(self.app.remaining,28)
        self.assertEqual(self.app.advance(recovering=True),'READY')
        sequence=[c.args[0]['simulation_second'] for c in self.app.context.accept_raw.call_args_list]
        self.assertEqual(sequence,[0,1,2]+list(range(2,30)));self.app.context.publish.assert_called_once()
        self.assertEqual(next(self.app.iterator)['simulation_second'],30)

    def test_recovery_budget_exhaustion_does_not_consume_or_publish(self):
        self.app.context.accept_raw.side_effect=TransportError('unit offline');self.app.advance()
        self.app.recovery_deadline=0
        with self.assertRaisesRegex(ProtocolError,'deadline'):self.app.advance(recovering=True)
        self.assertEqual(self.app.context.accept_raw.call_count,1);self.app.context.publish.assert_not_called()

    def test_ambiguous_publish_is_not_retried_by_input_recovery(self):
        self.app.context.publish.side_effect=TransportError('unit uncertain fanout')
        with self.assertRaises(TransportError):self.app.advance()
        self.assertIsNone(self.app.recovery_deadline);self.assertIsNone(self.app.pending_raw)
        self.assertEqual(self.app.context.accept_raw.call_count,1);self.app.context.publish.assert_called_once()

    def test_recovering_view_clears_guidance_before_reading_CSE(self):
        self.app.state='RECOVERING'
        self.app.context.clients={}
        with self.assertRaises(TransportError):self.app.view('inc-unit','resident')

    def test_recovering_or_degraded_actions_require_explicit_reset(self):
        for state in ['RECOVERING','DEGRADED']:
            self.app.state=state
            with self.assertRaises(RuntimeError):self.app.enqueue('step')
        self.app.enqueue('reset');self.assertEqual(self.app.jobs.get_nowait(),'reset')

    def test_production_loop_automatically_retries_input_and_pauses_after_one_step(self):
        self.app.context.accept_raw.side_effect=[TransportError('unit offline'),None]
        self.app.context.publish.side_effect=self.app.stop.set
        self.app.run(initial_action='step')
        self.assertEqual(self.app.context.accept_raw.call_count,2);self.app.context.publish.assert_called_once()
        self.app.context.close.assert_called_once();self.assertTrue(self.app.paused)
        events=[json.loads(s)['hop'] for s in (self.app.audit_evidence.path/'events.jsonl').read_text().splitlines()]
        self.assertEqual(events,['source_recovery_started','source_recovery_completed'])


if __name__=='__main__':unittest.main()
