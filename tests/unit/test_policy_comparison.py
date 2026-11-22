"""Offline contract and execution tests for the 0015 policy comparison."""

from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from mec.interworking.client import verified_result
from mec.interworking.worker import analyse
from mec.risk.evacuation import Navigation
from mec.risk.service import RiskJournal
from onem2m.client import ProtocolError
from simulator.evacuation import Evacuation
from simulator.fire_policy.comparison import (
    Comparison, EXIT, MODEL_ID, WAIT, ZONE_INDEX, action_mask, compare_case, movement_seconds,
)
from simulator.scenario_frames import ZONES
from tests.unit.test_evacuation import frame


@unittest.skipUnless(find_spec('numpy'), 'Install the comparison extra to run policy tests')
class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.navigation = Navigation()
        self.navigation.hazards = {zone: {'fire_index': 0, 'smoke_index': 0, 'collapsed': False}
                                   for zone in ZONES}

    def test_both_policies_share_action_clock_and_single_exit(self):
        case = Comparison('F1-R1')
        self.navigation.hazards['F1-L']['fire_index'] = 41
        with patch('simulator.fire_policy.comparison.ppo_action', side_effect=[ZONE_INDEX['F1-L'], EXIT]):
            self.assertEqual(case.advance(179, self.navigation), {})
            tracks = case.advance(180, self.navigation)
            self.assertTrue(all(d.target == 'F1-L' and d.duration_seconds == 60 for d in tracks.values()))
            self.assertEqual(case.advance(239, self.navigation), {})
            tracks = case.advance(240, self.navigation)
            self.assertTrue(all(d.action_index == EXIT and d.target == 'EXIT' for d in tracks.values()))
            case.advance(300, self.navigation)
        self.assertTrue(all(track.outcome == 'exit' and track.finished_at == 300 for track in case.tracks.values()))

    def test_no_route_counts_as_room_rescue(self):
        case = Comparison('F7-R3')
        self.navigation.hazards['F7-C3']['fire_index'] = 55
        self.navigation.hazards['F7-R3']['fire_index'] = 50
        with patch('simulator.fire_policy.comparison.ppo_action', return_value=WAIT):
            for second in range(180, 1380, 30):
                case.advance(second, self.navigation)
            self.assertEqual(case.tracks['dijkstra'].snapshot()['status'], 'NO_ROUTE')
            case.advance(1380, self.navigation)
        self.assertTrue(all(track.outcome == 'room' for track in case.tracks.values()))

    def test_collapse_has_priority_over_room_rescue(self):
        case = Comparison('F7-R3')
        self.navigation.hazards['F7-C3']['fire_index'] = 55
        with patch('simulator.fire_policy.comparison.ppo_action', return_value=WAIT):
            case.advance(1350, self.navigation)
            self.navigation.hazards['F7-R3']['collapsed'] = True
            case.advance(1380, self.navigation)
        self.assertTrue(all(track.outcome == 'death' and track.reason == 'collapse'
                            for track in case.tracks.values()))

    def test_no_route_reconsiders_on_next_action(self):
        case = Comparison('F7-R3')
        self.navigation.hazards['F7-C3']['smoke_index'] = 70
        with patch('simulator.fire_policy.comparison.ppo_action', return_value=WAIT):
            self.assertFalse(case.advance(180, self.navigation)['dijkstra'].route_available)
            self.navigation.hazards['F7-C3']['smoke_index'] = 0
            self.assertEqual(case.advance(200, self.navigation), {})
            self.assertEqual(case.advance(210, self.navigation)['dijkstra'].target, 'F7-C3')

    def test_action_mask_preserves_elevator_and_rejects_collapsed_neighbors(self):
        hazards = self.navigation.hazards
        hazards['F1-R2']['collapsed'] = True
        self.assertTrue(action_mask('F1-L', hazards)[ZONE_INDEX['F1-E']])
        self.assertFalse(action_mask('F1-L', hazards)[ZONE_INDEX['F1-R2']])
        self.assertFalse(action_mask('F1-R1', hazards)[EXIT])
        hazards['F1-L'].update(fire_index=40, smoke_index=65)
        self.assertEqual(movement_seconds(EXIT, 'F1-L', 'EXIT', hazards), 30)

    def test_paired_playback_uses_batch_decisions_at_exact_simulation_seconds(self):
        options = {'ignition_room': 'F1-R2'}
        playback = compare_case(2026, 5, 'F9-R3', include_frames=True, **options)
        batch = compare_case(2026, 5, 'F9-R3', **options)
        self.assertEqual(playback['policies'], batch['policies'])
        self.assertEqual(playback['ignition_room'], 'F1-R2')
        frames = {frame['second']: frame for frame in playback['frames']}
        self.assertEqual(len(frames), len(playback['frames']))
        self.assertEqual(list(frames), sorted(frames))
        self.assertEqual(set(frames[0]['zones']), set(ZONES))
        self.assertGreater(frames[0]['zones']['F1-R2']['fire'], 0)
        self.assertTrue(all(track['position'] == 'F9-R3' and track['decision'] is None
                            for track in frames[0]['policies'].values()))
        for key, track in playback['policies'].items():
            self.assertEqual(track['decisions'][0]['second'], playback['rules']['awareness_seconds'])
            for decision in track['decisions']:
                self.assertEqual(frames[decision['second']]['policies'][key]['decision'], decision)
            terminal = frames[track['finished_at']]['policies'][key]
            self.assertEqual(terminal['outcome'], track['outcome'])
            self.assertEqual(terminal['position'], track['position'])
        self.assertEqual(playback['policies']['dijkstra']['outcome'], 'death')
        self.assertEqual(playback['policies']['ppo']['outcome'], 'exit')
        self.assertEqual(frames[661]['policies']['ppo'], frames[600]['policies']['ppo'])

    def test_journal_replay_and_mec_response_keep_comparison_and_population(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'risk.sqlite3'
            journal = RiskJournal(path, compare=True)
            local = Evacuation(compare=True)
            legacy = Evacuation()
            original = frame(0)
            self.assertEqual(journal.apply(original.to_dict())['comparison']['model_id'], MODEL_ID)
            for model in (local, legacy):
                model.accept(original)
            latest = frame(1)
            for model in (local, legacy):
                model.accept(latest)
            raw = latest.to_dict()
            actual = RiskJournal(path, compare=True).apply(raw)
            expected = local.snapshot()
            self.assertEqual(actual, expected)
            expected_without_comparison = {k: v for k, v in expected.items() if k != 'comparison'}
            self.assertEqual(legacy.snapshot(), expected_without_comparison)
            self.assertEqual(expected['population']['total'], 170)
            provider = Mock()
            provider.call.return_value = {'state': 'ACCEPTED', 'result': actual}
            with patch('mec.interworking.worker.discover_risk', return_value={'serInstanceId': 'service'}):
                remote = analyse({'frame': raw, 'event_id': 'request'}, Mock(), provider,
                                 {'service_id': 'service', 'app_id': 'app'})
            self.assertEqual(verified_result(remote, raw, expected), expected)
            remote['analysis']['comparison'] = None
            with self.assertRaises(ProtocolError):
                verified_result(remote, raw, expected)
