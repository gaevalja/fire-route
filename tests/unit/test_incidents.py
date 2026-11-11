"""Offline application tests. Wire fixtures below do not supply real-CSE evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import Mock

from backend.incidents import EventConflict, IncidentStore
from mec.risk.routing import BuildingGraph
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient, ProtocolError, TransportError, WireResponse
from onem2m.decisions import publish_pending
from simulator.events import SensorEvent


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'incident.sqlite3'
        self.graph = BuildingGraph.load(ROOT / 'fixtures/building_3f.json')
        self.store = self.reopen()

    def reopen(self, **kwargs):
        return IncidentStore(self.path, self.graph, 'unit-controller', **kwargs)

    def event(self, *, event_id='event-unit', sequence=1, value=0, node='F2_A', at=NOW):
        return SensorEvent.parse({
            'schema_version': 1, 'event_id': event_id, 'incident_id': 'unit-incident',
            'sensor_id': 'unit-' + node, 'sensor_type': 'synthetic_smoke_index',
            'location_node': node, 'value': value, 'unit': 'unitless_0_100',
            'sequence': sequence, 'timestamp_utc': at.isoformat(),
            'source': 'unit-sensor', 'data_origin': 'SYNTHETIC'}, self.graph.nodes)

    def test_computed_baseline_alternative_and_no_route_versions(self):
        baseline = self.store.accept(self.event(), now=NOW)['route']
        alternative = self.store.accept(self.event(event_id='a-fire', sequence=2, value=90), now=NOW)['route']
        blocked = self.store.accept(self.event(event_id='b-fire', node='F2_B', value=90), now=NOW)['route']
        self.assertEqual((baseline['target_exit'], baseline['routing_cost']), ('EXIT_A', 13))
        self.assertEqual((alternative['target_exit'], alternative['routing_cost']), ('EXIT_B', 16))
        self.assertNotIn('F2_A', alternative['path'])
        self.assertEqual([r['route_version'] for r in [baseline, alternative, blocked]], [1, 2, 3])
        self.assertEqual((blocked['status'], blocked['target_exit'], blocked['path']), ('NO_VERIFIED_ROUTE', None, []))
        self.assertIsNone(blocked['routing_cost'])
        self.assertEqual(len(self.store.pending()), 3)

    def test_duplicate_survives_restart_without_new_version(self):
        event = self.event(value=90)
        self.store.accept(event, now=NOW)
        reopened = self.reopen()
        self.assertEqual(reopened.accept(event, now=NOW + timedelta(days=1))['state'], 'DUPLICATE')
        self.assertEqual(len(reopened.pending()), 1)
        self.assertEqual(reopened.pending()[0]['route']['route_version'], 1)

    def test_event_id_conflicting_payload_is_rejected(self):
        self.store.accept(self.event(), now=NOW)
        with self.assertRaises(EventConflict):
            self.store.accept(self.event(value=90), now=NOW)
        self.assertEqual(len(self.store.pending()), 1)

    def test_older_sequence_and_older_time_cannot_rollback(self):
        self.store.accept(self.event(sequence=10, value=90), now=NOW)
        for event in [self.event(event_id='old-sequence', sequence=9),
                      self.event(event_id='old-time', sequence=11, at=NOW-timedelta(seconds=1))]:
            self.assertEqual(self.store.accept(event, now=NOW)['state'], 'IGNORED_OUTDATED')
        self.assertEqual(len(self.store.pending()), 1)
        self.assertEqual(self.store.pending()[0]['route']['blocked_nodes'], ['F2_A'])

    def test_low_reading_retains_hazard(self):
        self.store.accept(self.event(value=90), now=NOW)
        route = self.store.accept(self.event(event_id='low', sequence=2, value=0), now=NOW)['route']
        self.assertEqual(route['blocked_nodes'], ['F2_A'])
        self.assertEqual(route['target_exit'], 'EXIT_B')

    def test_freshness_rejects_stale_future_without_advancing_sensor(self):
        for event, state in [(self.event(event_id='stale', sequence=100, at=NOW-timedelta(seconds=31)), 'IGNORED_STALE'),
                             (self.event(event_id='future', sequence=101, at=NOW+timedelta(seconds=6)), 'IGNORED_FUTURE')]:
            self.assertEqual(self.store.accept(event, now=NOW)['state'], state)
        self.assertEqual(self.store.pending(), [])
        self.assertEqual(self.store.accept(self.event(), now=NOW)['route']['route_version'], 1)

    def test_sensor_binding_change_rejected(self):
        self.store.accept(self.event(), now=NOW)
        event = replace(self.event(event_id='rebound', sequence=2, node='F2_B'), sensor_id='unit-F2_A')
        with self.assertRaises(EventConflict):
            self.store.accept(event, now=NOW)

    def test_temperature_does_not_invent_a_blocking_threshold(self):
        event = replace(self.event(value=100), sensor_type='temperature_celsius', unit='degC')
        route = self.store.accept(event, now=NOW)['route']
        self.assertEqual(route['blocked_nodes'], [])
        self.assertEqual(route['target_exit'], 'EXIT_A')

    def test_concurrent_duplicates_commit_only_once(self):
        event = self.event()
        with ThreadPoolExecutor(max_workers=8) as pool:
            states = list(pool.map(lambda _: self.store.accept(event, now=NOW)['state'], range(20)))
        self.assertEqual(states.count('ACCEPTED'), 1)
        self.assertEqual(states.count('DUPLICATE'), 19)
        self.assertEqual(len(self.store.pending()), 1)

    def test_policy_change_requires_migration(self):
        self.store.accept(self.event(), now=NOW)
        with self.assertRaises(EventConflict):
            self.reopen(smoke_threshold=80)

    def test_clock_and_time_budget_validation(self):
        with self.assertRaises(ValueError):
            self.store.accept(self.event(), now=NOW.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            self.reopen(sensor_ttl=float('nan'))

    def test_publisher_reconciles_ambiguous_create_after_restart(self):
        self.store.accept(self.event(value=90), now=NOW)
        fixture = WireFixture(ambiguous_route=True)
        client = CSEClient('http://unit.invalid', 'C-unit-controller', '4', transport=fixture)
        containers = {f'controller/{name}': {'path': f'/unit/controller/{name}'} for name in ['hazards', 'routes']}
        with self.assertRaises(TransportError):
            publish_pending(self.store, client, containers)
        self.assertEqual(len(self.reopen().pending()), 1)
        result = publish_pending(self.reopen(), client, containers)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['route']['content']['target_exit'], 'EXIT_B')
        self.assertEqual(fixture.creates, 2)  # One hazard and one route, despite ambiguous response.
        self.assertEqual(self.reopen().pending(), [])
        self.assertEqual(publish_pending(self.reopen(), client, containers), [])

    def test_mismatched_readback_keeps_outbox_pending(self):
        self.store.accept(self.event(), now=NOW)
        client = Mock()
        client.ensure.return_value = {'ri': 'expected'}
        client.resource.return_value = {'ri': 'wrong', 'con': '{}'}
        containers = {'controller/hazards': {'path': '/unit/hazards'}}
        with self.assertRaises(ProtocolError):
            publish_pending(self.store, client, containers)
        self.assertEqual(len(self.reopen().pending()), 1)

    def test_scoped_decision_policies_use_actual_actor_ids(self):
        client = Mock(release='4', originator='unit-admin')
        def ensure(parent, ty, attrs, **kwargs):
            return {**attrs, 'ri': attrs['rn'], 'ty': ty, **({'aei': 'C-' + attrs['rn']} if ty == 2 else {})}
        client.ensure.side_effect = ensure
        result = bootstrap(client, 'unit-base', 'fr_unit', 'http://unit.invalid/onem2m/notify', 86400, decision_policies=True)
        policies = [c.args[2] for c in client.ensure.call_args_list if c.args[1] == 1]
        route_policy = next(p for p in policies if p['rn'].endswith('__routes-policy'))
        hazard_policy = next(p for p in policies if p['rn'].endswith('__hazards-policy'))
        resident = result['actors']['resident']['ae_id']
        self.assertIn(resident, route_policy['pv']['acr'][1]['acor'])
        self.assertNotIn(resident, hazard_policy['pv']['acr'][1]['acor'])
        self.assertEqual(route_policy['pv']['acr'][0]['acop'], 3)


class WireFixture:
    """Unit-only in-memory wire responses; never launched or used by integration."""
    def __init__(self, *, ambiguous_route=False):
        self.data = {}
        self.creates = 0
        self.ambiguous_route = ambiguous_route

    def __call__(self, method, url, headers, body, timeout):
        path = urlsplit(url).path
        if method == 'POST':
            attrs = json.loads(body)['m2m:cin']
            self.creates += 1
            self.data[path + '/' + attrs['rn']] = {**attrs, 'ty': 4, 'ri': f'unit-cin-{self.creates}'}
            if self.ambiguous_route and '/routes' in path:
                self.ambiguous_route = False
                raise TransportError('Unit simulated lost response after committed CREATE')
            status, rsc, content = 201, 2001, {'m2m:cin': self.data[path + '/' + attrs['rn']]}
        elif path in self.data:
            status, rsc, content = 200, 2000, {'m2m:cin': self.data[path]}
        else:
            status, rsc, content = 404, 4004, {}
        return WireResponse(status, {'X-M2M-RI': headers['X-M2M-RI'], 'X-M2M-RVI': '4',
                                     'X-M2M-RSC': str(rsc), 'Content-Type': 'application/json'}, json.dumps(content).encode())
