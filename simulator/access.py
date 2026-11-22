"""Synthetic access-passage sensing derived from the simulated residents.

The simulated residents are the ground truth. This gateway emits anonymous
passage events (no resident identity) and deterministically misses a declared
fraction of passages, so a downstream estimator never sees the truth. It is not
person detection, Wi-Fi/BLE positioning or a calibrated sensor model.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

from simulator.commands import utc_time
from simulator.scenario_frames import ROOT

KIND_BATCH = 'FireRouteAccessBatch'
SENSOR_TYPE = 'ACCESS_PASSAGE'
MAX_BATCH_EVENTS = 5000
BATCH_FIELDS = {'schema_version','kind','event_id','incident_id','sequence_from','sequence_to','simulation_second',
                'timestamp_utc','source','data_origin','sensing_policy_sha256','gateway_status','sensor_type','unit','events'}
EVENT_FIELDS = {'sensor_id','from_zone','to_zone','value','status','simulation_second'}


def load_sensing(path=None):
    path = Path(path) if path else ROOT/'fixtures/occupancy_assumptions.json'
    if not path.is_file():
        path = Path(sys.prefix)/'share/fire-route/fixtures/occupancy_assumptions.json'
    data = json.loads(path.read_text())
    validate_sensing(data)
    return data


def validate_sensing(data):
    probabilities = {'miss_probability','device_carry_probability','device_detection_probability','false_detection_probability',
                     'access_occupied_prior','access_empty_prior','high_probability','possible_probability'}
    required = probabilities|{'schema_version','model_id','provenance','checkpoint_coverage','prior','presence_coverage',
                              'presence_scan_interval_seconds','presence_scan_window'}
    if not isinstance(data,dict) or set(data) != required or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Unexpected occupancy assumptions schema')
    if (data['model_id'] != 'fire-route-access-occupancy-v1' or data['provenance'] != 'ASSUMED_NOT_CALIBRATED'
            or data['checkpoint_coverage'] != 'ALL_ZONE_BOUNDARIES' or data['prior'] != 'REGISTERED_PEOPLE_PER_ROOM'
            or data['presence_coverage'] != 'ALL_LINKED_ZONES'):
        raise ValueError('Occupancy assumptions must retain explicit provenance')
    for key in probabilities:
        p = data[key]
        # Error rates may be zero (ideal sensor); priors, rates of carriage/detection and thresholds may not.
        low = 0 <= p if key in {'miss_probability','false_detection_probability'} else 0 < p
        if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not (low and p < 1):
            raise ValueError('Invalid assumed probability')
    if (data['miss_probability'] >= 0.5 or data['false_detection_probability'] >= 0.5
            or data['access_empty_prior'] >= data['access_occupied_prior']
            or data['possible_probability'] >= data['high_probability']):
        raise ValueError('Invalid assumed probability ordering')
    if type(data['presence_scan_interval_seconds']) is not int or not 1 <= data['presence_scan_interval_seconds'] <= 600:
        raise ValueError('Invalid presence scan interval')
    if type(data['presence_scan_window']) is not int or not 1 <= data['presence_scan_window'] <= 20:
        raise ValueError('Invalid presence scan window')


def sensing_hash(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


def canonical_sha256(value):
    """Same canonical JSON digest as the project IPE uses for CIN content checks."""
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def sensor_id(a,b):
    x,y = sorted((a,b))
    return f'passage:{x}|{y}'


def missed(seed,resident_id,sequence,a,b,probability):
    """Deterministic per trace seed, so repeated runs of one trace miss the same passages."""
    token = f'{seed}|{resident_id}|{sequence}|{a}|{b}'.encode()
    return int.from_bytes(hashlib.sha256(token).digest()[:8],'big')/2**64 < probability


class AccessGateway:
    def __init__(self,navigation,sensing=None):
        self.navigation = navigation
        self.sensing = dict(load_sensing() if sensing is None else sensing)
        validate_sensing(self.sensing)
        self.policy_hash = sensing_hash(self.sensing)
        self.truth_passages = 0
        self.missed_passages = 0

    def observe(self,before,after,frame):
        """One accepted frame's anonymous events from last-reached-node changes."""
        events = []
        for resident in sorted(before):
            a,b = before[resident],after.get(resident)
            if b is None or a == b:
                continue
            if b not in self.navigation.adjacency.get(a,{}):
                raise ValueError('Non-adjacent synthetic passage')
            self.truth_passages += 1
            if missed(frame['seed'],resident,frame['sequence'],a,b,self.sensing['miss_probability']):
                self.missed_passages += 1
                continue
            events.append({'sensor_id':sensor_id(a,b),'from_zone':a,'to_zone':b,'value':1,'status':'OK',
                           'simulation_second':frame['simulation_second']})
        # Sorting by sensor removes the resident ordering from the published record.
        events.sort(key=lambda e:(e['sensor_id'],e['from_zone'],e['to_zone']))
        return {'sequence':frame['sequence'],'simulation_second':frame['simulation_second'],
                'timestamp_utc':frame['timestamp_utc'],'frame_event_id':frame['event_id'],'events':events}

    def batch(self,frames,incident_id,source):
        if not frames:
            raise ValueError('No observed frames')
        sequences = [f['sequence'] for f in frames]
        if sequences != list(range(sequences[0],sequences[0]+len(sequences))):
            raise ValueError('Access frames must be consecutive')
        events = [e for f in frames for e in f['events']]
        if len(events) > MAX_BATCH_EVENTS:
            raise ValueError('Access batch exceeds event limit')
        last = frames[-1]
        return {'schema_version':1,'kind':KIND_BATCH,'event_id':'access-'+last['frame_event_id'],'incident_id':incident_id,
                'sequence_from':sequences[0],'sequence_to':sequences[-1],'simulation_second':last['simulation_second'],
                'timestamp_utc':last['timestamp_utc'],'source':source,'data_origin':'SYNTHETIC',
                'sensing_policy_sha256':self.policy_hash,'gateway_status':'OK','sensor_type':SENSOR_TYPE,
                'unit':'person','events':events}


def parse_batch(data,navigation):
    """Strict contract shared by the IPE and the MEC occupancy service."""
    if not isinstance(data,dict) or set(data) != BATCH_FIELDS:
        raise ValueError('Invalid access batch fields')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != KIND_BATCH:
        raise ValueError('Invalid access batch schema')
    for key in ['event_id','incident_id','source','sensing_policy_sha256']:
        value = data[key]
        if not isinstance(value,str) or not value.strip() or len(value) > 256 or any(c in value for c in '\r\n'):
            raise ValueError('Invalid access batch identity')
    if (data['data_origin'] != 'SYNTHETIC' or data['gateway_status'] != 'OK'
            or data['sensor_type'] != SENSOR_TYPE or data['unit'] != 'person'):
        raise ValueError('Access batch must be synthetic passage counts')
    first,last,second = data['sequence_from'],data['sequence_to'],data['simulation_second']
    if any(type(v) is not int for v in [first,last,second]) or not 1 <= first <= last or second < 0:
        raise ValueError('Invalid access batch sequence')
    utc_time(data['timestamp_utc'])
    events = data['events']
    if not isinstance(events,list) or len(events) > MAX_BATCH_EVENTS:
        raise ValueError('Invalid access events')
    for event in events:
        if not isinstance(event,dict) or set(event) != EVENT_FIELDS:
            raise ValueError('Invalid access event fields')
        a,b = event['from_zone'],event['to_zone']
        if not isinstance(a,str) or not isinstance(b,str) or a in navigation.exits or b not in navigation.adjacency.get(a,{}):
            raise ValueError('Access event is not a known zone boundary')
        if (event['sensor_id'] != sensor_id(a,b) or type(event['value']) is not int or event['value'] != 1
                or event['status'] != 'OK' or type(event['simulation_second']) is not int
                or not 0 <= event['simulation_second'] <= second):
            raise ValueError('Invalid access event values')
    return json.loads(json.dumps(data))
