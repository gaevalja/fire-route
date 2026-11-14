"""Synthetic lifecycle fixtures for the pinned adapter; no real CSE evidence."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from infra.cse import patch_shutdown as adapter


# Reproduce only the observed guard/close path; this is no CSE or REST server.
FIXTURE='''# UTF-8 offset regression: 종료
@atexit.register
def _shutdown():
    """Synthetic unit lifecycle."""
    if RC.cseStatus not in [CSEStatus.RUNNING, CSEStatus.SHUTTINGDOWNRESTART]:
        return
    storage.shutdown()
    RC.cseStatus = CSEStatus.STOPPED
'''.encode()


class ShutdownAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/adapter.SOURCE;self.path.parent.mkdir(parents=True)
        self.path.write_bytes(FIXTURE);self.path.chmod(0o644)
        self.sha=hashlib.sha256(FIXTURE).hexdigest()
        self.manifest=self.root/'patch.json'
        self.package=SimpleNamespace(version=adapter.VERSION,locate_file=lambda name:self.root/str(name))

    def patched(self,body=FIXTURE):
        with patch.object(adapter,'SOURCE_SHA256',self.sha):return adapter.patch_source(body)

    def execute(self,body,state):
        states=SimpleNamespace(RUNNING='RUNNING',SHUTTINGDOWN='SHUTTINGDOWN',
            SHUTTINGDOWNRESTART='RESTART',STOPPED='STOPPED')
        rc=SimpleNamespace(cseStatus=state);store=Mock()
        namespace={'atexit':SimpleNamespace(register=lambda fn:fn),
            'RC':rc,'CSEStatus':states,'storage':store}
        exec(compile(body,'synthetic-unit-lifecycle','exec'),namespace)
        namespace['_shutdown']();namespace['_shutdown']()
        return rc,store

    def test_requested_shutdown_flushes_once_and_stops_after_guard_correction(self):
        before,store=self.execute(FIXTURE,'SHUTTINGDOWN')
        store.shutdown.assert_not_called();self.assertEqual(before.cseStatus,'SHUTTINGDOWN')
        after,store=self.execute(self.patched(),'SHUTTINGDOWN')
        store.shutdown.assert_called_once();self.assertEqual(after.cseStatus,'STOPPED')

    def test_running_restart_and_nonstarted_cases_keep_their_existing_behavior(self):
        for state in ['RUNNING','RESTART','STOPPED','STARTING']:
            with self.subTest(state=state):
                old,old_store=self.execute(FIXTURE,state)
                new,new_store=self.execute(self.patched(),state)
                self.assertEqual(old.cseStatus,new.cseStatus)
                self.assertEqual(old_store.shutdown.call_count,new_store.shutdown.call_count)

    def test_changes_only_one_list_insertion_and_retains_upstream_bytes(self):
        result=self.patched();insertion=b'CSEStatus.SHUTTINGDOWN, '
        self.assertEqual(result.count(insertion),1)
        self.assertEqual(result.replace(insertion,b'',1),FIXTURE)
        self.assertTrue(result.startswith('# UTF-8 offset regression: 종료'.encode()))

    def test_unknown_source_hash_and_unexpected_structure_fail_closed(self):
        with self.assertRaises(ValueError):adapter.patch_source(FIXTURE)
        for changed in [FIXTURE.replace(b'not in',b'in'),
                        FIXTURE.replace(b'atexit.register',b'other.register')]:
            with patch.object(adapter,'SOURCE_SHA256',hashlib.sha256(changed).hexdigest()):
                with self.assertRaises(ValueError):adapter.patch_source(changed)
        with self.assertRaises(ValueError):self.patched(FIXTURE+b'\n')

    def test_other_version_or_source_path_escape_is_rejected(self):
        self.package.version='synthetic-other'
        with patch.object(adapter,'distribution',return_value=self.package):
            with self.assertRaises(ValueError):adapter.installed_source()
            self.package.version=adapter.VERSION
            external=self.root/'external.py';external.write_bytes(FIXTURE)
            self.path.unlink();self.path.symlink_to(external)
            with self.assertRaises(ValueError):adapter.installed_source()

    def apply(self):
        with patch.object(adapter,'distribution',return_value=self.package), \
                patch.object(adapter,'SOURCE_SHA256',self.sha),patch.object(adapter,'MANIFEST',self.manifest), \
                redirect_stdout(io.StringIO()):return adapter.main()

    def verify(self):
        with patch.object(adapter,'distribution',return_value=self.package), \
                patch.object(adapter,'SOURCE_SHA256',self.sha):
            return adapter.verify_installed_patch(self.manifest)

    def test_image_apply_and_startup_verification_retain_file_permissions(self):
        self.assertEqual(self.apply(),0)
        self.assertEqual(self.path.stat().st_mode&0o777,0o644)
        info=self.verify()
        self.assertTrue(info['verified']);self.assertEqual(info['upstream_sha256'],self.sha)
        self.assertEqual(info['patched_sha256'],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(info['patch_id'],adapter.PATCH_ID)

    def test_changing_manifest_to_authorize_unrelated_source_is_refused(self):
        self.assertEqual(self.apply(),0)
        self.path.write_bytes(self.path.read_bytes()+b'\n# unrelated change\n')
        with self.assertRaises(ValueError):self.verify()
        info=json.loads(self.manifest.read_text());info['patched_sha256']=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(info))
        with self.assertRaises(ValueError):self.verify()

    def test_failed_apply_never_overwrites_unknown_source_or_prints_exception_body(self):
        original=FIXTURE+b'# changed\n';self.path.write_bytes(original)
        self.assertEqual(self.apply(),1)
        self.assertEqual(self.path.read_bytes(),original);self.assertFalse(self.manifest.exists())
        stream=io.StringIO()
        with patch.object(adapter,'installed_source',side_effect=ValueError('private-fixture-value')),redirect_stdout(stream):
            self.assertEqual(adapter.main(),1)
        self.assertNotIn('private-fixture-value',stream.getvalue())


if __name__=='__main__':unittest.main()
