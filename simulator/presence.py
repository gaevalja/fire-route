"""Synthetic Wi-Fi/BLE presence scans derived from the simulated residents (UC-06 input).

Each scan publishes anonymous per-zone device counts. Whether a resident
carries a detectable device is fixed per resident; each scan detects a carried
device with a declared probability, and every covered zone can report one
false device with a declared probability. This is not RF positioning or device
tracking, and no device or resident identifier is published.
"""
from collections import Counter
import hashlib
import json

from simulator.access import load_sensing, sensing_hash, validate_sensing
from simulator.commands import utc_time

KIND_SCAN_BATCH = 'FireRoutePresenceScanBatch'
SENSOR_TYPE = 'PRESENCE_SCAN'
MAX_SCANS = 1000
SCAN_BATCH_FIELDS = {'schema_version','kind','event_id','incident_id','sequence_from','sequence_to','simulation_second',
                     'timestamp_utc','source','data_origin','sensing_policy_sha256','scanner_status','sensor_type',
                     'unit','scans'}


def chance(*parts):
    """Deterministic uniform value per trace seed and identity; reproducible across runs of one trace."""
    return int.from_bytes(hashlib.sha256('|'.join(map(str,parts)).encode()).digest()[:8],'big')/2**64


def covered_zones(navigation):
    """Zones a scanner can see: linked, non-exit zones (unlinked elevator shafts are excluded)."""
    return frozenset(n for n in navigation.nodes if n not in navigation.exits and navigation.adjacency.get(n))


class PresenceScanner:
    def __init__(self,navigation,sensing=None):
        self.navigation = navigation
        self.sensing = dict(load_sensing() if sensing is None else sensing)
        validate_sensing(self.sensing)
        self.policy_hash = sensing_hash(self.sensing)
        self.zones = covered_zones(navigation)

    def due(self,frame):
        return frame['simulation_second'] % self.sensing['presence_scan_interval_seconds'] == 0

    def observe(self,positions,frame):
        """One scan from the residents' last-reached nodes after this frame."""
        s,seed,sequence = self.sensing,frame['seed'],frame['sequence']
        counts = Counter()
        for resident,node in sorted(positions.items()):
            if node not in self.zones:
                continue
            if (chance(seed,resident,'carry') < s['device_carry_probability']
                    and chance(seed,resident,sequence,'detect') < s['device_detection_probability']):
                counts[node] += 1
        for zone in sorted(self.zones):
            if chance(seed,zone,sequence,'false') < s['false_detection_probability']:
                counts[zone] += 1
        return {'sequence':sequence,'simulation_second':frame['simulation_second'],
                'detections':{zone:count for zone,count in sorted(counts.items())}}

    def batch(self,scans,access_batch,source):
        """Scans aligned with one access batch's sequence range; the list may be empty."""
        first,last = access_batch['sequence_from'],access_batch['sequence_to']
        if any(not first <= scan['sequence'] <= last for scan in scans):
            raise ValueError('Presence scan outside the access batch range')
        return {'schema_version':1,'kind':KIND_SCAN_BATCH,'event_id':'presence-'+access_batch['event_id'],
                'incident_id':access_batch['incident_id'],'sequence_from':first,'sequence_to':last,
                'simulation_second':access_batch['simulation_second'],'timestamp_utc':access_batch['timestamp_utc'],
                'source':source,'data_origin':'SYNTHETIC','sensing_policy_sha256':self.policy_hash,
                'scanner_status':'OK','sensor_type':SENSOR_TYPE,'unit':'device','scans':list(scans)}


def parse_scan_batch(data,navigation):
    if not isinstance(data,dict) or set(data) != SCAN_BATCH_FIELDS:
        raise ValueError('Invalid presence scan fields')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != KIND_SCAN_BATCH:
        raise ValueError('Invalid presence scan schema')
    for key in ['event_id','incident_id','source','sensing_policy_sha256']:
        value = data[key]
        if not isinstance(value,str) or not value.strip() or len(value) > 256 or any(c in value for c in '\r\n'):
            raise ValueError('Invalid presence scan identity')
    if (data['data_origin'] != 'SYNTHETIC' or data['scanner_status'] != 'OK'
            or data['sensor_type'] != SENSOR_TYPE or data['unit'] != 'device'):
        raise ValueError('Presence scan must be synthetic anonymous device counts')
    first,last,second = data['sequence_from'],data['sequence_to'],data['simulation_second']
    if any(type(v) is not int for v in [first,last,second]) or not 1 <= first <= last or second < 0:
        raise ValueError('Invalid presence scan sequence')
    utc_time(data['timestamp_utc'])
    scans,zones,previous = data['scans'],covered_zones(navigation),0
    if not isinstance(scans,list) or len(scans) > MAX_SCANS:
        raise ValueError('Invalid presence scans')
    for scan in scans:
        if not isinstance(scan,dict) or set(scan) != {'sequence','simulation_second','detections'}:
            raise ValueError('Invalid presence scan entry')
        if (type(scan['sequence']) is not int or not first <= scan['sequence'] <= last or scan['sequence'] <= previous
                or type(scan['simulation_second']) is not int or not 0 <= scan['simulation_second'] <= second):
            raise ValueError('Invalid presence scan order')
        previous = scan['sequence']
        detections = scan['detections']
        if (not isinstance(detections,dict) or any(z not in zones for z in detections)
                or any(type(c) is not int or not 1 <= c <= 1000 for c in detections.values())):
            raise ValueError('Invalid presence detections')
    return json.loads(json.dumps(data))
