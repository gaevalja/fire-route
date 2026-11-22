"""Synthetic Docker/CSE fixtures; not actual lifecycle or persistence evidence."""
import json
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from infra import local_stability
from infra.cse.diagnostics import DockerUnavailable,classify,collect,event_view,inspect_view,log_view,SOURCE_PROBE
from tests.integration.cse_persistence import verify_marker
from tests.integration import cse_persistence
from onem2m.client import CSEError


class DockerObservationTests(unittest.TestCase):
    def observation(self,**state):
        return {'state':{'Running':False,'ExitCode':137,'OOMKilled':False,**state},'events':[]}

    def test_exit_137_does_not_imply_OOM_or_timeout(self):
        self.assertEqual(classify(self.observation()),'EXIT_137_UNDETERMINED')

    def test_actual_OOM_flag_or_event_is_distinct(self):
        self.assertEqual(classify(self.observation(OOMKilled=True)),'OOM_OBSERVED')
        obs=self.observation();obs['events']=[{'action':'oom'}]
        self.assertEqual(classify(obs),'OOM_OBSERVED')

    def test_timeout_requires_controlled_duration_and_both_signals(self):
        obs=self.observation();obs['events']=[{'action':'kill','signal':'15'},{'action':'kill','signal':'9'}]
        self.assertEqual(classify(obs),'EXIT_137_UNDETERMINED')
        self.assertEqual(classify(obs,controlled_stop_elapsed=30.1,grace_seconds=30),'CONTROLLED_STOP_TIMEOUT_SUPPORTED')
        self.assertEqual(classify(obs,controlled_stop_elapsed=2,grace_seconds=30),'EXIT_137_UNDETERMINED')
        obs['events'].pop()
        self.assertEqual(classify(obs,controlled_stop_elapsed=30,grace_seconds=30),'EXIT_137_UNDETERMINED')

    def test_timeout_follows_actual_configured_interrupt_signal(self):
        obs=self.observation();obs['stop_signal']='SIGINT'
        obs['events']=[{'action':'kill','signal':'2'},{'action':'kill','signal':'9'}]
        self.assertEqual(classify(obs,controlled_stop_elapsed=30.1,grace_seconds=30),
            'CONTROLLED_STOP_TIMEOUT_SUPPORTED')
        obs['events'][0]['signal']='15'
        self.assertEqual(classify(obs,controlled_stop_elapsed=30.1,grace_seconds=30),'EXIT_137_UNDETERMINED')
        obs['stop_signal']='SIGUSR1'
        self.assertEqual(classify(obs,controlled_stop_elapsed=30.1,grace_seconds=30),'EXIT_137_UNDETERMINED')

    def test_running_and_zero_exit_are_only_observations(self):
        self.assertEqual(classify(self.observation(Running=True)),'RUNNING')
        self.assertEqual(classify(self.observation(ExitCode=0)),'EXIT_ZERO_OBSERVED')

    def test_inspect_selects_no_environment_args_or_bind_source(self):
        raw={'Id':'a'*64,'State':{'Running':False,'ExitCode':137,'OOMKilled':False,'Error':'private-fixture-value',
                'Health':{'Status':'healthy','Log':[{'Output':'private-fixture-value'}]}},
            'Config':{'Env':['TOKEN=private-fixture-value'],'Cmd':['private-fixture-value']},
            'HostConfig':{'Memory':123},'Mounts':[{'Type':'bind','Source':'private-fixture-value','Destination':'/data'}]}
        result=inspect_view(raw)
        self.assertNotIn('private-fixture-value',json.dumps(result))
        self.assertTrue(result['runtime_error_present']);self.assertEqual(result['stop_signal'],'SIGTERM')
        self.assertEqual(result['health_status'],'healthy')
        raw['State']['Health']['Status']='private-fixture-value'
        self.assertIsNone(inspect_view(raw)['health_status'])

    def test_event_labels_and_raw_logs_are_never_retained(self):
        event=event_view({'Action':'kill','Actor':{'Attributes':{'signal':'9','token':'private-fixture-value'}}})
        logs=log_view('2026-11-14T02:00:00Z CSE started private-fixture-value\nprivate-fixture-value\nUsing default secret key')
        self.assertNotIn('private-fixture-value',json.dumps([event,logs]))
        self.assertEqual([e['event'] for e in logs['events']],['STARTED','DEFAULT_SECRET_WARNING'])
        self.assertFalse(logs['raw_log_retained'])
        colored=log_view('Using \x1b[31mdefault secret key\x1b[0m')
        self.assertEqual(colored['events'][0]['event'],'DEFAULT_SECRET_WARNING')

    def test_exec_event_action_never_retains_command_or_credentials(self):
        for action in ['exec_create','exec_start']:
            result=event_view({'Action':action+': python -c private-fixture-value',
                'Actor':{'Attributes':{'execCommand':'private-fixture-value'}}})
            self.assertEqual(result['action'],action)
            self.assertNotIn('private-fixture-value',json.dumps(result))
        self.assertEqual(event_view({'Action':'private-fixture-value'})['action'],'OTHER')

    def test_source_probe_syntax_does_not_require_installed_CSE(self):
        compile(SOURCE_PROBE,'installed-source-probe','exec')

    def test_nanosecond_exit_timestamp_keeps_event_window_at_actual_exit(self):
        raw={'Id':'a'*64,'State':{'Running':False,'ExitCode':137,'OOMKilled':False,
            'FinishedAt':'2026-11-14T02:18:10.251357874Z'}}
        def run(args):
            if args[:2]==['docker','inspect']:return json.dumps([raw])
            if args[:2] in [['docker','events'],['docker','logs']]:return ''
            self.fail('Unexpected fixture Docker operation')
        value=collect(container_id='a'*64,run=run)
        self.assertEqual(value['event_window']['since'],'2026-11-14T02:16:40.251357+00:00')
        self.assertEqual(value['state']['FinishedAt'],raw['State']['FinishedAt'])
        self.assertEqual(classify(value),'EXIT_137_UNDETERMINED')

    def test_controlled_stop_log_window_cannot_include_old_shutdown(self):
        commands=[];since='2026-11-14T04:00:00+00:00'
        raw={'Id':'a'*64,'State':{'Running':False,'ExitCode':0,'OOMKilled':False}}
        def run(args):
            commands.append(args)
            return json.dumps([raw]) if args[:2]==['docker','inspect'] else ''
        collect(container_id='a'*64,since=since,run=run)
        log_command=next(argv for argv in commands if argv[:2]==['docker','logs'])
        self.assertEqual(log_command[log_command.index('--since')+1],since)


class PersistenceReadbackTests(unittest.TestCase):
    def setUp(self):
        self.record={'ae_path':'/base/owned','ae_ri':'ae-ri','ae_id':'C-unit',
            'container_path':'/base/owned/marker','container_ri':'cnt-ri',
            'cin_path':'/base/owned/marker/before-restart','cin_ri':'cin-ri',
            'content':{'probe_id':'synthetic-unit'}}
        self.ae={'ri':'ae-ri','aei':'C-unit'};self.cnt={'ri':'cnt-ri'}
        self.cin={'ri':'cin-ri','con':json.dumps(self.record['content'])}
        self.client=Mock();self.actor=Mock();self.client.for_actor.return_value=self.actor
        self.client.resource.return_value=self.ae
        self.actor.resource.side_effect=lambda value,ty:self.cnt if ty==3 else self.cin

    def test_actual_returned_identity_is_used_for_marker_reads(self):
        verify_marker(self.client,self.record)
        self.client.for_actor.assert_called_once_with('C-unit','persistence-marker')
        self.assertEqual(self.actor.retrieve.call_count,2)

    def test_changed_AE_container_CIN_or_content_never_passes(self):
        for target,key,value in [(self.ae,'aei','C-other'),(self.cnt,'ri','other'),
                                 (self.cin,'ri','other'),(self.cin,'con','{"probe_id":"changed"}')]:
            old=target[key];target[key]=value
            with self.assertRaises(AssertionError):verify_marker(self.client,self.record)
            target[key]=old

    def test_actual_probe_error_fields_are_reported_without_exception_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime.json';state=root/'state.json'
            runtime.write_text(json.dumps({'secret_configured':True,'config_sha256':'synthetic-hash',
                'shutdown_patch':{'patch_id':'acme-2026.5.1-shutdown-state-guard-v1','verified':True}}))
            state.write_text('{}')
            settings=SimpleNamespace(evidence_root=root/'evidence',admin_originator='C-unit-admin',
                cse_url='http://unit.invalid:8080',release='4',request_timeout=1,runtime_info=runtime)
            with patch.object(cse_persistence,'sys',SimpleNamespace(version_info=(3,12))), \
                    patch.object(cse_persistence,'CSEClient'),patch.object(cse_persistence,'wait_for_cse'), \
                    patch.object(cse_persistence,'verify_marker',side_effect=CSEError(
                        'private-fixture-value',http_status=404,rsc=4004)):
                summary,path=cse_persistence.run(settings,'verify',state)
            self.assertEqual(summary['state'],'FAIL')
            self.assertEqual((summary['http_status'],summary['rsc']),(404,4004))
            self.assertNotIn('private-fixture-value',(path/'summary.json').read_text())

    def test_probe_rejects_unverified_patch_metadata_before_marker_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime.json';state=root/'state.json';state.write_text('{}')
            settings=SimpleNamespace(evidence_root=root/'evidence',admin_originator='C-unit-admin',
                cse_url='http://unit.invalid:8080',release='4',request_timeout=1,runtime_info=runtime)
            for value in [None,{}, {'verified':False,'patch_id':'acme-2026.5.1-shutdown-state-guard-v1'},
                          {'verified':True,'patch_id':'synthetic-other'}]:
                runtime.write_text(json.dumps({'secret_configured':True,'config_sha256':'synthetic-hash',
                    'shutdown_patch':value}))
                with patch.object(cse_persistence,'sys',SimpleNamespace(version_info=(3,12))), \
                        patch.object(cse_persistence,'CSEClient'),patch.object(cse_persistence,'wait_for_cse'), \
                        patch.object(cse_persistence,'verify_marker') as verify:
                    summary,path=cse_persistence.run(settings,'verify',state)
                self.assertEqual(summary['state'],'FAIL');verify.assert_not_called()

    def test_changed_patch_fingerprint_does_not_pass_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime.json';state=root/'state.json'
            adapter={'verified':True,'patch_id':'acme-2026.5.1-shutdown-state-guard-v1','patched_sha256':'synthetic-old'}
            state.write_text(json.dumps({'runtime_config_sha256':'synthetic-hash','shutdown_patch':adapter}))
            runtime.write_text(json.dumps({'secret_configured':True,'config_sha256':'synthetic-hash',
                'shutdown_patch':{**adapter,'patched_sha256':'synthetic-changed'}}))
            settings=SimpleNamespace(evidence_root=root/'evidence',admin_originator='C-unit-admin',
                cse_url='http://unit.invalid:8080',release='4',request_timeout=1,runtime_info=runtime)
            with patch.object(cse_persistence,'sys',SimpleNamespace(version_info=(3,12))), \
                    patch.object(cse_persistence,'CSEClient'),patch.object(cse_persistence,'wait_for_cse'), \
                    patch.object(cse_persistence,'verify_marker'):
                summary,path=cse_persistence.run(settings,'verify',state)
            self.assertEqual(summary['state'],'FAIL')
            self.assertEqual(summary['reason'],'CSE shutdown patch changed during restart')


class LifecycleReadinessTests(unittest.TestCase):
    """Simulated orchestration only; never counted as actual CSE lifecycle proof."""
    def simulate(self,failure=None):
        files={};commands=[];events=[];state={'running':False,'restart':False,'stopped':False}
        out=Mock();out.path=Path('evidence/unit-fixture')
        out.write.side_effect=lambda name,value:files.__setitem__(name,deepcopy(value))
        def docker(args,**kwargs):
            commands.append(args)
            if args[:3]==['docker','compose','up']:
                state['running']=True
                if failure=='initial-timeout':raise DockerUnavailable('Synthetic health timeout')
                events.append('initial-health-returned')
            elif args[:3]==['docker','compose','stop']:
                events.append('stop');state.update(running=False,stopped=True)
            elif args[:3]==['docker','compose','start']:
                state.update(running=True,restart=True)
                if '--wait' in args:
                    if failure=='restart-timeout':raise DockerUnavailable('Synthetic health timeout')
                    events.append('restart-health-returned')
            return ''
        def observe():
            running=state['running']
            forced=state['stopped'] and not running and failure=='forced-stop'
            logs=[{'event':'SHUTDOWN_COMPLETE'}] if state['stopped'] and not running and failure not in {'no-shutdown-marker','forced-stop'} else []
            return {'state':{'Running':running,'ExitCode':137 if forced else 0,'OOMKilled':False},
                'health_status':('unhealthy' if failure=='initial-unhealthy' else 'healthy') if running else None,
                'mounts':[{'type':'volume','destination':'/data'}],'logs':{'events':logs}}
        def probe(args,**kwargs):
            phase=args[-3];events.append('probe-'+phase)
            value={'test':'CSE_PERSISTENCE_PROBE','phase':phase,'state':'PASS',
                'evidence':'/app/evidence/synthetic-child'}
            if failure=='prepare' and phase=='prepare':value.update(state='FAIL',reason='ProtocolError')
            if failure=='verify' and phase=='verify':value.update(state='FAIL',reason='CSEError',http_status=404,rsc=4004)
            return subprocess.CompletedProcess(args,0 if value['state']=='PASS' else 1,json.dumps(value),'')
        with patch.object(local_stability,'Evidence',return_value=out), \
                patch.object(local_stability,'command',side_effect=docker), \
                patch.object(local_stability,'collect',side_effect=lambda **kw:observe()), \
                patch.object(local_stability,'source_identity',return_value={}), \
                patch.object(local_stability.subprocess,'run',side_effect=probe), \
                redirect_stdout(io.StringIO()):
            result=local_stability.main()
        return result,files,commands,events

    def test_both_probes_follow_successful_health_waits(self):
        code,files,commands,events=self.simulate()
        self.assertEqual(code,0)
        self.assertEqual(events,['initial-health-returned','probe-prepare','stop',
            'restart-health-returned','probe-verify'])
        for operation in ['up','start']:
            argv=next(c for c in commands if c[:3]==['docker','compose',operation])
            self.assertIn('--wait',argv);self.assertIn('--wait-timeout',argv)
            self.assertEqual(argv[-1],'cse')
        self.assertEqual(files['summary.json']['persistence'],'PASS')
        self.assertIn('ready-before-prepare.json',files)
        self.assertIn('ready-before-verify.json',files)
        self.assertNotIn('failure-observation.json',files)

    def test_initial_health_timeout_never_runs_marker_or_stop(self):
        code,files,commands,events=self.simulate('initial-timeout')
        self.assertEqual(code,1)
        self.assertEqual(files['summary.json']['state'],'FAIL')
        self.assertEqual(files['summary.json']['phase'],'WAIT_INITIAL_CSE_HEALTH')
        self.assertEqual(files['summary.json']['persistence'],'NOT_RUN')
        self.assertEqual(files['summary.json']['shutdown'],'NOT_RUN')
        self.assertEqual(events,[])
        self.assertIn('failure-observation.json',files)

    def test_unhealthy_observation_never_runs_marker(self):
        code,files,commands,events=self.simulate('initial-unhealthy')
        self.assertEqual(code,1)
        self.assertEqual(events,['initial-health-returned'])
        self.assertNotIn('initial_CSE_healthcheck_passed',files['assertions.json'])
        self.assertIn('failure-observation.json',files)

    def test_prepare_protocol_failure_retains_child_and_never_stops_CSE(self):
        code,files,commands,events=self.simulate('prepare')
        self.assertEqual(code,1)
        self.assertEqual(events,['initial-health-returned','probe-prepare'])
        summary=files['summary.json']
        self.assertEqual(summary['failed_probe_reason'],'ProtocolError')
        self.assertEqual(summary['failed_probe_evidence'],'/app/evidence/synthetic-child')
        self.assertEqual(summary['failed_probe_phase'],'prepare')
        self.assertEqual(summary['persistence'],'NOT_RUN');self.assertEqual(summary['shutdown'],'NOT_RUN')
        self.assertIn('failure-observation.json',files)

    def test_restart_timeout_has_no_verify_or_persistence_pass(self):
        code,files,commands,events=self.simulate('restart-timeout')
        self.assertEqual(code,1)
        self.assertEqual(events,['initial-health-returned','probe-prepare','stop'])
        summary=files['summary.json']
        self.assertEqual(summary['shutdown'],'PASS')
        self.assertEqual(summary['persistence'],'NOT_RUN')
        self.assertEqual(summary['recovery_start'],'REQUESTED_NOT_HEALTH_VERIFIED')
        self.assertIn('failure-observation.json',files)

    def test_failed_verify_is_persistence_failure_instead_of_not_run(self):
        code,files,commands,events=self.simulate('verify')
        self.assertEqual(code,1)
        self.assertEqual(events[-1],'probe-verify')
        summary=files['summary.json']
        self.assertEqual(summary['persistence'],'FAIL')
        self.assertEqual(summary['failed_probe_phase'],'verify')
        self.assertEqual(summary['shutdown'],'PASS')
        self.assertEqual((summary['failed_probe_http_status'],summary['failed_probe_rsc']),(404,4004))
        self.assertEqual(files['probe-verify.json']['rsc'],4004)

    def test_persisted_marker_does_not_hide_failed_shutdown(self):
        for mode in ['forced-stop','no-shutdown-marker']:
            with self.subTest(mode=mode):
                code,files,commands,events=self.simulate(mode)
                self.assertEqual(code,1)
                self.assertEqual(files['summary.json']['persistence'],'PASS')
                self.assertEqual(files['summary.json']['shutdown'],'FAIL')
                self.assertFalse(files['assertions.json']['shutdown_complete_marker_observed'])


if __name__=='__main__':unittest.main()
