"""Synthetic package fixtures; no installed CSE or actual lifecycle proof."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from infra.cse import runtime_audit


class RuntimeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.names=['acmecse/runtime/CSE.py','acmecse/plugins/database/TinyDB.py',
            'acmecse/__main__.py','acmecse/unrelated.py','acmecse/runtime.ini','other/CSE.py']
        for name in self.names:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('raise RuntimeError("private-fixture-value")\n')
        self.package=SimpleNamespace(version='synthetic-unit',files=self.names,
            locate_file=lambda name:self.root/str(name))

    def snapshot(self):
        with patch('importlib.metadata.distribution',return_value=self.package):
            return runtime_audit.snapshot_sources()

    def test_reads_only_selected_package_source_and_never_imports_CSE(self):
        result=self.snapshot()
        self.assertEqual({r['path'] for r in result['files']},set(self.names[:3]))
        self.assertNotIn('private-fixture-value',json.dumps(result))
        self.assertEqual(result['runtime_config_env_DB'],'NOT_READ')

    def test_preserves_shutdown_structure_and_redacts_literals_including_fstrings(self):
        source='''import signal
def shutdown():
    "private-fixture-value"
    print(f"private-fixture-value {2}")
    signal.raise_signal(signal.SIGINT)
    return b"private-fixture-value"
'''
        (self.root/self.names[0]).write_text(source)
        text=next(r['sanitized_source'] for r in self.snapshot()['files'] if r['path']==self.names[0])
        self.assertIn('def shutdown()',text)
        self.assertIn('signal.raise_signal(signal.SIGINT)',text)
        self.assertNotIn('private-fixture-value',text)
        compile(text,'sanitized-fixture','exec')

    def test_source_symlink_escape_is_rejected(self):
        target=self.root/self.names[0];target.unlink()
        external=self.root/'external.py';external.write_text('pass')
        target.symlink_to(external)
        with self.assertRaises(ValueError):self.snapshot()

    def test_empty_or_oversized_package_source_is_rejected(self):
        self.package.files=[]
        with self.assertRaises(ValueError):self.snapshot()
        self.package.files=self.names
        (self.root/self.names[0]).write_text('#'*(256*1024+1))
        with self.assertRaises(ValueError):self.snapshot()

    def test_Docker_denial_is_blocked_without_exec_or_secret_output(self):
        out=Mock();out.path=Path('evidence/synthetic-only')
        with patch.object(runtime_audit,'Evidence',return_value=out), \
                patch.object(runtime_audit,'source_identity',return_value={}), \
                patch.object(runtime_audit,'command',return_value=''), \
                patch.object(runtime_audit.subprocess,'run') as run,redirect_stdout(io.StringIO()):
            self.assertEqual(runtime_audit.main(),2)
        run.assert_not_called()
        summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
        self.assertEqual(summary['state'],'BLOCKED')
        self.assertEqual(summary['CSE_lifecycle'],'NOT_CHANGED')

    def test_source_collection_uses_stdin_and_has_no_lifecycle_mutation(self):
        out=Mock();out.path=Path('evidence/synthetic-only')
        data={'installed_version':'synthetic-unit','files':[{'path':'acmecse/runtime/CSE.py',
            'sanitized_source':'def shutdown():\n    pass'}]}
        result=SimpleNamespace(returncode=0,stdout=json.dumps(data),stderr='')
        with patch.object(runtime_audit,'Evidence',return_value=out), \
                patch.object(runtime_audit,'source_identity',return_value={}), \
                patch.object(runtime_audit,'command',return_value='a'*64) as command, \
                patch.object(runtime_audit.subprocess,'run',return_value=result) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(runtime_audit.main(),0)
        command.assert_called_once_with(['docker','compose','ps','--quiet','cse'])
        self.assertEqual(run.call_args.args[0],['docker','exec','-i','a'*64,'python','-'])
        compile(run.call_args.kwargs['input'],'stdin-audit-script','exec')
        summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
        self.assertEqual(summary['scope'],'SOURCE_COLLECTION_ONLY_NOT_LIFECYCLE_PASS')
        self.assertEqual(summary['CSE_lifecycle'],'NOT_CHANGED')

    def test_failed_exec_never_echoes_container_output(self):
        out=Mock();out.path=Path('evidence/synthetic-only');stream=io.StringIO()
        result=SimpleNamespace(returncode=1,stdout='private-fixture-value',stderr='private-fixture-value')
        with patch.object(runtime_audit,'Evidence',return_value=out), \
                patch.object(runtime_audit,'source_identity',return_value={}), \
                patch.object(runtime_audit,'command',return_value='a'*64), \
                patch.object(runtime_audit.subprocess,'run',return_value=result),redirect_stdout(stream):
            self.assertEqual(runtime_audit.main(),2)
        self.assertNotIn('private-fixture-value',stream.getvalue())
        self.assertNotIn('private-fixture-value',str(out.write.call_args_list))


if __name__=='__main__':unittest.main()
