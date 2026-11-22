"""Real local crypto plus transport-selection fixtures, never CSE proof."""
import shutil
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError

from infra.cse.pki import prepare,issue
from onem2m.client import CSEClient,TransportError,WireResponse
from onem2m.security import MutualTLSTransport
from tests.integration.cse_security import gateway_rejection,tls_cause


@unittest.skipUnless(shutil.which('openssl'),'OpenSSL required for actual certificate tests')
class CertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.ca=prepare(cls.root/'ca');cls.actor=issue(cls.ca,'CObserved123')
        cls.server=issue(cls.ca,'Cgateway',server=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_certificates_load_with_verification_and_reuse_same_keys(self):
        before=(self.actor/'private.key').read_bytes()
        self.assertEqual(issue(self.ca,'CObserved123'),self.actor)
        self.assertEqual((self.actor/'private.key').read_bytes(),before)
        transport=MutualTLSTransport(self.ca/'ca.crt',self.actor/'certificate.crt',self.actor/'private.key')
        contexts=[h._context for h in transport.opener.handlers if hasattr(h,'_context')]
        self.assertEqual(len(contexts),1);self.assertTrue(contexts[0].check_hostname)
        self.assertEqual(contexts[0].verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(contexts[0].minimum_version,ssl.TLSVersion.TLSv1_2)

    def test_cannot_send_mutual_TLS_credential_over_HTTP(self):
        transport=MutualTLSTransport(self.ca/'ca.crt',self.actor/'certificate.crt',self.actor/'private.key')
        with self.assertRaises(TransportError):transport('GET','http://localhost/',{},None,1)

    def test_unsafe_or_mismatched_key_is_rejected(self):
        target=self.root/'public-key-copy';shutil.copyfile(self.actor/'private.key',target);target.chmod(0o644)
        with self.assertRaises(ValueError):MutualTLSTransport(self.ca/'ca.crt',self.actor/'certificate.crt',target)
        with self.assertRaises(ValueError):MutualTLSTransport(self.ca/'ca.crt',self.actor/'certificate.crt',self.ca/'ca.key')

    def test_partial_directory_and_symlink_refuse_replacement(self):
        target=self.root/'partial';target.mkdir();(target/'ca.key').write_text('FIXTURE_INCOMPLETE')
        with self.assertRaises(ValueError):prepare(target)
        self.assertEqual((target/'ca.key').read_text(),'FIXTURE_INCOMPLETE')
        link=self.root/'link';link.symlink_to(self.ca,target_is_directory=True)
        with self.assertRaises(ValueError):issue(link,'CObserved123')

    def test_bad_certificate_subject_never_reaches_command_or_filesystem(self):
        for identity in ['../CAdmin','CAdmin/C','CAdmin\n','CAdmin;echo x','', '/id-in']:
            with self.subTest(identity=repr(identity)),self.assertRaises(ValueError):issue(self.ca,identity)

    def test_enrollment_identity_can_have_its_own_non_admin_certificate(self):
        enrollment=issue(self.ca,'C')
        self.assertNotEqual((enrollment/'private.key').read_bytes(),(self.actor/'private.key').read_bytes())

    def test_real_server_certificate_accepts_gateway_and_rejects_other_hostname(self):
        def verify(host):
            return subprocess.run(['openssl','verify','-purpose','sslserver','-verify_hostname',host,
                '-CAfile',str(self.ca/'ca.crt'),str(self.server/'certificate.crt')],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode
        self.assertEqual(verify('gateway'),0);self.assertNotEqual(verify('wrong-certificate-host'),0)


class ActorTransportTests(unittest.TestCase):
    def test_oneM2M_denial_is_not_counted_as_gateway_authentication_proof(self):
        self.assertTrue(gateway_rejection(WireResponse(403,{},b'')))
        self.assertFalse(gateway_rejection(WireResponse(403,{'X-M2M-RSC':'4103'},b'')))
        self.assertFalse(gateway_rejection(WireResponse(400,{'x-m2m-rsc':'4000'},b'')))
        self.assertFalse(gateway_rejection(WireResponse(200,{},b'')))
        error=TransportError('FIXTURE_TLS_RESULT')
        error.__cause__=URLError(ssl.SSLEOFError(8,'FIXTURE_EOF'))
        self.assertFalse(tls_cause(error))
        error.__cause__=URLError(ssl.SSLCertVerificationError(1,'FIXTURE_CERT_REJECTION'))
        self.assertTrue(tls_cause(error))

    def test_actual_returned_identity_selects_separate_transport(self):
        admin_transport=object();device_transport=object();calls=[]
        def factory(originator,actor):calls.append((originator,actor));return device_transport
        client=CSEClient('https://gateway:8443','CAdmin','4',transport=admin_transport,actor_transport=factory)
        actor=client.for_actor('CActuallyReturned','sensor')
        self.assertIs(actor.transport,device_transport);self.assertIsNot(actor.transport,admin_transport)
        self.assertEqual(calls,[('CActuallyReturned','sensor')])

    def test_missing_credential_never_falls_back_to_bootstrap(self):
        def denied(originator,actor):raise ValueError('No enrolled credential')
        client=CSEClient('https://gateway:8443','CAdmin','4',transport=object(),actor_transport=denied)
        with self.assertRaises(ValueError):client.for_actor('CNew','resident')

    def test_empty_factory_result_never_becomes_an_unauthenticated_transport(self):
        client=CSEClient('https://gateway:8443','CAdmin','4',transport=object(),actor_transport=lambda *args:None)
        with self.assertRaises(ValueError):client.for_actor('CNew','resident')

    def test_default_profile_retains_shared_transport_contract(self):
        transport=object();client=CSEClient('http://cse:8080','CAdmin','4',transport=transport)
        self.assertIs(client.for_actor('CActual','sensor').transport,transport)
