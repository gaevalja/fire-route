"""Local Git archive/health fixtures; no real MEC or Docker execution."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from infra.mec.healthcheck import NoRedirect, healthy
from infra.mec_local import PreparationBlocked
from infra.mec_runtime import stage_checkout


@unittest.skipUnless(shutil.which('git'), 'Local Git required')
class RuntimeSourceTests(unittest.TestCase):
    def fixture(self, directory):
        root = directory / 'repo';root.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                '-c', 'commit.gpgsign=false', '-c', 'user.name=RuntimeFixture',
                '-c', 'user.email=fixture@example.invalid', *args],cwd=root,
                stderr=subprocess.DEVNULL,text=True).strip()
        git('init', '-b', 'fixture')
        for name in ['LICENSE', 'go-apps/meep-app-enablement/main.go',
                     'go-apps/meep-app-enablement/go.mod', 'go-packages/test/example.go']:
            p = root / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_text('UNIT_FIXTURE\n')
        (root / '.gitignore').write_text('*.private.go\n')
        git('add', '.');git('commit', '-m', 'fixture')
        return root, git('rev-parse', 'HEAD')

    def test_exact_committed_archive_with_parent_directories_and_no_ignored_data(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d);repo,commit = self.fixture(directory)
            (repo / 'go-packages/test/secret.private.go').write_text('PRIVATE_FIXTURE')
            out = directory / 'build/source';before = (repo / 'go-apps/meep-app-enablement/main.go').read_bytes()
            hashes = stage_checkout(repo, out, commit)
            self.assertIn('go-apps/meep-app-enablement/main.go', hashes)
            self.assertFalse(any('secret' in name for name in hashes))
            self.assertFalse((out / '.git').exists());self.assertFalse((out / '.gitignore').exists())
            self.assertEqual((out / 'go-apps/meep-app-enablement/main.go').read_bytes(), before)
            self.assertEqual(stage_checkout(repo, out, commit), hashes)

    def test_staged_modifications_and_extra_files_are_preserved_but_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d);repo,commit = self.fixture(directory);out = directory / 'source'
            stage_checkout(repo, out, commit)
            extra = out / 'go-packages/test/extra.go';extra.write_text('USER_DATA')
            with self.assertRaisesRegex(PreparationBlocked, 'NOT_OVERWRITTEN'):stage_checkout(repo, out, commit)
            self.assertEqual(extra.read_text(), 'USER_DATA')
            extra.unlink();target = out / 'LICENSE';target.write_text('USER_LICENSE')
            with self.assertRaisesRegex(PreparationBlocked, 'NOT_OVERWRITTEN'):stage_checkout(repo, out, commit)
            self.assertEqual(target.read_text(), 'USER_LICENSE')

    def test_symlink_destination_cannot_replace_another_directory(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d);repo,commit = self.fixture(directory);out = directory / 'source'
            out.symlink_to(repo)
            with self.assertRaises(PreparationBlocked):stage_checkout(repo, out, commit)
            self.assertTrue(out.is_symlink())

    def test_traversal_and_symlink_archive_members_fail_before_staging(self):
        for name,kind in [('go-packages/../../escape', tarfile.REGTYPE), ('go-packages/link', tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode='w') as archive:
                    member = tarfile.TarInfo(name);member.type = kind
                    archive.addfile(member)
                with patch('infra.mec_runtime.subprocess.check_output',return_value=stream.getvalue()):
                    with self.assertRaises(PreparationBlocked):stage_checkout(Path(d), Path(d)/'out', 'fixture')
                self.assertFalse((Path(d)/'out').exists())


class RuntimeHealthTests(unittest.TestCase):
    def response(self, body=b'[]', status=200, media='application/json'):
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return body[:limit]
        class Headers:
            def get_content_type(self):return media
        reply = Reply();reply.status=status;reply.headers=Headers()
        return reply

    def test_only_real_200_list_representation_is_healthy(self):
        for body,status,media,expected in [(b'[]',200,'application/json',True),
            (b'{}',200,'application/json',False),(b'[NaN]',200,'application/json',False),
            (b'[]',500,'application/json',False),(b'[]',200,'text/html',False),
            (b'x'*(1024*1024+1),200,'application/json',False)]:
            with self.subTest(status=status,media=media), patch('infra.mec.healthcheck.build_opener') as build:
                build.return_value.open.return_value=self.response(body,status,media)
                self.assertEqual(healthy(),expected)
                self.assertEqual(build.return_value.open.call_args.args[0], 'http://127.0.0.1/mec_service_mgmt/v1/services')

    def test_unavailable_network_and_redirect_do_not_pass(self):
        with patch('infra.mec.healthcheck.build_opener') as build:
            build.return_value.open.side_effect=OSError('FIXTURE_DENIED')
            self.assertFalse(healthy())
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,None,None,'https://fixture.invalid'))
