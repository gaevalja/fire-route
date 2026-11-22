"""Fault harness fixtures only; no CSE or socket communication success claimed."""
import json
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from tests.integration.selected_faults import DisconnectEndpoint,RoleProbe,callback,disconnected_read_clients,records,run


class FaultHarnessTests(unittest.TestCase):
    def private_probe_handler(self,*,role='responder',actions=None):
        session=SimpleNamespace(settings=SimpleNamespace(),evidence=Mock(secret_values=()))
        app=Mock();app.audit_evidence.path=Path('unit-audit');auth=Mock();auth.role.return_value=role
        with patch('backend.http_api.ThreadingHTTPServer') as server, \
                patch('tests.integration.selected_faults.Thread'), \
                patch('tests.integration.selected_faults.AuthStore',return_value=auth), \
                patch.object(RoleProbe,'call'):
            server.return_value.server_address=('127.0.0.1',12345)
            probe=RoleProbe(session,app=app,**({'actions':actions} if actions is not None else {}))
            cls=server.call_args.args[1];probe.close()
        handler=object.__new__(cls);handler.path='/api/v1/scenario';handler.send=Mock()
        handler.headers={'Host':'127.0.0.1','Origin':'http://127.0.0.1','Content-Type':'application/json'}
        handler.connection=Mock();handler.token=Mock(return_value='unit-cookie')
        return probe,handler,app

    def post_action(self,handler,action):
        data=json.dumps({'action':action}).encode();handler.rfile=BytesIO(data)
        handler.headers['Content-Length']=str(len(data));handler.do_POST()
        return handler.send.call_args.args[0]

    def test_recovery_probe_step_reaches_production_API_enqueue(self):
        probe,handler,app=self.private_probe_handler(actions={'step'})
        self.assertEqual(probe.actions,frozenset({'step'}));self.assertEqual(self.post_action(handler,'step'),202)
        app.enqueue.assert_called_once_with('step')

    def test_default_fault_probe_remains_read_only(self):
        probe,handler,app=self.private_probe_handler()
        self.assertEqual(probe.actions,frozenset());self.assertEqual(self.post_action(handler,'step'),400)
        app.enqueue.assert_not_called()

    def test_recovery_step_still_requires_responder_and_denies_other_actions(self):
        _,handler,app=self.private_probe_handler(role='resident',actions={'step'})
        self.assertEqual(self.post_action(handler,'step'),403);app.enqueue.assert_not_called()
        _,handler,app=self.private_probe_handler(actions={'step'})
        self.assertEqual(self.post_action(handler,'reset'),400);app.enqueue.assert_not_called()

    def test_partial_final_evidence_line_is_not_mistaken_for_received_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rows.jsonl'
            path.write_bytes(b'{"kind":"complete"}\n{"kind":"partial"')
            self.assertEqual(records(path),[{'kind':'complete'}])
            path.write_bytes(b'invalid complete JSON\n')
            with self.assertRaises(ValueError):records(path)

    def test_only_matching_actual_sender_and_resource_are_accepted_as_callback(self):
        good={'body':{'m2m:sgn':{'nev':{'rep':{'m2m:cin':{'ri':'unit-ci'}}}}},'sender_matches_expected_cse':True}
        session=SimpleNamespace(settings=SimpleNamespace(notification_timeout=1),evidence=SimpleNamespace(path=Path('unused')))
        with patch('tests.integration.selected_faults.records',return_value=[{**good,'sender_matches_expected_cse':False},good]):
            self.assertEqual(callback(session,'unit-ci'),good)
        with patch('tests.integration.selected_faults.time.monotonic',side_effect=[0,2]):
            with self.assertRaises(AssertionError):callback(session,'unit-ci')

    def test_read_link_injection_restores_original_clients_even_on_failure(self):
        resident=SimpleNamespace(originator='C-unit-resident',release='4')
        responder=SimpleNamespace(originator='C-unit-responder',release='4')
        session=SimpleNamespace(clients={'resident':resident,'responder':responder},evidence=Mock())
        with patch('tests.integration.selected_faults.CSEClient') as client:
            with self.assertRaises(RuntimeError):
                with disconnected_read_clients(session,'http://127.0.0.1:12345'):
                    self.assertEqual(client.call_count,2)
                    raise RuntimeError('Synthetic fault')
        self.assertIs(session.clients['resident'],resident);self.assertIs(session.clients['responder'],responder)

    def test_disconnect_endpoint_closes_TCP_without_emitting_fake_HTTP(self):
        server=Mock();server.server_address=('127.0.0.1',12345);server.disconnections=0
        with patch('tests.integration.selected_faults.socketserver.ThreadingTCPServer',return_value=server) as constructor, \
                patch('tests.integration.selected_faults.Thread'):
            with DisconnectEndpoint() as endpoint:
                handler=constructor.call_args.args[1]
                peer=SimpleNamespace(server=server,request=Mock())
                handler.handle(peer)
                self.assertEqual(server.disconnections,1)
                peer.request.sendall.assert_not_called();peer.request.send.assert_not_called()
                peer.request.shutdown.assert_called_once()
                self.assertEqual(endpoint.url,'http://127.0.0.1:12345')
        server.shutdown.assert_called_once();server.server_close.assert_called_once()

    def test_unsupported_host_runtime_never_reports_actual_CSE_pass(self):
        session=Mock();session.close.return_value=True;session.evidence.path=Path('unused')
        with patch('tests.integration.selected_faults.ScenarioSession',return_value=session), \
                patch('tests.integration.selected_faults.sys',SimpleNamespace(version_info=(3,10))):
            summary,_=run(SimpleNamespace(),'unused-trace')
        self.assertEqual(summary['state'],'BLOCKED');self.assertEqual(summary['pass'],0)
        session.start.assert_not_called()
        self.assertEqual(summary['full_CSE_outage_recovery'],'NOT_RUN')

    def test_remote_target_is_blocked_before_fault_injection(self):
        session=Mock();session.close.return_value=True;session.evidence.path=Path('unused')
        with patch('tests.integration.selected_faults.ScenarioSession',return_value=session), \
                patch('tests.integration.selected_faults.sys',SimpleNamespace(version_info=(3,12))):
            summary,_=run(SimpleNamespace(cse_url='https://example.invalid'),'unused-trace')
        self.assertEqual(summary['state'],'BLOCKED');session.start.assert_not_called()

    def test_socket_denial_is_blocked_not_a_product_success(self):
        session=Mock();session.close.return_value=True;session.evidence.path=Path('unused')
        with patch('tests.integration.selected_faults.ScenarioSession',return_value=session), \
                patch('tests.integration.selected_faults.sys',SimpleNamespace(version_info=(3,12))), \
                patch('tests.integration.selected_faults.socket.socket',side_effect=PermissionError()):
            summary,_=run(SimpleNamespace(cse_url='http://cse:8080'),'unused-trace')
        self.assertEqual(summary['state'],'BLOCKED');session.start.assert_not_called()


if __name__=='__main__':unittest.main()
