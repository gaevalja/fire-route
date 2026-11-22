"""Pure TS-0010 primitive fixtures; no broker/CSE integration claim."""
import json
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import itertools
from onem2m.mqtt import topic_id, request_primitive, validate_response, OneM2MMQTT
from onem2m.client import CSEError, ProtocolError, TransportError

class MQTTBindingTests(unittest.TestCase):
    def test_topic_ID_mapping_and_no_wildcards(self):
        self.assertEqual(topic_id('/id-cse/ae'), 'id-cse:ae')
        for value in ['', '/', 'C+', 'C#', 'C x', '/a/../b','https://bad']:
            with self.subTest(value=value),self.assertRaises(ValueError):topic_id(value)

    def test_CREATE_and_RETRIEVE_have_correlated_primitive_not_HTTP_response(self):
        create=request_primitive('/base/ae/telemetry','C-unit','4',attributes={'con':'{}'})
        get=request_primitive('/base/ae/telemetry/la','C-unit','4')
        self.assertEqual((create['op'],create['ty'],create['to']),(1,4,'base/ae/telemetry'))
        self.assertEqual(create['pc'],{'m2m:cin':{'con':'{}'}})
        self.assertNotEqual(create['rqi'],get['rqi'])
        self.assertNotIn('pc',get)
        self.assertEqual(get['op'],2)

    def test_invalid_target_and_nonfinite_payload_rejected_before_network(self):
        for path in ['http://bad','//bad','/x?fu=1','/a/../b','/x\r\n']:
            with self.assertRaises(ValueError):request_primitive(path,'C-unit','4')
        with self.assertRaises(ValueError):request_primitive('/x','C-unit','4',attributes={'x':float('nan')})

    def test_response_requires_actual_oneM2M_status_id_release_and_content(self):
        req=request_primitive('/x','C-unit','4',attributes={})
        okay={'rqi':req['rqi'],'rvi':'4','rsc':2001,'pc':{'m2m:cin':{'ty':4,'ri':'unit'}}}
        self.assertEqual(validate_response(json.dumps(okay).encode(),req),okay)
        for mutation in [{'rqi':'other'},{'rvi':'5'},{'rsc':True},{'rsc':2000},{'pc':None}]:
            with self.subTest(mutation=mutation),self.assertRaises(ProtocolError):
                validate_response(json.dumps({**okay,**mutation}).encode(),req)
        for raw in [b'PUBACK',b'[]',b'{"rsc":NaN}',b'x'*(1024*1024+1)]:
            with self.assertRaises(ProtocolError):validate_response(raw,req)

    def test_ACP_denial_propagates_without_retry_or_success_conversion(self):
        req=request_primitive('/x','C-unit','4')
        with self.assertRaises(CSEError) as error:
            validate_response(json.dumps({'rqi':req['rqi'],'rvi':'4','rsc':4103}).encode(),req)
        self.assertEqual(error.exception.rsc,4103)

    def test_connection_configuration_rejects_bad_host_and_budgets(self):
        for broker,port,timeout in [('http://bad',1883,10),('mqtt',True,10),('mqtt',1883,0)]:
            with self.assertRaises(ValueError):OneM2MMQTT(broker,'/id-cse','C-unit',port=port,timeout=timeout)

    def fixture_sdk(self, *, send_response=True, retained=False, subscription=True):
        """Unit-only SDK fixture, not a running broker or CSE."""
        owner=self;owner.sent=[];owner.disconnected=0
        class Client:
            def __init__(self,*a,**k):pass
            def connect(self,*a,**k):self.on_connect(self,None,None,SimpleNamespace(is_failure=False),None)
            def subscribe(self,topic,qos):
                self.topic=topic
                if subscription:self.on_subscribe(self,None,1,[SimpleNamespace(is_failure=False)],None)
                return 0,1
            def publish(self,topic,body,**kwargs):
                owner.sent.append((topic,json.loads(body),kwargs))
                if send_response:
                    req=json.loads(body)
                    self.on_message(self,None,SimpleNamespace(topic=self.topic,retain=retained,payload=json.dumps(
                        {'rqi':req['rqi'],'rvi':'4','rsc':2001,'pc':{'m2m:cin':{'ri':'unit','ty':4}}}).encode()))
                return SimpleNamespace(rc=0)
            def loop(self,**kwargs):return 0
            def disconnect(self):owner.disconnected+=1
        package=ModuleType('paho');sub=ModuleType('paho.mqtt');sdk=ModuleType('paho.mqtt.client')
        sdk.Client=Client;sdk.CallbackAPIVersion=SimpleNamespace(VERSION2=2);sdk.MQTTv311=4;sdk.MQTT_ERR_SUCCESS=0
        package.mqtt=sub;sub.client=sdk
        return patch.dict('sys.modules',{'paho':package,'paho.mqtt':sub,'paho.mqtt.client':sdk})

    def test_single_publish_requires_primitive_response_and_disconnects(self):
        with self.fixture_sdk():
            value=OneM2MMQTT('mqtt','/id-cse','C-unit').exchange('/base',attributes={'con':'{}'})
        self.assertEqual(value['rsc'],2001);self.assertEqual(self.disconnected,1)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.sent[0][2],{'qos':1,'retain':False})

    def test_PUBACK_without_oneM2M_response_times_out_and_is_never_replayed(self):
        with self.fixture_sdk(send_response=False),patch('onem2m.mqtt.time.monotonic',side_effect=itertools.count(0,.01)):
            with self.assertRaises(TransportError):OneM2MMQTT('mqtt','/id-cse','C-unit',timeout=.02).exchange('/base',attributes={})
        self.assertEqual(len(self.sent),1);self.assertEqual(self.disconnected,1)

    def test_publish_waits_for_SUBACK_and_rejects_retained_responses(self):
        with self.fixture_sdk(subscription=False),patch('onem2m.mqtt.time.monotonic',side_effect=itertools.count(0,.01)):
            with self.assertRaises(TransportError):OneM2MMQTT('mqtt','/id-cse','C-unit',timeout=.02).exchange('/base',attributes={})
        self.assertEqual(self.sent,[])
        with self.fixture_sdk(retained=True):
            with self.assertRaises(TransportError):OneM2MMQTT('mqtt','/id-cse','C-unit',timeout=.01).exchange('/base',attributes={})
