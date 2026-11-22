"""Local Git/config/SQLite and explicit CSE fixtures; no actual MEC evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend.notifications import NotificationService, NotificationStore
from backend.p0 import IntegrationBlocked
from infra.mec_local import (BRANCH, REPOSITORIES, PreparationBlocked, audit_repository,
                             git, prepare, run as source_run)
from mec.local_integration import catalog_decoder, configuration, local_url, provision, run


def catalog():
    return {'schema_version': 1, 'event_id': 'mec-' + 'a' * 32,
            'MEC_API': 'MEC011_SERVICE_DISCOVERY', 'MEC_environment': 'local-sandbox',
            'consumption_path': 'APPLICATION_AE_BRIDGE_NOT_MEC_IPE',
            'MEC_IPE': 'NOT_IMPLEMENTED', 'service_count': 0, 'services': []}


@unittest.skipUnless(shutil.which('git'), 'Git required for real local source-lock tests')
class SourceTests(unittest.TestCase):
    def fixture(self, path, name):
        path.mkdir(parents=True)
        def command(*args):
            return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                '-c', 'user.name=SourceFixture', '-c', 'user.email=fixture@example.invalid', *args],
                cwd=path, stderr=subprocess.DEVNULL, text=True)
        command('init', '-b', BRANCH)
        (path / 'README.md').write_text('UNIT_FIXTURE_NOT_OFFICIAL_SOURCE\n')
        (path / 'deploy').mkdir()
        (path / 'deploy/site.yml').write_text('# UNIT_FIXTURE_DO_NOT_EXECUTE\n')
        command('add', 'README.md', 'deploy/site.yml')
        command('commit', '-m', 'fixture')
        command('remote', 'add', 'origin', REPOSITORIES[name])
        command('update-ref', 'refs/remotes/origin/' + BRANCH, 'HEAD')
        return command

    def test_actual_local_git_hashes_and_reuse_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            locked = {'schema_version': 1, 'repositories': {}}
            for name in REPOSITORIES:
                path = root / 'sources' / name
                self.fixture(path, name)
                record = audit_repository(path, name)
                self.assertEqual(len(record['commit']), 40)
                self.assertIn('deploy/site.yml', record['review_files'])
                locked['repositories'][name] = record
            lock = root / 'sources.lock.json'
            lock.write_text(json.dumps(locked))
            original = lock.read_bytes()
            with patch('infra.mec_local.git', wraps=git) as call:
                self.assertEqual(prepare(root), locked)
                self.assertEqual(prepare(root, inspect_only=True), locked)
                self.assertTrue(all('clone' not in c.args and 'fetch' not in c.args for c in call.call_args_list))
            self.assertEqual(lock.read_bytes(), original)

    def test_edited_source_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'repo';self.fixture(path, 'etsi-mec-sandbox')
            (path / 'deploy/site.yml').write_text('USER_WORK\n')
            with self.assertRaisesRegex(PreparationBlocked, 'LOCAL_CHANGES'):
                audit_repository(path, 'etsi-mec-sandbox')
            self.assertEqual((path / 'deploy/site.yml').read_text(), 'USER_WORK\n')

    def test_remote_branch_and_locked_hash_mismatches_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'repo';command = self.fixture(path, 'etsi-mec-sandbox')
            original = audit_repository(path, 'etsi-mec-sandbox')
            with self.assertRaisesRegex(PreparationBlocked, 'LOCKED_SOURCE_CHANGED'):
                audit_repository(path, 'etsi-mec-sandbox', {**original, 'tree': '0' * 40})
            command('update-ref', '-d', 'refs/remotes/origin/' + BRANCH)
            with self.assertRaises(PreparationBlocked):audit_repository(path, 'etsi-mec-sandbox')
            command('update-ref', 'refs/remotes/origin/' + BRANCH, 'HEAD')
            command('remote', 'set-url', 'origin', 'https://fixture.invalid/repo.git')
            with self.assertRaisesRegex(PreparationBlocked, 'REMOTE_MISMATCH'):
                audit_repository(path, 'etsi-mec-sandbox')

    def test_inspection_missing_sources_does_not_create_or_download(self):
        with tempfile.TemporaryDirectory() as d, patch('infra.mec_local.git') as call:
            path = Path(d) / 'missing'
            with self.assertRaises(PreparationBlocked):prepare(path, inspect_only=True)
            self.assertFalse(path.exists());call.assert_not_called()

    def test_unowned_checkout_not_replaced(self):
        with tempfile.TemporaryDirectory() as d, patch('infra.mec_local.git') as call:
            root = Path(d);target = root / 'sources/etsi-mec-sandbox';target.mkdir(parents=True)
            (target / 'user.txt').write_text('keep')
            with self.assertRaisesRegex(PreparationBlocked, 'UNOWNED'):
                prepare(root)
            self.assertEqual((target / 'user.txt').read_text(), 'keep');call.assert_not_called()

    def test_invalid_lock_and_source_symlinks_block_without_network(self):
        with tempfile.TemporaryDirectory() as d, patch('infra.mec_local.git') as call:
            root = Path(d)
            for value in ['[]', '{"schema_version":1,"repositories":{"etsi-mec-sandbox":null}}']:
                (root / 'sources.lock.json').write_text(value)
                with self.assertRaises(PreparationBlocked):prepare(root)
            (root / 'sources.lock.json').unlink()
            (root / 'sources').symlink_to(root)
            with self.assertRaises(PreparationBlocked):prepare(root)
            call.assert_not_called()

    def test_download_failure_retains_blocked_status_not_platform_success(self):
        with tempfile.TemporaryDirectory() as d, patch('infra.mec_local.git', side_effect=PreparationBlocked('ETSI_DNS_UNAVAILABLE')):
            root = Path(d)
            result, evidence = source_run(root / 'sources', evidence_root=root / 'evidence')
            self.assertEqual(result['state'], 'BLOCKED')
            self.assertEqual(result['Hosted'], 'NOT_CONTACTED')
            self.assertEqual(result['source_scripts'], 'NOT_EXECUTED')
            self.assertTrue((evidence / 'summary.json').exists())

    def test_git_failure_does_not_echo_helper_credentials(self):
        response = subprocess.CompletedProcess([], 128, '', 'Could not resolve host with FIXTURE_SECRET')
        with patch('infra.mec_local.subprocess.run', return_value=response):
            with self.assertRaises(PreparationBlocked) as caught:git(Path('.'), 'version')
        self.assertEqual(str(caught.exception), 'ETSI_DNS_UNAVAILABLE')
        self.assertNotIn('FIXTURE_SECRET', str(caught.exception))


class LocalConfigurationTests(unittest.TestCase):
    def test_only_explicit_private_hosts_are_accepted(self):
        for host in ['localhost', '127.0.0.1', '[::1]', '192.168.1.2', '172.20.0.2', '10.1.2.3', '[fd00::2]', 'host.docker.internal']:
            value = 'http://' + host + ':8080/mec_service_mgmt/v1'
            self.assertEqual(local_url(value, 'fixture'), value)
        for host in ['82.112.253.59', '169.254.169.254', '0.0.0.0', '[::]', 'example.com', '192.0.2.1']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                local_url('http://' + host + '/mec_service_mgmt/v1', 'fixture')

    def test_missing_config_blocks_without_any_MEC_or_CSE_request(self):
        with tempfile.TemporaryDirectory() as d, patch('mec.local_integration.discover') as mec, patch('mec.local_integration.CSEClient') as cse:
            result, evidence = run({'EVIDENCE_ROOT': d})
            self.assertEqual(result['state'], 'BLOCKED');self.assertEqual(result['checks'], 0)
            self.assertEqual(result['MEC'], 'NOT_CONTACTED');self.assertEqual(result['CSE'], 'NOT_CONTACTED')
            mec.assert_not_called();cse.assert_not_called()
            self.assertEqual(json.loads((evidence / 'checks.json').read_text()), {})

    def test_public_MEC_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as d, patch('mec.local_integration.discover') as call:
            result, _ = run({'EVIDENCE_ROOT': d, 'MEC_LOCAL_SERVICE_MGMT_URL': 'http://82.112.253.59/mec_service_mgmt/v1'})
            self.assertEqual(result['state'], 'FAIL');self.assertEqual(result['Hosted'], 'NOT_CONTACTED')
            call.assert_not_called()

    def test_container_loopback_and_unsupported_auth_fail_explicitly(self):
        valid = {'MEC_LOCAL_SERVICE_MGMT_URL': 'http://host.docker.internal:8080/mec_service_mgmt/v1'}
        self.assertEqual(configuration({**valid, 'MEC_IN_COMPOSE': '1'})[0].environment, 'local-sandbox')
        for host in ['localhost', '127.0.0.1', '127.0.0.2', '[::1]', '[0:0:0:0:0:0:0:1]']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                configuration({**valid, 'MEC_LOCAL_SERVICE_MGMT_URL': 'http://' + host + ':8080/mec_service_mgmt/v1', 'MEC_IN_COMPOSE': '1'})
        for name in ['MEC_API_TOKEN_FILE', 'MEC_CA_FILE', 'CSE_CLIENT_CERT', 'CSE_CLIENT_KEY', 'CSE_CA_FILE']:
            with self.subTest(name=name), self.assertRaises(ValueError):configuration({**valid, name: '/private/fixture'})

    def test_invalid_CSE_callback_base_and_instance_fail_before_connect(self):
        valid = {'MEC_LOCAL_SERVICE_MGMT_URL': 'http://host.docker.internal:8080/mec_service_mgmt/v1'}
        for override in [{'MEC_LOCAL_CSE_URL': 'http://public.invalid'}, {'MEC_LOCAL_CALLBACK_URL': 'http://82.112.253.59'}, {'MEC_LOCAL_CSE_BASE': '../other'}, {'MEC_APPLICATION_INSTANCE_ID': '../invented'}]:
            with self.subTest(override=override), self.assertRaises(ValueError):configuration({**valid, **override})


class CatalogConsumerTests(unittest.TestCase):
    def test_decoder_rejects_other_event_and_content_without_rewriting_it(self):
        expected = catalog();decode = catalog_decoder(expected)
        self.assertEqual(decode(dict(expected)).to_dict(), expected)
        for value in [[], {**expected, 'service_count': 1}, {**expected, 'event_id': 'wrong'}]:
            with self.assertRaises(ValueError):decode(value)

    def test_catalog_callback_persists_exact_CIN_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            expected = catalog();store = NotificationStore(Path(d) / 'fixture.sqlite3')
            service = NotificationService(store, '/fixture-cse', '4', frozenset(), decoder=catalog_decoder(expected))
            service.approve({'/fixture-cse/sub'})
            headers = {'X-M2M-RI': 'fixture-rqi', 'X-M2M-Origin': '/fixture-cse', 'Content-Type': 'application/json'}
            body = {'m2m:sgn': {'sur': '/fixture-cse/sub', 'nev': {'net': 3, 'rep': {'m2m:cin': {'ty': 4, 'ri': 'fixture-cin', 'con': json.dumps(expected)}}}}}
            raw = json.dumps(body).encode()
            self.assertEqual(service.handle(headers, raw).kind, 'event')
            self.assertEqual(service.handle(headers, raw).kind, 'duplicate')
            rows = store.find(expected['event_id'])
            self.assertEqual(len(rows), 1);self.assertEqual(rows[0]['event'], expected)
            self.assertEqual(rows[0]['cin_ri'], 'fixture-cin')

    def test_provision_uses_returned_AE_IDs_and_restricts_reader_to_SUB_creation(self):
        class CSEFixture:
            originator = 'FIXTURE_ADMIN';release = '4'
            def __init__(self):self.calls = []
            def for_actor(self, identity, actor):
                self.calls.append(('actor', identity, actor));return self
            def ensure(self, parent, ty, attrs, **kwargs):
                self.calls.append(('ensure', parent, ty, attrs))
                return {'ri': 'fixture-' + attrs['rn'], 'aei': 'returned-' + attrs['rn']}
        fixture = CSEFixture();resources = provision(fixture, 'fixture', 'http://fixture.invalid/notify')
        rule = next(c[3]['pv']['acr'] for c in fixture.calls if c[0] == 'ensure' and c[2] == 1)
        bridge, reader = (resources['actors'][role]['ae_id'] for role in ('bridge', 'reader'))
        self.assertIn({'acor': [bridge], 'acop': 3}, rule)
        self.assertIn({'acor': [reader], 'acop': 2}, rule)
        self.assertIn({'acor': [reader], 'acop': 1, 'acod': [{'ty': 3, 'chty': [23]}]}, rule)
        self.assertFalse(any(r['acor'] == [reader] and r['acop'] == 3 for r in rule))
        self.assertTrue(resources['container'].endswith('/catalog'))
