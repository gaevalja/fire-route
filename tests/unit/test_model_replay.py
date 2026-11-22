"""Loopback HTTP tests with real auth and replay assets, without a live incident."""

from http.client import HTTPConnection
from importlib.util import find_spec
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import Mock

from backend.auth import AuthStore, digest
from backend.http_api import api_server
from backend.model_replay import COMPARE_PATH, MAKER_PREFIX, REPLAY_PAGE, REPLAY_PREFIX, ModelReplay


STATIC_ROOT = Path(__file__).resolve().parents[2] / 'frontend/scenario'
TRAINING_RUN = 'FIRE_EVAC_0016'


class ModelReplayHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runs = Path(temporary.name)
        self.training = self.runs / TRAINING_RUN
        self.training.mkdir()
        self.manifest('training')

        auth = AuthStore({role: digest(f'unit-{role}') for role in ('resident', 'responder')})
        self.tokens = {role: auth.login(role, f'unit-{role}', 'unit-peer')[0]
                       for role in ('resident', 'responder')}
        # The handler normally receives the advertised host from Compose.
        self.origin = 'http://127.0.0.1:3001'
        self.app = Mock()
        server = api_server('127.0.0.1', 0, self.app, auth, self.origin, STATIC_ROOT,
                            model_replay=ModelReplay(STATIC_ROOT, self.runs))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.client = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        self.addCleanup(self.client.close)

    def manifest(self, status):
        (self.training / 'manifest.json').write_text(json.dumps({'status': status}), encoding='utf-8')

    def request(self, method, path, role, body=None):
        headers = {'Host': self.origin.removeprefix('http://')}
        if role:
            headers['Cookie'] = f'fr_session={self.tokens[role]}'
        if body is not None:
            headers.update(Origin=self.origin, **{'Content-Type': 'application/json'})
            body = json.dumps(body).encode()
        self.client.request(method, path, body=body, headers=headers)
        response = self.client.getresponse()
        return response.status, response.headers, response.read()

    def get(self, path, role='responder'):
        return self.request('GET', path, role)

    def test_replay_is_same_origin_and_responder_only(self):
        for path in (REPLAY_PAGE, REPLAY_PREFIX + 'runs', MAKER_PREFIX + 'engine.js',
                     REPLAY_PREFIX + 'runs/FIRE_EVAC_0015/browser_policy.json'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, None)[0], 401)
                self.assertEqual(self.get(path, 'resident')[0], 403)
                self.assertEqual(self.get(path)[0], 200)
        self.assertIn("frame-ancestors 'none'", self.get('/')[1]['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'self'", self.get(REPLAY_PAGE)[1]['Content-Security-Policy'])
        self.app.status.assert_not_called()
        self.app.enqueue.assert_not_called()

    def test_training_metrics_and_model_completion_are_visible_on_refresh(self):
        def catalog():
            status, _, body = self.get(REPLAY_PREFIX + 'runs')
            self.assertEqual(status, 200)
            return {record['id']: record for record in json.loads(body)['runs']}

        runs = catalog()
        self.assertTrue(runs['FIRE_EVAC_0015']['has_model'])
        self.assertEqual(runs[TRAINING_RUN]['status'], 'training')
        self.assertFalse(runs[TRAINING_RUN]['has_model'])
        folder = REPLAY_PREFIX + 'runs/' + TRAINING_RUN + '/'
        self.assertEqual(self.get(folder + 'browser_policy.json')[0], 404)
        csv = 'time/total_timesteps,train/loss\n256,0.5\n'
        (self.training / 'progress.csv').write_bytes(csv.encode())
        self.assertEqual(self.get(folder + 'progress.csv')[2], csv.encode())
        self.assertEqual(self.get(REPLAY_PREFIX + 'runs/FIRE_EVAC_0015/eval_progress.csv')[0], 200)
        (self.training / 'browser_policy.json').write_text('{}', encoding='utf-8')
        self.manifest('complete')
        self.assertTrue(catalog()[TRAINING_RUN]['has_model'])
        self.assertEqual(self.get(folder + 'browser_policy.json')[2], b'{}')

    def test_only_review_files_are_served(self):
        folder = REPLAY_PREFIX + 'runs/FIRE_EVAC_0015/'
        for path in (folder + 'model.zip', folder + 'manifest.json', folder + 'source_snapshot/config.js',
                     folder + '%2e%2e/browser_policy.json', MAKER_PREFIX + 'manifest.json'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_paired_endpoint_rejects_unapproved_roles_and_scenario_values(self):
        settings = {'seed': 2026, 'wind': 5}
        self.assertEqual(self.request('POST', COMPARE_PATH, None, settings)[0], 401)
        self.assertEqual(self.request('POST', COMPARE_PATH, 'resident', settings)[0], 403)
        for extra in ({'seed': True}, {'wind': 2}, {'ignition_room': 'F7-C1'}, {'start_room': ['F7-R3']},
                      {'start_room': None}, {'model': 'FIRE_EVAC_0001'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request('POST', COMPARE_PATH, 'responder', settings | extra)[0], 400)
        self.app.enqueue.assert_not_called()

    @unittest.skipUnless(find_spec('numpy'), 'Install the comparison extra to run policy tests')
    def test_paired_endpoint_returns_one_timeline_without_enqueuing_live_action(self):
        inputs = {'seed': 59, 'wind': 5, 'ignition_room': 'F3-R2', 'start_room': 'F7-R3'}
        status, _, body = self.request('POST', COMPARE_PATH, 'responder', inputs)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['model_id'], 'FIRE_EVAC_0015')
        self.assertEqual(result['start_room'], 'F7-R3')
        self.assertEqual(result['ignition_room'], 'F3-R2')
        self.assertEqual(set(result['frames'][0]['policies']), {'dijkstra', 'ppo'})
        self.assertEqual(result['frames'][-1]['second'], 540)
        self.app.status.assert_not_called()
        self.app.enqueue.assert_not_called()
