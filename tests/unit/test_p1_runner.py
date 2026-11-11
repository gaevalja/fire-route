from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.config import Settings
from backend.p1_routes import require_denial, run
from onem2m.client import CSEError, ProtocolError


class P1RunnerTests(unittest.TestCase):
    def test_blocked_socket_is_not_an_integration_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(evidence_root=Path(directory))
            with patch('backend.p1_routes.socket.socket', side_effect=PermissionError('unit-only socket denial')):
                result, path = run(settings, require_target_python=False)
            self.assertEqual((result['state'], result['pass'], result['blocked']), ('BLOCKED', 0, 1))
            self.assertEqual(result['all_device_acks'], 'NOT_RUN')
            self.assertEqual(result['MEC'], 'unavailable')
            self.assertFalse((path / 'requests.jsonl').exists())

    def test_only_actual_consistent_access_denial_is_accepted(self):
        def deny():
            raise CSEError('unit denial', http_status=403, rsc=4103)
        require_denial(deny)

    def test_malformed_or_wrong_response_cannot_prove_denial(self):
        for exc in [ProtocolError('unit mismatch', http_status=403, rsc=4103),
                    CSEError('unit wrong HTTP', http_status=200, rsc=4103),
                    CSEError('unit missing resource', http_status=404, rsc=4004)]:
            def operation():
                raise exc
            with self.subTest(error=type(exc).__name__, status=exc.http_status), self.assertRaises(CSEError):
                require_denial(operation)

    def test_successful_forbidden_operation_fails_the_gate(self):
        with self.assertRaises(ProtocolError):
            require_denial(lambda: {'unit': 'unexpectedly allowed'})
