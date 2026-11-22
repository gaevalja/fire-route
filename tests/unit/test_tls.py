import tempfile
from pathlib import Path
import ssl
import unittest
from unittest.mock import patch,MagicMock
from backend.tls import server_context
from infra.dev_tls import prepare

class TLSConfigurationTests(unittest.TestCase):
    def test_plain_local_profile_preserved(self):
        self.assertIsNone(server_context('http://127.0.0.1:3001'))

    def test_https_missing_pair_and_http_with_cert_fail_closed(self):
        for origin,cert,key in [('https://localhost',None,None),('https://localhost','a',None),('http://localhost','a','b'),('file:///x',None,None)]:
            with self.assertRaises(ValueError):server_context(origin,cert,key)

    def test_server_context_enforces_TLS12_and_valid_pair(self):
        fake=MagicMock()
        with patch('backend.tls.ssl.SSLContext',return_value=fake):
            self.assertIs(server_context('https://localhost','cert.pem','key.pem'),fake)
        self.assertEqual(fake.minimum_version,ssl.TLSVersion.TLSv1_2)
        fake.load_cert_chain.assert_called_once_with(certfile='cert.pem',keyfile='key.pem')

    def test_invalid_chain_and_symlink_rejected_without_value_echo(self):
        fake=MagicMock();fake.load_cert_chain.side_effect=ssl.SSLError('PRIVATE_VALUE')
        with patch('backend.tls.ssl.SSLContext',return_value=fake),self.assertRaises(ValueError) as e:
            server_context('https://localhost','cert','key')
        self.assertNotIn('PRIVATE_VALUE',str(e.exception))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'link').symlink_to(root/'absent')
            with self.assertRaises(ValueError):server_context('https://localhost',root/'link',root/'key')

    def test_existing_incomplete_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'tls';root.mkdir();(root/'ca.key').write_text('PRIVATE_VALUE')
            with self.assertRaises(ValueError):prepare(root)
            self.assertEqual((root/'ca.key').read_text(),'PRIVATE_VALUE')

    def test_world_readable_server_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            key=Path(d)/'key';key.write_text('PRIVATE_VALUE');key.chmod(0o644)
            with self.assertRaises(ValueError) as e:server_context('https://localhost','cert',key)
            self.assertNotIn('PRIVATE_VALUE',str(e.exception))
