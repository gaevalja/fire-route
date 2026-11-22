"""Bounded oneM2M TS-0010 JSON request/response binding, not raw telemetry.

Paho is an optional dependency of the isolated standards test image only.
MQTT PUBACK is never interpreted as a oneM2M response or device ACK.
No application retry/reconnect is performed after an uncertain CREATE.
"""
from __future__ import annotations
import json
import time
from uuid import uuid4

from onem2m.client import CSEError, ProtocolError, TransportError, strict_json


def topic_id(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 256
            or any(c in value for c in '#+?\\\x00\r\n')
            or any(c.isspace() for c in value) or '://' in value
            or any(p in {'.','..'} for p in value.split('/'))):
        raise ValueError('Invalid oneM2M topic identity')
    value = value.lstrip('/').replace('/', ':')
    if not value:
        raise ValueError('Empty oneM2M topic identity')
    return value


def request_primitive(path, actor, release, *, attributes=None):
    if (not isinstance(path,str) or not path.startswith('/') or path.startswith('//')
            or any(c in path for c in '?#\\\r\n')
            or any(p in {'.','..'} for p in path.split('/'))):
        raise ValueError('Invalid CSE-relative MQTT target')
    topic_id(actor)
    if release != '4':
        raise ValueError('This binding profile is tested against release 4 only')
    primitive = {'op': 1 if attributes is not None else 2, 'to': path.lstrip('/'),
                 'fr': actor, 'rqi': 'fr-' + uuid4().hex, 'rvi': release}
    if attributes is not None:
        if not isinstance(attributes, dict):raise ValueError('CIN attributes must be an object')
        # Validate serialization before any network operation.
        json.dumps(attributes, allow_nan=False)
        primitive.update(ty=4, pc={'m2m:cin': attributes})
    return primitive


def validate_response(payload: bytes, expected: dict) -> dict:
    if not isinstance(payload, bytes) or len(payload) > 1024*1024:
        raise ProtocolError('MQTT oneM2M response exceeds limit')
    try:
        response = strict_json(payload)
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError('Invalid MQTT oneM2M JSON') from None
    if (not isinstance(response, dict) or response.get('rqi') != expected['rqi']
            or response.get('rvi') != expected['rvi']
            or type(response.get('rsc')) is not int):
        raise ProtocolError('Uncorrelated MQTT oneM2M response')
    if not 2000 <= response['rsc'] < 3000:
        raise CSEError('MQTT oneM2M operation denied/failed', rsc=response['rsc'])
    wanted = 2001 if expected['op'] == 1 else 2000
    if response['rsc'] != wanted or not isinstance(response.get('pc'),dict):
        raise ProtocolError('Unexpected MQTT oneM2M result', rsc=response['rsc'])
    return response


class OneM2MMQTT:
    def __init__(self, broker: str, cse_id: str, actor: str, *, port=1883,
                 timeout=10, evidence=None):
        if not isinstance(broker,str) or not broker or any(c in broker for c in '/?#\r\n'):
            raise ValueError('Invalid MQTT broker hostname')
        if type(port) is not int or not 1 <= port <= 65535 or not 0 < timeout <= 60:
            raise ValueError('Invalid MQTT connection budget')
        self.broker,self.port,self.timeout = broker,port,timeout
        self.actor,self.evidence = actor,evidence
        self.sender,self.receiver = topic_id(actor),topic_id(cse_id)

    def exchange(self, path: str, *, attributes=None) -> dict:
        primitive = request_primitive(path,self.actor,'4',attributes=attributes)
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise TransportError('Optional paho-mqtt 2.1.0 missing; use standards image') from None
        req_topic = f'/oneM2M/req/{self.sender}/{self.receiver}/json'
        resp_topic = f'/oneM2M/resp/{self.sender}/{self.receiver}/json'
        state = {'connected':False,'subscribed':False,'failed':False,'payload':None}
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
            client_id='fr-' + uuid4().hex[:20], protocol=mqtt.MQTTv311,
            clean_session=True, reconnect_on_failure=False)
        client.connect_timeout = self.timeout
        def connected(c,u,f,reason,properties):
            if reason.is_failure:
                state['failed']=True
            else:
                state['connected']=True
                rc,_=c.subscribe(resp_topic,qos=1)
                if rc != mqtt.MQTT_ERR_SUCCESS:state['failed']=True
        def subscribed(c,u,mid,reasons,properties):
            state['subscribed']=bool(reasons) and all(not reason.is_failure for reason in reasons)
            if not state['subscribed']:state['failed']=True
        def received(c,u,message):
            if message.topic != resp_topic or message.retain or len(message.payload)>1024*1024:
                state['failed']=True
            elif state['payload'] is None:
                state['payload']=bytes(message.payload)
        client.on_connect,client.on_subscribe,client.on_message=connected,subscribed,received
        record={'binding':'oneM2M_MQTT','request_topic':req_topic,
                'response_topic':resp_topic,'request_primitive':primitive,'qos':1,'retain':False}
        started=time.monotonic()
        try:
            client.connect(self.broker,self.port,keepalive=30)
            deadline=time.monotonic()+self.timeout
            def wait(predicate):
                while not predicate():
                    if state['failed'] or time.monotonic()>=deadline:
                        raise TransportError('MQTT oneM2M exchange unavailable within budget')
                    if client.loop(timeout=min(.1,max(.001,deadline-time.monotonic()))) != mqtt.MQTT_ERR_SUCCESS:
                        raise TransportError('MQTT link lost; uncertain request is not replayed')
            wait(lambda:state['subscribed'])
            info=client.publish(req_topic,json.dumps(primitive,allow_nan=False),qos=1,retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:raise TransportError('MQTT publish failed')
            wait(lambda:state['payload'] is not None)
            # Preserve real denial/malformed primitive in private evidence too.
            try:record['response_primitive']=strict_json(state['payload'])
            except (ValueError,UnicodeDecodeError):record['response_parse']='INVALID_JSON'
            return validate_response(state['payload'],primitive)
        except (OSError,TimeoutError):
            record['error']='TransportError'
            raise TransportError('MQTT connection interrupted; no CREATE replay') from None
        except CSEError as exc:
            record.update(error=type(exc).__name__,rsc=exc.rsc)
            raise
        finally:
            client.disconnect()
            record['duration_ms']=round((time.monotonic()-started)*1000,3)
            if self.evidence:self.evidence.append('mqtt.jsonl',record)
