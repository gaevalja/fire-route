"""Explicit MEC HTTP/CSE fixtures only; no actual MEC response is generated."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mec.catalog import CatalogSettings,DiscoveryTransport,MECError,discover,persist_catalog
from mec.probe import run


def service():
    return {'serName':'FIXTURE_SERVICE','version':'2.0','state':'ACTIVE','serializer':'JSON',
            'serInstanceId':'fixture-id','transportInfo':{'type':'REST_HTTP','protocol':'HTTP',
                'endpoint':{'uris':['http://fixture.invalid/?token=FIXTURE_SECRET']},
                'security':{'credentials':'FIXTURE_SECRET'}}}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.settings=CatalogSettings('https://fixture.invalid/mec_service_mgmt/v1','hosted-sandbox')

    def fixture(self,body,status=200,media='application/json'):
        calls=[]
        def transport(url):calls.append(url);return status,{'Content-Type':media},json.dumps(body).encode()
        return transport,calls

    def test_global_and_application_scoped_paths_follow_inspected_API(self):
        transport,calls=self.fixture([service()]);snapshot=discover(self.settings,transport=transport)
        self.assertEqual(calls,['https://fixture.invalid/mec_service_mgmt/v1/services'])
        settings=CatalogSettings(self.settings.service_management_url,'hosted-sandbox','allocated-app-id')
        discover(settings,transport=transport)
        self.assertTrue(calls[-1].endswith('/applications/allocated-app-id/services'))
        self.assertEqual(snapshot['service_count'],1)
        self.assertEqual(snapshot['deployment'],'NOT_VERIFIED_BY_DISCOVERY')
        self.assertEqual(snapshot['MEC_IPE'],'NOT_IMPLEMENTED')

    def test_security_blocks_and_endpoints_never_enter_public_catalog(self):
        transport,_=self.fixture([service()]);snapshot=discover(self.settings,transport=transport)
        self.assertNotIn('FIXTURE_SECRET',json.dumps(snapshot));self.assertNotIn('endpoint',json.dumps(snapshot))

    def test_empty_actual_response_remains_empty_not_a_fabricated_service(self):
        transport,_=self.fixture([]);self.assertEqual(discover(self.settings,transport=transport)['services'],[])

    def test_bad_status_media_shapes_and_duplicate_service_ids_fail(self):
        cases=[({'services':[]},200,'application/json'),([service()],302,'application/json'),
               ([service()],200,'text/html'),([service(),service()],200,'application/json'),
               ([{'serName':'missing-fields'}],200,'application/json')]
        for body,status,media in cases:
            transport,_=self.fixture(body,status,media)
            with self.subTest(status=status,media=media),self.assertRaises(MECError) as caught:
                discover(self.settings,transport=transport)
            if status!=200:self.assertEqual(caught.exception.http_status,status)

    def test_non_finite_and_oversized_json_fail(self):
        for body in [b'[NaN]',b'x'*(1024*1024+1)]:
            with self.assertRaises(MECError):discover(self.settings,transport=lambda url:(200,{'content-type':'application/json'},body))

    def test_plaintext_hosted_or_plaintext_bearer_and_wrong_API_path_rejected(self):
        for url,environment,token in [('http://fixture.invalid/mec_service_mgmt/v1','hosted-sandbox',None),
            ('http://localhost/mec_service_mgmt/v1','local-sandbox',Path('fixture')),
            ('https://localhost/mec_service_mgmt/v1','hosted-sandbox',None),
            ('https://fixture.invalid/invented-api','hosted-sandbox',None)]:
            with self.subTest(url=url),self.assertRaises(ValueError):CatalogSettings(url,environment,token_file=token)

    def test_private_bearer_file_required_no_token_echo(self):
        with tempfile.TemporaryDirectory() as d:
            token=Path(d)/'token';token.write_text('FIXTURE_SECRET');token.chmod(0o644)
            settings=CatalogSettings(self.settings.service_management_url,'hosted-sandbox',token_file=token)
            with self.assertRaises(ValueError) as caught:DiscoveryTransport(settings)
            self.assertNotIn('FIXTURE_SECRET',str(caught.exception))

    def test_missing_MEC_environment_is_BLOCKED_without_network(self):
        with tempfile.TemporaryDirectory() as d,patch('mec.probe.discover') as call:
            result,_=run({'EVIDENCE_ROOT':d})
            self.assertEqual(result['state'],'BLOCKED');self.assertEqual(result['Hosted'],'NOT_CONTACTED');call.assert_not_called()

    def test_known_reflected_bearer_is_redacted_in_service_metadata(self):
        class FixtureTransport:
            token='FIXTURE_TOKEN_REFLECTED'
            def __call__(self,url):
                item=service();item['serName']=self.token
                return 200,{'content-type':'application/json'},json.dumps([item]).encode()
        self.assertNotIn(FixtureTransport.token,json.dumps(discover(self.settings,transport=FixtureTransport())))


class BridgeTests(unittest.TestCase):
    def test_bridge_records_actual_CIN_and_readback_and_never_claims_MEC_IPE(self):
        settings=CatalogSettings('http://fixture.invalid/mec_service_mgmt/v1','local-sandbox')
        snapshot=discover(settings,transport=lambda url:(200,{'content-type':'application/json'},b'[]'))
        class CSEFixture:
            def __init__(self):self.payload=None;self.calls=[]
            def resource(self,result,ty):return result
            def retrieve(self,path):
                self.calls.append(('GET',path));return {'ri':'fixture-cnt','lbl':['fire-route:mec-catalog']} if self.payload is None else {'ri':'fixture-cin','con':self.payload['con']}
            def create(self,path,ty,payload):self.calls.append(('POST',path));self.payload=payload;return {'ri':'fixture-cin'}
        cse=CSEFixture();result=persist_catalog(cse,'/fixture/cnt',snapshot)
        self.assertEqual([c[0] for c in cse.calls],['GET','POST','GET'])
        self.assertEqual(result['MEC_IPE'],'NOT_IMPLEMENTED')
        self.assertEqual(json.loads(cse.payload['con'])['consumption_path'],'APPLICATION_AE_BRIDGE_NOT_MEC_IPE')

    def test_bridge_does_not_retry_uncertain_CSE_create(self):
        class Broken:
            calls=0
            def resource(self,r,t):return r
            def retrieve(self,p):return {'ri':'fixture-cnt','lbl':['fire-route:mec-catalog']}
            def create(self,*args):self.calls+=1;raise OSError('FIXTURE_CONNECTION_LOST')
        cse=Broken()
        with self.assertRaises(OSError):persist_catalog(cse,'/fixture/cnt',{'MEC_API':'MEC011_SERVICE_DISCOVERY','consumption_path':'DIRECT_MEC_API'})
        self.assertEqual(cse.calls,1)

    def test_bridge_rejects_unrelated_container_before_any_create(self):
        class Unrelated:
            def resource(self,r,t):return r
            def retrieve(self,p):return {'ri':'fixture-telemetry','lbl':['fire-route']}
            def create(self,*args):raise AssertionError('Must not write to another module')
        with self.assertRaises(ValueError):persist_catalog(Unrelated(),'/fixture/telemetry',
            {'MEC_API':'MEC011_SERVICE_DISCOVERY','consumption_path':'DIRECT_MEC_API'})
