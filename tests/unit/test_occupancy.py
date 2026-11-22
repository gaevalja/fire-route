"""Access-event + presence-scan occupancy and room guidance fixtures; never actual CSE/MEC evidence."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.config import Settings
from backend.scenario_core import ScenarioSession, zone_routes
from backend.scenario_demo import ScenarioApp
from mec.interworking.client import verified_estimate
from mec.interworking.worker import analyse_occupancy, decode_occupancy_request, digest
from mec.occupancy.estimator import BatchOrderError, OccupancyEstimator, evaluate, prioritize, validate_estimate
from mec.occupancy.service import OccupancyJournal, RETAINED_INCIDENTS, parse_unit
from mec.risk.evacuation import Navigation, load_assumptions
from mec.service_client import OCCUPANCY_ENDPOINT, OCCUPANCY_SERVICE, RISK_ENDPOINT, ServiceError, discover_service, register_service
from onem2m.bootstrap import ACCESS_LABEL, PRESENCE_LABEL, bootstrap
from onem2m.client import CSEClient, ProtocolError, TransportError
from simulator.access import AccessGateway, canonical_sha256, load_sensing, missed, parse_batch, sensor_id, validate_sensing
from simulator.evacuation import Evacuation
from simulator.events import utc_now
from simulator.presence import PresenceScanner, covered_zones, parse_scan_batch
from simulator.scenario_frames import PROFILE, ZONES, emission, source_manifest

HASH = source_manifest()['bundle_sha256']
APP = '00000000-0000-4000-8000-0000000000a1'
SID = '00000000-0000-4000-8000-0000000000a2'
NAV = Navigation()
SENSING = load_sensing()


def frame(second=0, *, changes=None):
    raw = {'schema_version':1,'profile_id':PROFILE,'source_manifest_sha256':HASH,'seed':59,'wind_mps':5,
           'simulation_second':second,'ended':False,
           'zones':[{'zone_id':n,'fire_index':0,'smoke_index':0,'collapsed':False} for n in ZONES]}
    for zone in raw['zones']:
        zone.update((changes or {}).get(zone['zone_id'],{}))
    return emission(raw,'inc-unit','unit:source',HASH)


def config(**overrides):
    data = load_assumptions()
    data.update(people_per_room=1,walk_speed_min_mps=1,walk_speed_max_mps=1,slow_fraction=0,
                departure_delay_min_s=0,departure_delay_max_s=0)
    data.update(overrides)
    return data


def frame_meta(sequence, second=None, stamp=None):
    return {'seed':59,'sequence':sequence,'simulation_second':sequence-1 if second is None else second,
            'timestamp_utc':stamp or utc_now(),'event_id':f'frame-{sequence}'}


def batch(sequence_from, sequence_to, events=(), *, incident='inc-unit', stamp=None):
    """Access batch; frame s has simulation_second s-1 and events happen in the last frame."""
    stamp = stamp or utc_now()
    frames = [{'sequence':s,'simulation_second':s-1,'timestamp_utc':stamp,'frame_event_id':f'frame-{s}',
               'events':[]} for s in range(sequence_from,sequence_to+1)]
    for a,b in events:
        frames[-1]['events'].append({'sensor_id':sensor_id(a,b),'from_zone':a,'to_zone':b,'value':1,'status':'OK',
                                     'simulation_second':sequence_to-1})
    return AccessGateway(NAV,SENSING).batch(frames,incident,'unit:access-gateway')


def scans(access, detections_by_sequence=None):
    """Presence batch aligned with an access batch; {sequence: {zone: devices}}."""
    entries = [{'sequence':s,'simulation_second':s-1,'detections':dict(d)}
               for s,d in sorted((detections_by_sequence or {}).items())]
    return PresenceScanner(NAV,SENSING).batch(entries,access,'unit:presence-scanner')


def unit(sequence_from, sequence_to, events=(), detections=None, **kw):
    access = batch(sequence_from,sequence_to,events,**kw)
    return {'access':access,'presence':scans(access,detections)}


def apply_units(estimator, *units):
    for value in units:
        parsed = parse_unit(value,NAV)
        estimator.apply(parsed['access'],parsed['presence'])
    return {z['zone_id']:z for z in validate_estimate(estimator.snapshot(),NAV)['zones']}


class GatewayTests(unittest.TestCase):
    def test_passages_are_anonymous_adjacent_and_missed_deterministically(self):
        none = AccessGateway(NAV,{**SENSING,'miss_probability':0})
        observed = none.observe({'p1':'F7-R3','p2':'F7-C3','p3':'F7-C3'},
                                {'p1':'F7-C3','p2':'F7-C3','p3':'F7-C2'},frame_meta(5))
        self.assertEqual([(e['from_zone'],e['to_zone']) for e in observed['events']],[('F7-C3','F7-C2'),('F7-R3','F7-C3')])
        self.assertNotIn('p1',json.dumps(observed))
        self.assertEqual(none.truth_passages,2)
        lossy = AccessGateway(NAV,{**SENSING,'miss_probability':0.49})
        before = {f'p{i}':'F7-R3' for i in range(400)};after = {k:'F7-C3' for k in before};meta = frame_meta(9)
        first = lossy.observe(before,after,meta)
        again = AccessGateway(NAV,{**SENSING,'miss_probability':0.49}).observe(before,after,meta)
        self.assertEqual(first,again)
        self.assertEqual(len(first['events'])+lossy.missed_passages,400)
        self.assertTrue(100<lossy.missed_passages<300)
        self.assertIn(missed(59,'p0',9,'F7-R3','F7-C3',0.49),{True,False})

    def test_non_adjacent_passage_is_rejected(self):
        with self.assertRaises(ValueError):
            AccessGateway(NAV,SENSING).observe({'p':'F7-R3'},{'p':'F2-R1'},frame_meta(2))

    def test_batch_requires_consecutive_frames_and_parses(self):
        value = batch(1,3,[('F7-R3','F7-C3')])
        self.assertEqual(parse_batch(value,NAV),value)
        self.assertEqual(value['events'][0]['sensor_id'],'passage:F7-C3|F7-R3')
        with self.assertRaises(ValueError):
            AccessGateway(NAV,SENSING).batch([{'sequence':1,'events':[]},{'sequence':3,'events':[]}],'inc','src')

    def test_parse_rejects_unknown_boundaries_values_and_fields(self):
        good = batch(1,1,[('F7-R3','F7-C3')])
        for mutate in [lambda b:b['events'][0].update(to_zone='F2-R1'),
                       lambda b:b['events'][0].update(sensor_id='passage:x|y'),
                       lambda b:b['events'][0].update(value=2),
                       lambda b:b['events'][0].update(from_zone='EXIT_A',to_zone='F1-L'),
                       lambda b:b.update(data_origin='MEASURED'),
                       lambda b:b.update(extra=1),
                       lambda b:b.update(sequence_from=0)]:
            bad = copy.deepcopy(good);mutate(bad)
            with self.assertRaises(ValueError):parse_batch(bad,NAV)

    def test_assumptions_keep_provenance_and_probability_order(self):
        for change in [{'provenance':'MEASURED'},{'device_carry_probability':1},{'access_empty_prior':0.9},
                       {'possible_probability':0.8},{'presence_scan_window':0}]:
            with self.assertRaises(ValueError):validate_sensing({**SENSING,**change})


class PresenceScannerTests(unittest.TestCase):
    def test_ideal_scanner_counts_covered_occupants_only(self):
        ideal = PresenceScanner(NAV,{**SENSING,'device_carry_probability':0.999999,'device_detection_probability':0.999999,
                                     'false_detection_probability':0})
        scan = ideal.observe({'resident-x1':'F7-R3','resident-x2':'F7-R3','resident-x3':'EXIT_A','resident-x4':'F2-E'},frame_meta(11))
        self.assertEqual(scan['detections'],{'F7-R3':2})
        self.assertNotIn('F2-E',covered_zones(NAV));self.assertNotIn('EXIT_A',covered_zones(NAV))
        self.assertNotIn('resident-x',json.dumps(scan))

    def test_carriage_is_persistent_detection_and_false_devices_are_deterministic(self):
        scanner = PresenceScanner(NAV,{**SENSING,'device_detection_probability':0.999999,'false_detection_probability':0})
        people = {f'p{i}':'F7-R3' for i in range(200)}
        counts = [scanner.observe(people,frame_meta(s))['detections'].get('F7-R3',0) for s in (11,21,31)]
        self.assertEqual(len(set(counts)),1)  # Same carriers every scan when detection is ~certain.
        self.assertTrue(150<counts[0]<200)     # About 90% carry a device.
        noisy = PresenceScanner(NAV,{**SENSING,'false_detection_probability':0.3})
        self.assertEqual(noisy.observe({},frame_meta(41)),noisy.observe({},frame_meta(41)))
        self.assertTrue(10<len(noisy.observe({},frame_meta(41))['detections'])<120)
        self.assertTrue(scanner.due(frame_meta(11,second=10)));self.assertFalse(scanner.due(frame_meta(12,second=11)))

    def test_scan_batch_contract(self):
        access = batch(1,3)
        value = scans(access,{2:{'F7-R3':1}})
        self.assertEqual(parse_scan_batch(value,NAV),value)
        for mutate in [lambda b:b['scans'][0]['detections'].update({'F2-E':1}),
                       lambda b:b['scans'][0]['detections'].update({'F7-R3':0}),
                       lambda b:b['scans'][0].update(sequence=9),
                       lambda b:b.update(unit='person')]:
            bad = copy.deepcopy(value);mutate(bad)
            with self.assertRaises(ValueError):parse_scan_batch(bad,NAV)
        with self.assertRaises(ValueError):PresenceScanner(NAV,SENSING).batch([{'sequence':7}],access,'src')
        other = scans(batch(1,4));other['sequence_to'] = 3
        with self.assertRaises(ValueError):parse_unit({'access':batch(1,4),'presence':other},NAV)


class EstimatorTests(unittest.TestCase):
    def test_prior_departure_exit_and_unmatched_counts(self):
        zones = apply_units(OccupancyEstimator(NAV,SENSING),unit(1,4,[('F7-R3','F7-C3'),('F1-L','EXIT_A')]))
        result = OccupancyEstimator(NAV,SENSING);result.apply(batch(1,4,[('F7-R3','F7-C3'),('F1-L','EXIT_A')]))
        snapshot = validate_estimate(result.snapshot(),NAV)
        self.assertEqual(zones['F7-R3']['estimated_count'],1);self.assertEqual(zones['F7-C3']['estimated_count'],1)
        self.assertEqual(zones['F2-R1']['basis'],'REGISTERED_PRIOR')
        self.assertEqual(snapshot['detected_exits'],1);self.assertEqual(snapshot['unmatched_departures'],1)
        self.assertEqual(snapshot['estimated_remaining'],169)  # Building headcount: prior - detected exits.
        self.assertEqual(snapshot['zone_count_total'],170)     # Without scans every count-backed zone is listed.
        self.assertNotIn('F1-L',zones)
        self.assertEqual(zones['F2-R1']['likelihood'],'HIGH');self.assertEqual(zones['F2-R1']['probability'],0.8)

    def test_silent_scans_refute_a_count_and_detections_confirm_it(self):
        entry = unit(1,4,[('F7-R3','F7-C3')])
        silent = apply_units(OccupancyEstimator(NAV,SENSING),entry,unit(5,8,detections={5:{},6:{},7:{}}))
        self.assertEqual(silent['F7-C3']['likelihood'],'LOW')  # Count kept, listed, but scans disagree.
        self.assertAlmostEqual(silent['F7-C3']['probability'],0.288,places=3)
        self.assertEqual(silent['F7-C3']['evidence'],{'access_count':1,'scans':3,'detections':0})
        seen = apply_units(OccupancyEstimator(NAV,SENSING),entry,unit(5,8,detections={5:{'F7-C3':1},6:{},7:{'F7-C3':1}}))
        self.assertEqual(seen['F7-C3']['likelihood'],'HIGH');self.assertEqual(seen['F7-C3']['last_detection_second'],6)

    def test_scans_find_missed_entries_and_ignore_evidence_before_the_last_passage(self):
        once = apply_units(OccupancyEstimator(NAV,SENSING),unit(1,3,detections={2:{'F9-C2':1}}))
        self.assertEqual((once['F9-C2']['likelihood'],once['F9-C2']['basis']),('POSSIBLE','PRESENCE_SCAN'))
        twice = apply_units(OccupancyEstimator(NAV,SENSING),unit(1,3,detections={2:{'F9-C2':1},3:{'F9-C2':2}}))
        self.assertEqual(twice['F9-C2']['likelihood'],'HIGH');self.assertEqual(twice['F9-C2']['estimated_count'],2)
        refuted = apply_units(OccupancyEstimator(NAV,SENSING),unit(1,3,detections={2:{'F9-C2':1}}),
                              unit(4,6,detections={4:{},5:{}}))
        self.assertNotIn('F9-C2',refuted)  # Scan-only zones need at least POSSIBLE to be listed.
        before = apply_units(OccupancyEstimator(NAV,SENSING),unit(1,4,[('F7-R3','F7-C3')],detections={1:{'F7-R3':2}}))
        self.assertEqual(before['F7-R3']['evidence']['scans'],0)  # Scan at second 0 predates the departure at 3.

    def test_gap_replay_incident_policy_and_misaligned_scans_are_rejected_without_change(self):
        estimator = OccupancyEstimator(NAV,SENSING)
        estimator.apply(batch(1,2))
        before = copy.deepcopy(estimator.snapshot())
        for bad in [batch(4,4),batch(1,2),batch(3,3,incident='other')]:
            with self.assertRaises(BatchOrderError):estimator.apply(bad)
        other = batch(3,3);other['sensing_policy_sha256'] = '0'*64
        with self.assertRaises(BatchOrderError):estimator.apply(other)
        with self.assertRaises(BatchOrderError):estimator.apply(batch(3,3),scans(batch(3,4)))
        self.assertEqual(estimator.snapshot(),before)

    def test_priority_orders_levels_then_hazard_and_evaluation_reports_each_level(self):
        zones = [{'zone_id':'F2-R1','estimated_count':2,'likelihood':'HIGH','probability':0.9},
                 {'zone_id':'F7-R3','estimated_count':1,'likelihood':'POSSIBLE','probability':0.5},
                 {'zone_id':'F5-R2','estimated_count':1,'likelihood':'HIGH','probability':0.75},
                 {'zone_id':'F3-R1','estimated_count':1,'likelihood':'LOW','probability':0.2}]
        hazards = [{'zone_id':'F5-R2','fire_index':40,'smoke_index':10,'collapsed':False}]
        ranked = prioritize(zones,hazards,['F7-R3','F3-R1'])
        self.assertEqual([z['zone_id'] for z in ranked],['F5-R2','F2-R1','F7-R3','F3-R1'])
        self.assertEqual(ranked[0]['hazard']['fire_index'],40);self.assertTrue(ranked[2]['hazard']['blocked'])
        result = evaluate(zones,[{'zone_id':'F2-R1','remaining_count':1},{'zone_id':'F9-R9','remaining_count':2},
                                 {'zone_id':'F3-R1','remaining_count':1},{'zone_id':'EXIT_A','remaining_count':5}])
        self.assertEqual((result['truth_zones'],result['detected_zones'],result['missed_zones'],result['false_zones']),(3,2,1,2))
        self.assertEqual((result['high_zones'],result['high_true_zones'],result['possible_zones'],result['possible_true_zones'],
                          result['low_zones'],result['low_true_zones']),(2,1,1,0,1,1))


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'occupancy.db'

    def test_idempotent_catch_up_restart_and_conflict(self):
        journal = OccupancyJournal(self.path,NAV,SENSING)
        one,two = unit(1,2,[('F7-R3','F7-C3')],{1:{'F7-R3':1}}),unit(3,3,[('F7-C3','F7-C2')])
        first = journal.apply_many([one])
        self.assertEqual(journal.apply_many([one,two])['applied_through_sequence'],3)
        restarted = OccupancyJournal(self.path,NAV,SENSING)
        self.assertEqual(restarted.apply(two),journal.apply(two))
        self.assertEqual(restarted.apply(one),first)
        self.assertEqual(first['presence_scans'],1)
        conflict = copy.deepcopy(two);conflict['access']['events'] = []
        with self.assertRaises(BatchOrderError):restarted.apply(conflict)
        with self.assertRaises(BatchOrderError):restarted.apply(unit(9,9))

    def test_only_newest_unit_must_be_fresh(self):
        journal = OccupancyJournal(self.path,NAV,SENSING)
        old = unit(1,1,stamp='2020-01-01T00:00:00Z')
        with self.assertRaises(ValueError):journal.apply_many([old])
        self.assertEqual(journal.apply_many([old,unit(2,2)])['applied_through_sequence'],2)
        with self.assertRaises(ValueError):journal.apply_many([])
        with self.assertRaises(ValueError):journal.apply(batch(1,1))  # A bare access batch is not a unit.

    def test_retention_keeps_newest_incidents_and_never_prunes_current(self):
        journal = OccupancyJournal(self.path,NAV,SENSING)
        for index in range(RETAINED_INCIDENTS+3):
            journal.apply(unit(1,1,incident=f'inc-{index}'))
        db = sqlite3.connect(self.path)
        try:
            names = {row[0] for row in db.execute('SELECT incident FROM incidents')}
        finally:db.close()
        self.assertEqual(len(names),RETAINED_INCIDENTS)
        self.assertIn(f'inc-{RETAINED_INCIDENTS+2}',names);self.assertNotIn('inc-0',names)


class InterworkingTests(unittest.TestCase):
    def setUp(self):
        self.unit = unit(1,2,[('F7-R3','F7-C3')],{2:{'F7-C3':1}})
        access,presence = self.unit['access'],self.unit['presence']
        self.ref = {'path':'/cse/fr__AccessGatewayAE/passages/access-2','ri':'cin-1','content_sha256':canonical_sha256(access),
                    **{k:access[k] for k in ['event_id','incident_id','sequence_from','sequence_to','timestamp_utc']},
                    'presence':{'path':'/cse/fr__PresenceScannerAE/scans/presence-2','ri':'cin-2',
                                'content_sha256':canonical_sha256(presence)}}
        self.document = {'schema_version':1,'kind':'FireRouteOccupancyRequest','event_id':'occ-'+'a'*32,'batches':[self.ref]}
        self.stored = {self.ref['path']:('cin-1',access),self.ref['presence']['path']:('cin-2',presence)}
        self.client = Mock();self.client.resource.side_effect = CSEClient.resource
        self.client.retrieve.side_effect = lambda path:{'m2m:cin':{'ty':4,'ri':self.stored[path][0],'con':json.dumps(self.stored[path][1])}}
        self.platform = Mock();self.platform.call.return_value = [{'serName':OCCUPANCY_SERVICE,'serInstanceId':SID,
            'state':'ACTIVE','serializer':'JSON','transportInfo':{'endpoint':{'uris':[OCCUPANCY_ENDPOINT]}}}]
        estimator = OccupancyEstimator(NAV,SENSING);estimator.apply(access,presence)
        self.estimate = estimator.snapshot()
        def provider(method,path,body=None,**kw):
            if method=='GET':return {'registration':{'app_id':APP,'service_id':SID}}
            return {'state':'ACCEPTED','estimate':self.estimate}
        self.provider = Mock();self.provider.call.side_effect = provider

    def test_request_contract(self):
        self.assertEqual(decode_occupancy_request(self.document).event_id,self.document['event_id'])
        for mutate in [lambda d:d.update(event_id='occ-x'),lambda d:d.update(batches=[]),
                       lambda d:d['batches'].append({**self.ref,'sequence_from':5,'sequence_to':5}),
                       lambda d:d['batches'][0].update(content_sha256='zz'),lambda d:d.update(kind='FireRouteRiskRequest'),
                       lambda d:d['batches'][0].pop('presence'),lambda d:d['batches'][0]['presence'].update(path='relative')]:
            bad = copy.deepcopy(self.document);mutate(bad)
            with self.assertRaises(ValueError):decode_occupancy_request(bad)

    def test_ipe_retrieves_both_sensor_cins_discovers_service_and_hashes_estimate(self):
        result = analyse_occupancy(self.document,self.client,self.platform,self.provider,{})
        self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(result['service_id'],SID)
        self.assertEqual(result['estimate_sha256'],digest(self.estimate))
        self.assertEqual([c.args[0] for c in self.client.retrieve.call_args_list],[self.ref['path'],self.ref['presence']['path']])
        posted = [c for c in self.provider.call.call_args_list if c.args[0]=='POST'][0]
        self.assertEqual(posted.args[2],{'batches':[self.unit]})
        self.assertEqual(verified_estimate(result,self.ref,NAV),self.estimate)

    def test_tampered_reference_or_estimate_is_unknown_and_transport_loss_is_retried(self):
        for path in ('content_sha256',None):
            tampered = copy.deepcopy(self.document)
            if path:tampered['batches'][0]['content_sha256'] = '0'*64
            else:tampered['batches'][0]['presence']['content_sha256'] = '0'*64
            self.assertEqual(analyse_occupancy(tampered,self.client,self.platform,self.provider,{})['state'],'UNKNOWN')
        result = analyse_occupancy(self.document,self.client,self.platform,self.provider,{})
        bad = copy.deepcopy(result);bad['estimate']['zone_count_total'] += 1
        with self.assertRaises(ProtocolError):verified_estimate(bad,self.ref,NAV)
        expired = copy.deepcopy(result);expired['valid_until_utc'] = '2020-01-01T00:00:00Z'
        with self.assertRaises(ProtocolError):verified_estimate(expired,self.ref,NAV)
        self.client.retrieve.side_effect = TransportError('unit')
        with self.assertRaises(TransportError):analyse_occupancy(self.document,self.client,self.platform,self.provider,{})

    def test_second_service_registration_uses_its_own_endpoint(self):
        controller = Mock();controller.call.side_effect = lambda method,path,*a,**k:{'id':APP,'name':OCCUPANCY_SERVICE,'nodeName':'mep1'}
        info = {'serInstanceId':SID,'serName':OCCUPANCY_SERVICE,'state':'ACTIVE','serializer':'JSON',
                'transportInfo':{'endpoint':{'uris':[OCCUPANCY_ENDPOINT]}}}
        platform = Mock()
        platform.call.side_effect = lambda method,path,body=None,**k:(None if path.endswith('/confirm_ready')
            else info if path.endswith('/'+SID) or method=='POST' else [])
        result = register_service(controller,platform,OCCUPANCY_SERVICE,OCCUPANCY_ENDPOINT)
        posted = [c for c in platform.call.call_args_list if c.args[0]=='POST' and c.args[1].endswith('/services')][0]
        self.assertEqual(posted.args[2]['transportInfo']['endpoint']['uris'],[OCCUPANCY_ENDPOINT])
        self.assertEqual(result['service_id'],SID)
        catalog = Mock();catalog.call.return_value = [info]
        self.assertEqual(discover_service(catalog,OCCUPANCY_SERVICE,SID,OCCUPANCY_ENDPOINT),info)
        with self.assertRaises(ServiceError):discover_service(catalog,OCCUPANCY_SERVICE,SID,RISK_ENDPOINT)


class FakeCSE:
    originator = 'CAdmin';release = '4'

    def __init__(self):
        self.calls = [];self.count = 0

    def for_actor(self, originator, actor):
        return self

    def ensure(self, parent, resource_type, attrs, creator=None):
        self.count += 1;self.calls.append((parent,resource_type,attrs))
        value = {'ri':f'ri-{self.count}','ty':resource_type,**attrs}
        if resource_type == 2:value['aei'] = 'C'+attrs['rn']
        return value


class BootstrapTests(unittest.TestCase):
    def run_bootstrap(self, **kw):
        fake = FakeCSE();callbacks = {f'display-{x}':'http://unit.invalid/'+x for x in 'abc'}
        return fake,bootstrap(fake,'cse','fr_unit_ns','http://unit.invalid/cb',3600,decision_policies=True,
                              display_callbacks=callbacks,dashboard=True,**kw)

    def policy(self, fake, suffix):
        return next(a for p,t,a in fake.calls if t==1 and a['rn']=='fr_unit_ns__'+suffix)['pv']['acr']

    def test_access_profile_adds_two_sensor_aes_and_role_scoped_containers(self):
        fake,resources = self.run_bootstrap(access_sensing=True,access_readers=['C-ipe'])
        actors = resources['actors']
        self.assertIn('access-gateway',actors);self.assertIn('presence-scanner',actors)
        for key in ['access-gateway/passages','presence-scanner/scans','controller/zone-routes','controller/occupancy-estimates']:
            self.assertIn(key,resources['containers'])
        for suffix,writer in [('access-policy','access-gateway'),('presence-policy','presence-scanner')]:
            rules = self.policy(fake,suffix)
            self.assertEqual(next(r['acor'] for r in rules if r['acop']==3),[actors[writer]['ae_id']])
            readers = next(r['acor'] for r in rules if r['acop']==2)
            self.assertEqual(set(readers),{actors['controller']['ae_id'],actors['responder']['ae_id'],'C-ipe'})
            self.assertNotIn(actors['resident']['ae_id'],json.dumps(rules))
        estimates = self.policy(fake,'occupancy-estimates-policy')
        self.assertEqual(next(r['acor'] for r in estimates if r['acop']==2),[actors['responder']['ae_id']])
        zones = self.policy(fake,'zone-routes-policy')
        self.assertEqual(set(next(r['acor'] for r in zones if r['acop']==2)),{actors['resident']['ae_id'],actors['responder']['ae_id']})
        passages = next(a for p,t,a in fake.calls if t==3 and a['rn']=='passages')
        self.assertIn(ACCESS_LABEL,passages['lbl']);self.assertIn('access-passages:fr_unit_ns',passages['lbl'])
        scanned = next(a for p,t,a in fake.calls if t==3 and a['rn']=='scans')
        self.assertIn(PRESENCE_LABEL,scanned['lbl']);self.assertIn('presence-scans:fr_unit_ns',scanned['lbl'])

    def test_default_profile_keeps_eight_actors_and_rejects_sensing_without_dashboard(self):
        fake,resources = self.run_bootstrap()
        self.assertEqual(len(resources['actors']),8)
        self.assertNotIn('access-gateway/passages',resources['containers'])
        with self.assertRaises(ValueError):
            bootstrap(FakeCSE(),'cse','fr_unit_ns','http://unit.invalid/cb',3600,access_sensing=True)


class ZoneViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.addCleanup(self.directory.cleanup)
        self.settings = replace(Settings(),evidence_root=Path(self.directory.name))
        self.app = ScenarioApp(self.settings,Path('unused-trace'))
        model = Evacuation(config());f = frame();model.accept(f)
        common = {k:f.data[k] for k in ['event_id','incident_id','simulation_second','timestamp_utc']}
        common.update(schema_version=1,route_version=1,policy_sha256=model.navigation.policy_hash)
        snap = model.snapshot()
        self.payloads = {'controller/routes':{**common,**model.fixed(),'blocked_nodes':[]},
            'controller/status':{**common,'observed_at_utc':f.data['timestamp_utc'],'delivery':{'state':'ALL_ACKED','ack_count':3}},
            'controller/diagnostics':{**common,'population':snap['population'],'residents':snap['residents']},
            'occupancy/observations':{**common,'zones':snap['zones']},'sensor/telemetry':f.to_dict(),
            'controller/zone-routes':{**common,'blocked_nodes':[],'origin_kind':'ROOM','computed_by':'CONTROLLER_SAME_FRAME',
                                      'routes':zone_routes(model)},
            'controller/occupancy-estimates':{**common,'kind':'FireRouteOccupancyPublication','state':'ESTIMATED',
                'applied_through_sequence':1,'registered_prior_total':85,'estimated_remaining':85,'zone_count_total':2,
                'presence_scans':1,'detected_exits':0,'unmatched_departures':0,'estimator':{'computed_by':'MEC_OCCUPANCY_SERVICE'},
                'sensing':{},'evaluation':{'truth_zones':1},'priority':[{'rank':1,'zone_id':'F7-R3','estimated_count':2,
                'likelihood':'HIGH','probability':0.97,'last_detection_second':0,'basis':'REGISTERED_PRIOR',
                'evidence':{'access_count':2,'scans':1,'detections':1},'hazard':{}}]}}
        self.client = Mock();self.client.resource.side_effect = CSEClient.resource
        def retrieve(path):
            key = next(k for k in self.payloads if path.startswith('/unit/'+k+'/'))
            return {'m2m:cin':{'ty':4,'ri':'unit-cin','con':json.dumps(self.payloads[key])}}
        self.client.retrieve.side_effect = retrieve
        self.app.context = SimpleNamespace(incident_id='inc-unit',clients={'resident':self.client,'responder':self.client},
            resources={'containers':{k:{'path':'/unit/'+k} for k in self.payloads}},model=model,hash=HASH,access_sensing=True)
        self.app.busy = False

    def test_resident_room_route_is_correlated_and_validated(self):
        result = self.app.view('inc-unit','resident',zone='F5-R2')
        self.assertEqual(result['zone_route']['source_node'],'F5-R2')
        self.assertEqual(result['zone_route']['path'][0],'F5-R2')
        self.assertIn(result['zone_route']['target_exit'],{'EXIT_A','EXIT_B'})
        self.assertNotIn('occupancy_estimate',result)
        self.assertEqual(self.app.view('inc-unit','resident')['route']['source_node'],'F7-R3')

    def test_unknown_zone_mismatch_blocked_path_and_stale_fail_closed(self):
        with self.assertRaises(LookupError):self.app.view('inc-unit','resident',zone='F5-C2')
        self.payloads['controller/zone-routes']['route_version'] = 2
        mismatched = self.app.view('inc-unit','resident',zone='F5-R2')
        self.assertIsNone(mismatched['zone_route'])  # Personal route withheld...
        self.assertEqual(mismatched['route']['source_node'],'F7-R3')  # ...fixed guidance kept.
        self.payloads['controller/zone-routes']['route_version'] = 1
        self.payloads['controller/diagnostics']['route_version'] = 2
        pending = self.app.view('inc-unit','responder',diagnostics=True,zone='F5-R2')
        self.assertEqual(pending['guidance_status'],'PENDING');self.assertIsNone(pending['zone_route'])
        self.payloads['controller/diagnostics']['route_version'] = 1
        self.payloads['controller/zone-routes']['routes']['F5-R2']['path'].insert(1,'F2-R1')
        with self.assertRaises(ProtocolError):self.app.view('inc-unit','resident',zone='F5-R2')
        self.payloads['controller/zone-routes']['routes'] = zone_routes(self.app.context.model)
        self.payloads['controller/status']['observed_at_utc'] = '2020-01-01T00:00:00Z'
        stale = self.app.view('inc-unit','resident',zone='F5-R2')
        self.assertEqual(stale['guidance_status'],'STALE');self.assertIsNone(stale['zone_route'])

    def test_responder_estimate_current_only_and_dropped_when_stale(self):
        result = self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(result['occupancy_estimate']['state'],'ESTIMATED')
        self.assertEqual(result['occupancy_estimate']['priority'][0]['zone_id'],'F7-R3')
        self.payloads['controller/occupancy-estimates']['priority'][0]['probability'] = 1.5
        with self.assertRaises(ProtocolError):self.app.view('inc-unit','responder',diagnostics=True)
        self.payloads['controller/occupancy-estimates']['priority'][0]['probability'] = 0.97
        self.payloads['controller/occupancy-estimates']['applied_through_sequence'] = 0
        self.assertEqual(self.app.view('inc-unit','responder',diagnostics=True)['occupancy_estimate']['state'],'UNKNOWN')
        self.payloads['controller/status']['observed_at_utc'] = '2020-01-01T00:00:00Z'
        self.assertNotIn('occupancy_estimate',self.app.view('inc-unit','responder',diagnostics=True))

    def test_zone_route_http_path_is_rooms_only(self):
        from backend.http_api import api_server
        with patch('backend.http_api.ThreadingHTTPServer') as server:
            app = Mock();auth = Mock(lifetime=1200);auth.role.return_value = 'resident'
            app.zone_ids = frozenset({'F5-R2'});app.view.return_value = {'route':None}
            api_server('unit.invalid',3001,app,auth,'http://127.0.0.1:3001',Path('frontend/scenario'),snapshots=True)
            cls = server.call_args.args[1]
        def get(path):
            handler = object.__new__(cls);handler.path = path
            handler.headers = {'Host':'127.0.0.1:3001'};handler.send = Mock();handler.do_GET()
            return handler.send.call_args.args[0]
        self.assertEqual(get('/api/v1/incidents/inc-unit/resident/F5-R2'),200)
        app.view.assert_called_once_with('inc-unit','resident',diagnostics=False,zone='F5-R2')
        self.assertEqual(get('/api/v1/incidents/inc-unit/resident/F5-C2'),404)
        self.assertEqual(get('/api/v1/incidents/inc-unit/snapshot/F5-R2'),404)
        self.assertEqual(get('/api/v1/incidents/inc-unit/responder/F5-R2'),403)
        self.assertEqual(app.view.call_count,1)


class PublishAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.addCleanup(self.directory.cleanup)
        self.session = ScenarioSession(replace(Settings(),evidence_root=Path(self.directory.name)))
        self.session.model = Evacuation(config())
        self.session.gateway = AccessGateway(self.session.model.navigation,SENSING)
        self.session.scanner = PresenceScanner(self.session.model.navigation,SENSING)
        self.writes = []
        def write(key,name,value,actor='controller'):
            self.writes.append((key,name,value,actor))
            return {'path':'/unit/'+key+'/'+name,'ri':'ri-'+name,'content':value}
        self.session.write = write
        self.estimator = OccupancyEstimator(self.session.model.navigation,SENSING)
        self.second = 0

    def advance(self, count):
        for _ in range(count):
            before = self.session.positions();value = frame(self.second);self.second += 1
            self.session.model.accept(value);self.session.observe_access(before,value.to_dict())

    def common(self):
        last = self.session.model.last
        return {'schema_version':1,'event_id':last['event_id'],'incident_id':last['incident_id'],'route_version':last['sequence'],
                'simulation_second':last['simulation_second'],'timestamp_utc':last['timestamp_utc'],'data_origin':'SYNTHETIC',
                'policy_sha256':self.session.model.navigation.policy_hash,'source':'unit:controller'}

    def estimate(self, references):
        stored = {'/unit/'+w[0]+'/'+w[1]:w[2] for w in self.writes}
        for ref in references:
            access,presence = stored[ref['path']],stored[ref['presence']['path']]
            self.assertEqual(canonical_sha256(access),ref['content_sha256'])
            self.assertEqual(canonical_sha256(presence),ref['presence']['content_sha256'])
            if access['sequence_to'] > self.estimator.applied:
                value = parse_unit({'access':access,'presence':presence},NAV)
                self.estimator.apply(value['access'],value['presence'])
        return self.estimator.snapshot(),{'computed_by':'MEC_OCCUPANCY_SERVICE','service_id':SID}

    def test_sensor_cins_then_estimate_publication_with_truth_comparison(self):
        self.session.estimate_occupancy = self.estimate
        self.advance(12)
        publication = self.session.publish_access(self.common())
        keys = [(w[0],w[3]) for w in self.writes]
        self.assertEqual(keys,[('access-gateway/passages','access-gateway'),('presence-scanner/scans','presence-scanner'),
                               ('controller/occupancy-estimates','controller')])
        self.assertEqual([s['simulation_second'] for s in self.writes[1][2]['scans']],[0,10])
        self.assertGreater(self.session.gateway.truth_passages,0)
        self.assertEqual(publication['applied_through_sequence'],12);self.assertEqual(publication['presence_scans'],2)
        self.assertEqual(publication['evaluation']['truth_source'],'SYNTHETIC_SIMULATION_GROUND_TRUTH')
        self.assertEqual(sum(p['estimated_count'] for p in publication['priority']),publication['zone_count_total'])
        self.assertEqual(publication['estimated_remaining'],publication['registered_prior_total']-publication['detected_exits'])
        for record in (self.writes[0][2],self.writes[1][2]):self.assertNotIn('-p1',json.dumps(record))
        self.assertEqual(self.session.access_unacked,[])

    def test_failed_estimate_keeps_batches_for_catch_up_then_limit_stops(self):
        self.session.estimate_occupancy = Mock(side_effect=ProtocolError('unit'))
        self.advance(4);self.assertIsNone(self.session.publish_access(self.common()))
        self.assertEqual(len(self.session.access_unacked),1)
        self.session.estimate_occupancy = Mock(side_effect=self.estimate)
        self.advance(3);publication = self.session.publish_access(self.common())
        self.assertEqual(len(self.session.estimate_occupancy.call_args.args[0]),2)
        self.assertEqual(publication['applied_through_sequence'],7)
        with patch('backend.scenario_core.MAX_UNACKED_ACCESS_BATCHES',1):
            self.session.estimate_occupancy = Mock(side_effect=ProtocolError('unit'))
            self.advance(1);self.session.publish_access(self.common())
            self.advance(1);self.session.publish_access(self.common())
        self.assertEqual(self.session.access_broken,'ESTIMATE_CATCH_UP_LIMIT')
        self.advance(1);self.assertIsNone(self.session.publish_access(self.common()))

    def test_base_runtime_without_estimator_only_records_sensor_cins(self):
        self.advance(2);self.assertIsNone(self.session.publish_access(self.common()))
        self.assertEqual([w[0] for w in self.writes],['access-gateway/passages','presence-scanner/scans'])
        self.assertEqual(self.session.access_unacked,[])


if __name__ == '__main__':
    unittest.main()
