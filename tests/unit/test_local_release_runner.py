"""Unit command fixtures only; never touches Docker or starts services."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from infra import local_release

class LocalReleaseRunnerTests(unittest.TestCase):
    PORTS={'CSE_HOST_PORT':'41001','APP_HOST_PORT':'41002','SCENARIO_HOST_PORT':'41003','SECURE_HOST_PORT':'41004'}
    def run_fixture(self,directory,interrupted):
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            if argv[:2]==['docker','info']:
                return subprocess.CompletedProcess(argv,0 if interrupted else 1,'unit','')
            if argv==['make','test-unit']:raise KeyboardInterrupt()
            return subprocess.CompletedProcess(argv,0,'','')
        with patch.object(local_release,'ROOT',Path(directory)),patch('sys.argv',['local_release']),\
                patch('infra.local_release.shutil.which',return_value='/unit/tool'),\
                patch('infra.local_release.source_identity',return_value={'scope':'UNIT_FIXTURE'}),\
                patch('infra.local_release.available_loopback_ports',return_value=self.PORTS),\
                patch('infra.local_release.subprocess.run',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
            code=local_release.main()
        summaries=list((Path(directory)/'evidence').glob('*/summary.json'))
        return code,json.loads(summaries[0].read_text()),calls

    def test_interrupted_step_is_failed_not_unattempted_and_only_own_projects_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            code,summary,calls=self.run_fixture(d,True)
        self.assertEqual(code,1);self.assertEqual(summary['state'],'FAIL')
        self.assertEqual(len(summary['steps']),1);self.assertEqual(summary['steps'][0]['state'],'FAIL')
        self.assertEqual(summary['unattempted_steps'],18)
        self.assertIn(['make','down'],calls)
        self.assertFalse(any('--volumes' in c or '-v' in c for c in calls))
        cleanup=[c for c in calls if c[:2]==['docker','compose']][0]
        self.assertTrue(cleanup[3].startswith('fr-accept-'));self.assertTrue(cleanup[3].endswith('-standards'))

    def test_Docker_denial_blocks_without_any_cleanup_or_acceptance_step(self):
        with tempfile.TemporaryDirectory() as d:
            code,summary,calls=self.run_fixture(d,False)
        self.assertEqual(code,1);self.assertEqual(summary['state'],'BLOCKED')
        self.assertEqual(summary['steps'],[]);self.assertEqual(summary['unattempted_steps'],19)
        self.assertEqual(len(calls),1)

    def test_selected_ports_reach_Compose_environment_and_both_browser_commands(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def command(argv,**kwargs):
                calls.append((argv,kwargs.get('env')))
                return subprocess.CompletedProcess(argv,0,'unit','')
            with patch.object(local_release,'ROOT',Path(d)),patch('sys.argv',['local_release']),\
                    patch('infra.local_release.shutil.which',return_value='/unit/tool'),\
                    patch('infra.local_release.source_identity',return_value={'scope':'UNIT_FIXTURE'}),\
                    patch('infra.local_release.available_loopback_ports',return_value=self.PORTS),\
                    patch('infra.local_release.subprocess.run',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(local_release.main(),0)
            meta=json.loads(next((Path(d)/'evidence').glob('*/meta.json')).read_text())
            self.assertEqual(meta['ports'],self.PORTS)
            for argv,environment in calls:
                if environment:
                    self.assertTrue(all(environment[k]==v for k,v in self.PORTS.items()))
            browser=[argv for argv,_ in calls if argv[:2]==['node','tests/browser/dashboard.mjs']]
            self.assertEqual(browser,[['node','tests/browser/dashboard.mjs','--port','41003'],
                                      ['node','tests/browser/dashboard.mjs','--https','--port','41004']])

class LoopbackPortSelectionTests(unittest.TestCase):
    def fixtures(self,ports,fail_index=None):
        owner=self;owner.open=set();owner.bindings=[];owner.closed=[]
        class Socket:
            def __init__(self,index):self.index=index
            def __enter__(self):owner.open.add(self.index);return self
            def __exit__(self,*args):owner.open.remove(self.index);owner.closed.append(self.index)
            def bind(self,address):
                owner.bindings.append(address)
                if self.index==fail_index:raise PermissionError('UNIT_ONLY_PRIVATE_ERROR')
            def getsockname(self):
                # Earlier selections stay reserved throughout selection.
                owner.assertEqual(owner.open,set(range(self.index+1)))
                return ('127.0.0.1',ports[self.index])
        values=iter(range(len(ports)))
        return patch('infra.local_release.socket.socket',side_effect=lambda *a:Socket(next(values)))

    def test_kernel_allocates_distinct_ports_and_closes_all_reservations(self):
        with self.fixtures([44001,44002,44003,44004]):
            result=local_release.available_loopback_ports()
        self.assertEqual(list(result.values()),['44001','44002','44003','44004'])
        self.assertEqual(self.bindings,[('127.0.0.1',0)]*4)
        self.assertEqual(self.closed,[3,2,1,0]);self.assertEqual(self.open,set())

    def test_failed_binding_releases_reservations_and_never_exposes_error_value(self):
        with self.fixtures([44001,44002,44003],fail_index=2),self.assertRaises(RuntimeError) as error:
            local_release.available_loopback_ports()
        self.assertEqual(self.closed,[2,1,0]);self.assertEqual(self.open,set())
        self.assertNotIn('UNIT_ONLY_PRIVATE_ERROR',str(error.exception))

    def test_duplicate_or_privileged_port_is_rejected_without_starting_services(self):
        for ports in [[44001,44001],[80]]:
            with self.subTest(ports=ports),self.fixtures(ports),self.assertRaises(RuntimeError):
                local_release.available_loopback_ports()
            self.assertEqual(self.open,set())
