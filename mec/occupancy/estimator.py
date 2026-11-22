"""Access-event occupancy corrected by Wi-Fi/BLE presence scans (interim report UC-05/UC-06).

Inputs are only anonymous passage batches and anonymous per-zone device counts.
The registered room prior comes from the declared evacuation assumptions;
nothing here reads the simulated residents (ground truth). Output is a
per-zone occupancy probability with its evidence, never an exact presence.

Per zone, the access count sets a prior (occupied if count >= 1). Scans taken
since the zone's last passage update it with a naive-Bayes likelihood ratio:

    P(scans | occupied by n) = sum_j Bin(j; n, carry) * prod_scan P(result | j carried devices)
    P(scans | empty)         = prod_scan (false if detected else 1 - false)

where one scan detects with probability 1 - (1 - detect)^j * (1 - false). All
parameters are declared, uncalibrated assumptions.
"""
from collections import deque
import hashlib
import json
from math import comb

from mec.risk.evacuation import Navigation
from simulator.access import load_sensing, sensing_hash, validate_sensing
from simulator.presence import covered_zones

ESTIMATOR_ID = 'fire-route-access-presence-bayes-v1'
KIND_ESTIMATE = 'FireRouteOccupancyEstimate'
LEVELS = ('HIGH','POSSIBLE','LOW')
BASES = {'PASSAGE','REGISTERED_PRIOR','PRESENCE_SCAN'}


class BatchOrderError(ValueError):
    """Rejected before any count changes: next consecutive batch or explicit reset required."""


class OccupancyEstimator:
    def __init__(self,navigation=None,sensing=None):
        self.navigation = navigation or Navigation()
        self.sensing = dict(load_sensing() if sensing is None else sensing)
        validate_sensing(self.sensing)
        per_room = self.navigation.assumptions['people_per_room']
        rooms = sorted(n for n,m in self.navigation.metadata.items() if m['kind'] == 'room')
        self.policy_hash = hashlib.sha256(json.dumps({'estimator':ESTIMATOR_ID,'sensing':sensing_hash(self.sensing),
            'people_per_room':per_room,'evacuation_policy':self.navigation.policy_hash},sort_keys=True).encode()).hexdigest()
        self.covered = covered_zones(self.navigation)
        self.counts = {n:0 for n in self.navigation.nodes if n not in self.navigation.exits}
        for room in rooms:
            self.counts[room] = per_room
        self.basis = {room:'REGISTERED_PRIOR' for room in rooms if per_room > 0}
        self.prior_total = per_room*len(rooms)
        self.last_passage = {}
        self.scans = deque(maxlen=self.sensing['presence_scan_window'])
        self.scans_applied = 0
        self.applied = 0
        self.detected_exits = 0
        self.unmatched_departures = 0
        self.incident = None
        self.last_batch = None

    def apply(self,batch,presence=None):
        """Apply one parsed access batch and its aligned parsed scan batch (None = no scanner)."""
        if self.incident is not None and batch['incident_id'] != self.incident:
            raise BatchOrderError('INCIDENT_CHANGED_WITHOUT_RESET')
        if batch['sequence_from'] != self.applied+1:
            raise BatchOrderError('SEQUENCE_GAP_OR_REPLAY')
        if self.last_batch is not None and batch['simulation_second'] <= self.last_batch['simulation_second']:
            raise BatchOrderError('NON_MONOTONIC_SIMULATION_TIME')
        if batch['sensing_policy_sha256'] != sensing_hash(self.sensing):
            raise BatchOrderError('SENSING_POLICY_DIFFERS')
        if presence is not None and (any(presence[k] != batch[k] for k in ('incident_id','sequence_from','sequence_to'))
                                     or presence['sensing_policy_sha256'] != batch['sensing_policy_sha256']):
            raise BatchOrderError('PRESENCE_SCANS_NOT_ALIGNED')
        # Passages and scans are merged in time order: a scan sees positions after its frame.
        events = sorted(batch['events'],key=lambda e:e['simulation_second'])
        scans = presence['scans'] if presence is not None else []
        index = 0
        for scan in scans:
            while index < len(events) and events[index]['simulation_second'] <= scan['simulation_second']:
                self.passage(events[index]);index += 1
            self.scans.append((scan['simulation_second'],dict(scan['detections'])))
            self.scans_applied += 1
        for event in events[index:]:
            self.passage(event)
        self.incident = batch['incident_id']
        self.applied = batch['sequence_to']
        self.last_batch = batch

    def passage(self,event):
        a,b,second = event['from_zone'],event['to_zone'],event['simulation_second']
        if self.counts[a] > 0:
            self.counts[a] -= 1
        else:
            # Evidence that an earlier entry into this zone was missed.
            self.unmatched_departures += 1
        self.basis[a] = 'PASSAGE'
        self.last_passage[a] = second
        if b in self.navigation.exits:
            self.detected_exits += 1
        else:
            self.counts[b] += 1
            self.basis[b] = 'PASSAGE'
            self.last_passage[b] = second

    def evidence(self,zone):
        """Scan results for this zone taken at or after its last passage (inside the window)."""
        since = self.last_passage.get(zone,-1)
        return [(second,detections.get(zone,0)) for second,detections in self.scans if second >= since]

    def probability(self,zone):
        s = self.sensing
        count = self.counts.get(zone,0)
        prior = s['access_occupied_prior'] if count >= 1 else s['access_empty_prior']
        if zone not in self.covered:
            return prior,[]
        scans = self.evidence(zone)
        carry,detect,false = s['device_carry_probability'],s['device_detection_probability'],s['false_detection_probability']
        empty = 1.0
        for _,devices in scans:
            empty *= false if devices else 1-false
        people = max(1,count)
        occupied = 0.0
        for carried in range(people+1):
            weight = comb(people,carried)*carry**carried*(1-carry)**(people-carried)
            silent = (1-detect)**carried*(1-false)
            for _,devices in scans:
                weight *= 1-silent if devices else silent
            occupied += weight
        if empty <= 0:
            return 1.0,scans
        odds = prior/(1-prior)*occupied/empty
        return odds/(1+odds),scans

    def level(self,probability):
        if probability >= self.sensing['high_probability']:
            return 'HIGH'
        return 'POSSIBLE' if probability >= self.sensing['possible_probability'] else 'LOW'

    def snapshot(self):
        if self.last_batch is None:
            raise ValueError('No applied access batch')
        zones = []
        for zone in sorted(self.counts):
            count = self.counts[zone]
            probability,scans = self.probability(zone)
            level = self.level(probability)
            # Count-backed zones are always listed (LOW included); scan-only zones need POSSIBLE.
            if count < 1 and level == 'LOW':
                continue
            seen = [second for second,devices in scans if devices]
            candidates = ([self.last_passage[zone]] if zone in self.last_passage else [])+seen
            last = max(candidates) if candidates else None
            zones.append({'zone_id':zone,
                'estimated_count':count if count >= 1 else max(1,max(devices for _,devices in scans)),
                'likelihood':level,'probability':round(probability,3),'last_detection_second':last,
                'basis':self.basis.get(zone,'PASSAGE') if count >= 1 else 'PRESENCE_SCAN',
                'evidence':{'access_count':count,'scans':len(scans),'detections':len(seen)}})
        return {'schema_version':1,'kind':KIND_ESTIMATE,'incident_id':self.incident,
                'source_event_id':self.last_batch['event_id'],'applied_through_sequence':self.applied,
                'simulation_second':self.last_batch['simulation_second'],'timestamp_utc':self.last_batch['timestamp_utc'],
                'estimator_id':ESTIMATOR_ID,'estimator_policy_sha256':self.policy_hash,
                'data_origin':'SYNTHETIC','provenance':'ASSUMED_NOT_CALIBRATED',
                # Building headcount uses exit passages only; the zone sum is reported separately.
                'registered_prior_total':self.prior_total,'estimated_remaining':max(0,self.prior_total-self.detected_exits),
                'zone_count_total':sum(z['estimated_count'] for z in zones),'presence_scans':self.scans_applied,
                'detected_exits':self.detected_exits,'unmatched_departures':self.unmatched_departures,'zones':zones}


def validate_estimate(estimate,navigation):
    """Bounded shape check before an estimate is published or displayed."""
    fields = {'schema_version','kind','incident_id','source_event_id','applied_through_sequence','simulation_second',
              'timestamp_utc','estimator_id','estimator_policy_sha256','data_origin','provenance','registered_prior_total',
              'estimated_remaining','zone_count_total','presence_scans','detected_exits','unmatched_departures','zones'}
    if not isinstance(estimate,dict) or set(estimate) != fields or estimate['kind'] != KIND_ESTIMATE:
        raise ValueError('Invalid occupancy estimate fields')
    if estimate['data_origin'] != 'SYNTHETIC' or estimate['provenance'] != 'ASSUMED_NOT_CALIBRATED':
        raise ValueError('Occupancy estimate must stay synthetic and assumed')
    numbers = ['applied_through_sequence','simulation_second','registered_prior_total','estimated_remaining',
               'zone_count_total','presence_scans','detected_exits','unmatched_departures']
    if any(type(estimate[k]) is not int or estimate[k] < 0 for k in numbers):
        raise ValueError('Invalid occupancy estimate counts')
    zones = estimate['zones']
    if not isinstance(zones,list) or len(zones) > len(navigation.nodes):
        raise ValueError('Invalid occupancy zones')
    seen = set()
    entry = {'zone_id','estimated_count','likelihood','probability','last_detection_second','basis','evidence'}
    for zone in zones:
        evidence = zone.get('evidence') if isinstance(zone,dict) else None
        if (not isinstance(zone,dict) or set(zone) != entry
                or zone['zone_id'] not in navigation.nodes or zone['zone_id'] in navigation.exits or zone['zone_id'] in seen
                or type(zone['estimated_count']) is not int or zone['estimated_count'] < 1
                or zone['likelihood'] not in LEVELS or zone['basis'] not in BASES
                or isinstance(zone['probability'],bool) or not isinstance(zone['probability'],(int,float))
                or not 0 <= zone['probability'] <= 1
                or (zone['last_detection_second'] is not None and type(zone['last_detection_second']) is not int)
                or not isinstance(evidence,dict) or set(evidence) != {'access_count','scans','detections'}
                or any(type(v) is not int or v < 0 for v in evidence.values())):
            raise ValueError('Invalid occupancy zone entry')
        seen.add(zone['zone_id'])
    if (sum(z['estimated_count'] for z in zones) != estimate['zone_count_total']
            or estimate['estimated_remaining'] != max(0,estimate['registered_prior_total']-estimate['detected_exits'])):
        raise ValueError('Occupancy estimate total differs')
    return estimate


def prioritize(zones,hazard_zones,blocked):
    """Responder check order: probability level first; within it blocked/hazardous zones, then probability."""
    hazards = {z['zone_id']:z for z in hazard_zones}
    blocked = set(blocked)
    def hazard(zone):
        h = hazards.get(zone,{})
        return {'blocked':zone in blocked,'collapsed':bool(h.get('collapsed',False)),
                'fire_index':h.get('fire_index',0),'smoke_index':h.get('smoke_index',0)}
    def key(zone):
        h = hazard(zone['zone_id'])
        return (LEVELS.index(zone['likelihood']),0 if h['blocked'] or h['collapsed'] else 1,
                -max(h['fire_index'],h['smoke_index']),-zone['probability'],-zone['estimated_count'],zone['zone_id'])
    return [{**zone,'rank':rank,'hazard':hazard(zone['zone_id'])} for rank,zone in enumerate(sorted(zones,key=key),1)]


def evaluate(zones,truth_zones,exits=frozenset({'EXIT_A','EXIT_B'})):
    """Compare with the simulated ground truth; responder-only evidence, not a field accuracy claim."""
    estimated = {z['zone_id']:z['estimated_count'] for z in zones}
    actual = {z['zone_id']:z['remaining_count'] for z in truth_zones if z['remaining_count'] > 0 and z['zone_id'] not in exits}
    union = set(estimated)|set(actual)
    result = {'truth_source':'SYNTHETIC_SIMULATION_GROUND_TRUTH','truth_zones':len(actual),
              'detected_zones':len(set(estimated)&set(actual)),'missed_zones':len(set(actual)-set(estimated)),
              'false_zones':len(set(estimated)-set(actual)),
              'count_abs_error':sum(abs(estimated.get(z,0)-actual.get(z,0)) for z in union),
              'truth_remaining':sum(actual.values()),'zone_count_total':sum(estimated.values())}
    for level in LEVELS:
        names = {z['zone_id'] for z in zones if z['likelihood'] == level}
        result[level.lower()+'_zones'] = len(names)
        result[level.lower()+'_true_zones'] = len(names&set(actual))
    return result
