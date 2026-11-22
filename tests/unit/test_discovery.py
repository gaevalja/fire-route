"""Unit transport fixtures; never an actual discovery result."""
import unittest
from urllib.parse import parse_qs, urlsplit
from onem2m.client import CSEClient, CSEError, ProtocolError
from tests.unit.test_client import FixtureTransport, response

class DiscoveryTests(unittest.TestCase):
    def client(self, result, status=200, rsc='2000'):
        t = FixtureTransport(lambda call: response(call, result, status, rsc))
        return CSEClient('http://unit.invalid', 'C-unit', '4', transport=t), t

    def test_filter_encoding_and_actual_URI_list(self):
        c,t = self.client({'m2m:uril':['/id-unit/ae1']})
        self.assertEqual(c.discover('/base', label='namespace:unit&x=1', resource_type=2), ['/id-unit/ae1'])
        q = parse_qs(urlsplit(t.calls[0]['url']).query)
        self.assertEqual(q, {'fu':['1'],'drt':['2'],'ty':['2'],'lbl':['namespace:unit&x=1'],'lim':['100']})

    def test_empty_result_is_valid_but_not_missing_representation(self):
        self.assertEqual(self.client({'m2m:uril':[]})[0].discover('/base',label='none',resource_type=2), [])
        with self.assertRaises(ProtocolError):
            self.client({})[0].discover('/base',label='none',resource_type=2)

    def test_malformed_duplicate_external_and_over_limit_results_rejected(self):
        for refs in [None, {}, [''], ['https://foreign.invalid/a'], ['/a/../b'], ['/x?y=1'], ['/a','/a'], ['/a','/b'], [1]]:
            with self.subTest(refs=refs), self.assertRaises(ProtocolError):
                self.client({'m2m:uril':refs})[0].discover('/base',label='unit',resource_type=2,limit=1)

    def test_invalid_filters_and_paths_never_call_transport(self):
        c,t=self.client({'m2m:uril':[]})
        for label,ty,lim,path in [('',2,100,'/base'),('a b',2,100,'/base'),('a',True,100,'/base'),('a',2,True,'/base'),('a',2,1001,'/base'),('a',2,1,'/base?x=1')]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                c.discover(path,label=label,resource_type=ty,limit=lim)
        self.assertEqual(t.calls,[])

    def test_actual_denial_is_not_an_empty_search(self):
        c,_=self.client({},403,'4103')
        with self.assertRaises(CSEError) as e:c.discover('/base',label='unit',resource_type=2)
        self.assertEqual(e.exception.rsc,4103)
