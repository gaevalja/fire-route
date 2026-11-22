"""Host/control failure fixtures; no real Docker or CSE success evidence."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from infra import cse_recovery
from infra.cse.diagnostics import DockerUnavailable
from tests.integration import selected_recovery


class RecoveryControlTests(unittest.TestCase):
    def test_atomic_control_is_bound_to_host_run_and_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            selected_recovery.signal(path,'unit-run','stopped',observation={'unit':True})
            self.assertFalse(list(path.glob('*.tmp')))
            self.assertEqual(selected_recovery.wait_signal(path,'unit-run','stopped',1)['observation'],{'unit':True})
            with self.assertRaises(AssertionError):selected_recovery.wait_signal(path,'wrong-run','stopped',1)
            with self.assertRaises(AssertionError):selected_recovery.wait_signal(path,'unit-run','absent',0)

    def test_child_exit_is_not_silently_waited_or_treated_as_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(cse_recovery,'runner_state',return_value={'Running':False}):
                with self.assertRaisesRegex(AssertionError,'exited'):
                    cse_recovery.await_phase(Path(directory),'unit-run','ready','a'*64,10)

    def test_container_identity_validation_and_safe_inspect_projection(self):
        run=Mock(return_value=json.dumps({'Running':False,'ExitCode':1,'OOMKilled':False,'Error':'unit-sensitive-detail'}))
        with self.assertRaises(AssertionError):cse_recovery.runner_state('unit-invalid-id',run)
        run.assert_not_called()
        self.assertEqual(cse_recovery.runner_state('a'*64,run),{'Running':False,'ExitCode':1,'OOMKilled':False})

    def test_agent_Docker_denial_is_BLOCKED_before_any_stop_or_start(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Mock();out.path=Path(directory)/'unit-out';out.path.mkdir()
            with patch.object(cse_recovery,'Evidence',return_value=out), \
                    patch.object(cse_recovery,'print',create=True), \
                    patch.object(cse_recovery,'source_identity',return_value={}), \
                    patch.object(cse_recovery,'command',side_effect=DockerUnavailable()) as command:
                self.assertEqual(cse_recovery.main(),2)
            self.assertEqual(command.call_count,1)
            summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
            self.assertEqual(summary['state'],'BLOCKED');self.assertEqual(summary['Hosted'],'NOT_CONTACTED')

    def test_failed_shutdown_requests_same_CSE_restart_and_preserves_FAIL(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Mock();out.path=Path(directory)/'unit-out';out.path.mkdir()
            cid='a'*64;commands=[]
            def command(args,**kwargs):
                commands.append(args)
                if args[:3]==['docker','compose','ps']:return cid
                if 'scenario-recovery' in args and '--detach' in args:return 'b'*64
                return ''
            before={'container_id':cid,'image_id':'unit-image','health_status':'healthy'}
            stopped={'state':{'Running':False,'ExitCode':137,'OOMKilled':False},'logs':{'events':[]}}
            with patch.object(cse_recovery,'Evidence',return_value=out), \
                    patch.object(cse_recovery,'print',create=True), \
                    patch.object(cse_recovery,'source_identity',return_value={}), \
                    patch.object(cse_recovery,'command',side_effect=command), \
                    patch.object(cse_recovery,'collect',side_effect=[before,stopped]), \
                    patch.object(cse_recovery,'await_phase',return_value={'evidence':'/app/evidence/20261115-000000Z-1234abcd','allowed_actions':['step']}), \
                    patch.object(cse_recovery,'runner_state',return_value={'Running':False}):
                self.assertEqual(cse_recovery.main(),1)
            self.assertIn(['docker','compose','start','cse'],commands)
            summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
            self.assertEqual(summary['state'],'FAIL');self.assertEqual(summary['cleanup_CSE_start'],'REQUESTED_NOT_HEALTH_VERIFIED')

    def test_wrong_private_action_configuration_fails_before_stopping_CSE(self):
        for actions in [None,[],['reset'],['step','reset']]:
            with self.subTest(actions=actions),tempfile.TemporaryDirectory() as directory:
                out=Mock();out.path=Path(directory)/'unit-out';out.path.mkdir();commands=[]
                def command(args,**kwargs):
                    commands.append(args)
                    return 'b'*64 if 'scenario-recovery' in args and '--detach' in args else ''
                ready={'evidence':'/app/evidence/20261115-000000Z-1234abcd','allowed_actions':actions}
                with patch.object(cse_recovery,'Evidence',return_value=out), \
                        patch.object(cse_recovery,'print',create=True), \
                        patch.object(cse_recovery,'source_identity',return_value={}), \
                        patch.object(cse_recovery,'command',side_effect=command), \
                        patch.object(cse_recovery,'collect',return_value={'container_id':'a'*64,'health_status':'healthy'}), \
                        patch.object(cse_recovery,'await_phase',return_value=ready), \
                        patch.object(cse_recovery,'runner_state',return_value={'Running':False}):
                    self.assertEqual(cse_recovery.main(),1)
                self.assertFalse(any(args[:3]==['docker','compose','stop'] for args in commands))
                summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
                self.assertNotIn('cleanup_CSE_start',summary)

    def test_child_failure_reason_reaches_host_summary_without_changing_FAIL(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Mock();out.path=Path(directory)/'unit-out';out.path.mkdir();cid='a'*64
            def command(args,**kwargs):
                if args[:3]==['docker','compose','ps']:return cid
                if 'scenario-recovery' in args and '--detach' in args:return 'b'*64
                if args[:3]==['docker','compose','stop']:
                    selected_recovery.signal(out.path/'control',out.path.name,'finished',summary={
                        'state':'FAIL','reason':'Unexpected fault-check HTTP status 400 (expected 202) at POST /api/v1/scenario'})
                return ''
            before={'container_id':cid,'health_status':'healthy'}
            stopped={'state':{'Running':False,'ExitCode':0,'OOMKilled':False},'logs':{'events':[{'event':'SHUTDOWN_COMPLETE'}]}}
            with patch.object(cse_recovery,'Evidence',return_value=out), \
                    patch.object(cse_recovery,'print',create=True), \
                    patch.object(cse_recovery,'source_identity',return_value={}), \
                    patch.object(cse_recovery,'command',side_effect=command), \
                    patch.object(cse_recovery,'collect',side_effect=[before,stopped]), \
                    patch.object(cse_recovery,'await_phase',side_effect=[{
                        'evidence':'/app/evidence/20261115-000000Z-1234abcd','allowed_actions':['step']},AssertionError('runner exited')]), \
                    patch.object(cse_recovery,'runner_state',return_value={'Running':False}):
                self.assertEqual(cse_recovery.main(),1)
            summary=next(c.args[1] for c in out.write.call_args_list if c.args[0]=='summary.json')
            self.assertEqual(summary['state'],'FAIL');self.assertIn('400 (expected 202)',summary['failed_child_reason'])

    def test_unsupported_runner_runtime_and_remote_target_never_contact_CSE(self):
        for version,settings in [((3,10),SimpleNamespace()),((3,12),SimpleNamespace(cse_url='https://remote.invalid'))]:
            with tempfile.TemporaryDirectory() as directory:
                session=Mock();session.evidence.path=Path(directory);session.close.return_value=True
                with patch.object(selected_recovery,'sys',SimpleNamespace(version_info=version)), \
                        patch.object(selected_recovery,'ScenarioSession',return_value=session):
                    summary,_=selected_recovery.run(settings,Path('unit-unused'),Path(directory)/'not-active','')
                self.assertEqual(summary['state'],'BLOCKED');session.start.assert_not_called()


if __name__=='__main__':unittest.main()
