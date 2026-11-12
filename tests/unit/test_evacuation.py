"""Synthetic component fixtures; these tests never claim actual CSE evidence."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from mec.risk.evacuation import Navigation,load_assumptions
from simulator.evacuation import Evacuation
from simulator.events import ContractError
from simulator.scenario_frames import PROFILE,ZONES,ScenarioFrame,emission,read_trace,source_manifest,validate_raw
from backend.config import Settings
from backend.notifications import NotificationService,NotificationStore,MAX_NOTIFICATION_BYTES
from backend.scenario_demo import ScenarioApp

HASH = source_manifest()['bundle_sha256']


def raw(second=0):
    return {'schema_version':1,'profile_id':PROFILE,'source_manifest_sha256':HASH,'seed':2026,
        'wind_mps':5,'simulation_second':second,'ended':False,
        'zones':[{'zone_id':n,'fire_index':0,'smoke_index':0,'collapsed':False} for n in ZONES]}


def frame(second=0,*,changes=None):
    data = raw(second)
    for z in data['zones']:
        if z['zone_id'] in (changes or {}):
            z.update(changes[z['zone_id']])
    result = emission(data,'inc-unit','unit:source',HASH)
    result.data['event_id'] = 'frame-'+str(second)
    return result


def config(**overrides):
    data = load_assumptions()
    data.update(people_per_room=1,walk_speed_min_mps=1,walk_speed_max_mps=1,slow_fraction=0,
        departure_delay_min_s=0,departure_delay_max_s=0)
    data.update(overrides)
    return data


class FrameContractTests(unittest.TestCase):
    def test_manifest_profile_and_public_envelope(self):
        f = frame()
        self.assertEqual(len(f.to_dict()['zones']),162)
        self.assertEqual(ScenarioFrame.parse(f.to_dict()),f)
        self.assertNotIn('_minuteTarget',f.to_dict())

    def test_unknown_future_fields_and_missing_zones_rejected(self):
        for mutate in [lambda d:d.update(_minuteTarget={}),lambda d:d['zones'].pop(),
                       lambda d:d['zones'].append(dict(d['zones'][0]))]:
            value = raw();mutate(value)
            with self.assertRaises(ContractError):validate_raw(value,HASH)

    def test_bad_indexes_wind_seed_and_clock(self):
        for key,value in [('seed',True),('seed',0),('wind_mps',2),('simulation_second',-1),('ended',1)]:
            data=raw();data[key]=value
            with self.assertRaises(ContractError):validate_raw(data,HASH)
        for value in [float('nan'),float('inf'),True,-1,101]:
            data=raw();data['zones'][0]['fire_index']=value
            with self.assertRaises(ContractError):validate_raw(data,HASH)

    def test_shared_corridor_smoke_and_cap_checked(self):
        for key,value in [('F2-C1',1),('F1-R1',31)]:
            data=raw();next(z for z in data['zones'] if z['zone_id']==key)['smoke_index']=value
            with self.assertRaises(ContractError):validate_raw(data,HASH)

    def test_collapse_cap_and_exclusions_checked(self):
        for names in [['F1-SA'],['F1-E'],['F1-R1','F1-R2','F1-R3']]:
            data=raw()
            for z in data['zones']:
                if z['zone_id'] in names:z['collapsed']=True
            with self.assertRaises(ContractError):validate_raw(data,HASH)

    def test_source_and_UTC_provenance_checked(self):
        for key,value in [('source_manifest_sha256','0'*64),('data_origin','PHYSICAL'),('sequence',2),
                          ('timestamp_utc','2026-01-01T00:00:00'),('source','bad\nsource')]:
            value_dict=frame().to_dict();value_dict[key]=value
            with self.assertRaises(ContractError):ScenarioFrame.parse(value_dict)

    def test_termination_requires_all_hazard_zones(self):
        data=raw();data['ended']=True
        with self.assertRaises(ContractError):validate_raw(data,HASH)
        for z in data['zones']:z['fire_index']=100
        self.assertTrue(validate_raw(data,HASH)['ended'])

    def test_trace_checks_order_and_oversized_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace'
            p.write_text(json.dumps(raw())+'\n'+json.dumps(raw(1))+'\n')
            self.assertEqual(len(list(read_trace(p,HASH))),2)
            p.write_text(json.dumps(raw())+'\n'+json.dumps(raw(2))+'\n')
            with self.assertRaises(ContractError):list(read_trace(p,HASH))
            p.write_text('x'*65537+'\n')
            with self.assertRaises(ContractError):list(read_trace(p,HASH))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.nav=Navigation(config());self.nav.update(frame())

    def test_164_nodes_external_exits_and_isolated_elevators(self):
        self.assertEqual(len(self.nav.nodes),164)
        self.assertEqual(self.nav.exits,{'EXIT_A','EXIT_B'})
        for floor in range(1,11):self.assertFalse(self.nav.adjacency[f'F{floor}-E'])
        self.assertNotIn('F11-ROOF',self.nav.exits)
        self.assertEqual(len(self.nav.adjacency['F11-ROOF']),2)

    def test_analytic_room_to_exit_time_and_stair_factor(self):
        result=self.nav.route('F1-R1',1)
        self.assertEqual(result['path'],['F1-R1','F1-L','EXIT_A'])
        self.assertEqual(result['routing_cost'],7)
        edge=self.nav.adjacency['F1-SA']['F2-SA']
        self.assertEqual(edge.length_m/self.nav.speed(edge,1),16)

    def test_collapse_avoided_and_both_stairs_blocked_no_route(self):
        self.nav.update(frame(changes={'F7-C1':{'collapsed':True}}))
        result=self.nav.route('F7-R3')
        self.assertEqual(result['status'],'ROUTE_AVAILABLE');self.assertNotIn('F7-C1',result['path'])
        self.nav.update(frame(changes={'F7-SA':{'fire_index':60},'F7-SB':{'fire_index':60}}))
        result=self.nav.route('F7-R3')
        self.assertEqual(result['status'],'NO_VERIFIED_ROUTE');self.assertIsNone(result['target_exit'])
        self.assertEqual(result['path'],[])

    def test_load_changes_exit_choice(self):
        result=self.nav.route('F1-R1',occupied={tuple(sorted(('F1-L','EXIT_A'))):2})
        self.assertEqual(result['target_exit'],'EXIT_B')

    def test_smoke_slows_without_claiming_physical_tenability(self):
        edge=self.nav.adjacency['F1-R1']['F1-L'];baseline=self.nav.speed(edge,1)
        self.nav.update(frame(changes={'F1-L':{'fire_index':30,'smoke_index':50}}))
        self.assertLess(self.nav.speed(edge,1),baseline)
        self.assertNotIn('F1-L',self.nav.blocked)

    def test_invalid_assumptions_fail(self):
        for key,value in [('people_per_room',True),('door_capacity_people',0),('walk_speed_min_mps',0),
                          ('slow_multiplier',2),('smoke_slowdown_fraction',1),('fire_block_index',101),
                          ('stair_floor_length_m',float('nan')),('provenance','MEASURED')]:
            data=config();data[key]=value
            with self.assertRaises(ValueError):Navigation(data)


class ResidentTests(unittest.TestCase):
    def test_seeded_variability_and_fixed_queries_do_not_move_people(self):
        a,b=Evacuation(),Evacuation();f=frame();a.accept(f);b.accept(f)
        before=[asdict(p) for p in a.people]
        for node in ['F1-R1','F5-R7','F10-R9']:a.fixed(node)
        self.assertEqual(before,[asdict(p) for p in a.people])
        self.assertEqual(before,[asdict(p) for p in b.people]);self.assertEqual(len(before),170)
        self.assertGreater(len({p.walk_speed_mps for p in a.people}),1)

    def test_delay_and_analytic_travel_no_teleport(self):
        model=Evacuation(config(departure_delay_min_s=2,departure_delay_max_s=2))
        model.accept(frame());p=next(p for p in model.people if p.origin=='F1-R1')
        self.assertIsNone(p.target)
        model.accept(frame(1));self.assertIsNone(p.target)
        model.accept(frame(2));self.assertEqual(p.target,'F1-L');self.assertEqual(p.progress_m,0)
        model.accept(frame(3));self.assertEqual(p.node,'F1-R1');self.assertEqual(p.progress_m,1)
        model.accept(frame(4));self.assertEqual(p.node,'F1-R1');self.assertEqual(p.progress_m,2)
        model.accept(frame(5));self.assertEqual(p.node,'F1-L');self.assertEqual(p.distance_m,3)

    def test_capacity_and_conservation_over_time(self):
        model=Evacuation(config(door_capacity_people=1,exit_capacity_people=1))
        for second in range(100):
            model.accept(frame(second));value=model.snapshot()['population']
            self.assertEqual(value['total'],value['remaining']+value['evacuated'])
            self.assertTrue(all(n<=model.navigation.links[k].capacity for k,n in model.occupied().items()))
        self.assertGreater(model.snapshot()['population']['evacuated'],0)

    def test_queue_admission_and_eventual_progress(self):
        model=Evacuation(config(people_per_room=3,door_capacity_people=1))
        model.accept(frame());room=[p for p in model.people if p.origin=='F1-R1']
        self.assertEqual([p.status for p in room],['MOVING','QUEUED','QUEUED'])
        for second in range(1,10):model.accept(frame(second))
        self.assertTrue(all(p.node!='F1-R1' for p in room))

    def test_in_transit_collapse_retains_person_and_position(self):
        model=Evacuation(config());model.accept(frame());model.accept(frame(1))
        p=next(p for p in model.people if p.origin=='F1-R1');distance=p.distance_m
        model.accept(frame(2,changes={'F1-L':{'collapsed':True}}))
        self.assertEqual(p.status,'BLOCKED_IN_TRANSIT');self.assertEqual(p.distance_m,distance)
        self.assertIsNone(p.evacuated_at_s)
        self.assertGreater(model.snapshot()['population']['remaining'],0)

    def test_late_departure_cannot_jump_an_existing_door_queue(self):
        model=Evacuation(config(people_per_room=3,door_capacity_people=1,
            departure_delay_min_s=2,departure_delay_max_s=2))
        model.accept(frame());people=[p for p in model.people if p.origin=='F1-R1']
        people[0].departure_delay_s=4
        people[1].departure_delay_s=people[2].departure_delay_s=0
        for second in range(1,5):model.accept(frame(second))
        self.assertEqual(people[2].status,'MOVING')
        self.assertEqual(people[0].status,'QUEUED')

    def test_exact_duplicate_is_idempotent_conflict_and_time_jump_rejected(self):
        model=Evacuation(config());f=frame();self.assertTrue(model.accept(f))
        before=model.snapshot();self.assertFalse(model.accept(f));self.assertEqual(model.snapshot(),before)
        with self.assertRaises(ValueError):model.accept(frame(2))
        other=frame();other.data['event_id']='different'
        with self.assertRaises(ValueError):model.accept(other)
        model.accept(frame(1))
        with self.assertRaises(ValueError):model.accept(f)

    def test_context_change_requires_reset(self):
        model=Evacuation(config());model.accept(frame())
        for key,value in [('incident_id','inc-new'),('seed',5),('source','other')]:
            f=frame(1);f.data[key]=value
            with self.assertRaises(ValueError):model.accept(f)

    def test_everyone_can_exit_an_unblocked_schematic(self):
        model=Evacuation(config());model.accept(frame())
        for second in range(1,700):
            model.accept(frame(second))
            if model.snapshot()['population']['remaining']==0:break
        self.assertEqual(model.snapshot()['population']['evacuated'],85)
        self.assertTrue(all(p.evacuated_at_s is not None for p in model.people))

    def test_blocked_origin_and_empty_population_remain_consistent(self):
        model=Evacuation(config(people_per_room=0));model.accept(frame(changes={'F7-R3':{'collapsed':True}}))
        value=model.snapshot();self.assertEqual(value['population']['total'],0)
        self.assertEqual(value['fixed_route']['status'],'NO_VERIFIED_ROUTE')


class SelectedTransportContractTests(unittest.TestCase):
    def test_complete_frame_notification_fits_and_is_durably_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store=NotificationStore(Path(directory)/'notifications.sqlite3')
            service=NotificationService(store,'/id-unit','4',frozenset(ZONES),decoder=lambda d:ScenarioFrame.parse(d,HASH))
            ref='/id-unit/sub';service.approve({ref})
            message={'m2m:sgn':{'sur':ref,'nev':{'net':3,'rep':{'m2m:cin':{'ty':4,'ri':'cin-unit','con':json.dumps(frame().to_dict())}}}}}
            body=json.dumps(message).encode()
            self.assertLess(len(body),MAX_NOTIFICATION_BYTES)
            headers={'X-M2M-Origin':'/id-unit','X-M2M-RI':'unit-rqi','X-M2M-RVI':'4','Content-Type':'application/json'}
            self.assertEqual(service.handle(headers,body).http_status,200)
            self.assertEqual(service.handle(headers,body).kind,'duplicate')
            self.assertEqual(len(store.records()),1)
            self.assertEqual(len(store.records()[0]['event']['zones']),162)


class SelectedViewUnitTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        from dataclasses import replace
        self.settings=replace(Settings(),evidence_root=Path(self.directory.name))
        self.app=ScenarioApp(self.settings,Path('unused-trace'))
        model=Evacuation(config());f=frame();model.accept(f)
        common={k:f.data[k] for k in ['event_id','incident_id','simulation_second','timestamp_utc']}
        common.update(schema_version=1,route_version=1,policy_sha256=model.navigation.policy_hash)
        snap=model.snapshot()
        self.payloads={'controller/routes':{**common,**model.fixed(),'blocked_nodes':[]},
            'controller/status':{**common,'observed_at_utc':f.data['timestamp_utc'],'delivery':{'state':'ALL_ACKED','ack_count':3}},
            'controller/diagnostics':{**common,'population':snap['population'],'residents':snap['residents']},
            'occupancy/observations':{**common,'zones':snap['zones']},'sensor/telemetry':f.to_dict()}
        from onem2m.client import CSEClient
        self.client=Mock();self.client.resource.side_effect=CSEClient.resource
        def retrieve(path):
            key=next(k for k in self.payloads if path.startswith('/unit/'+k+'/'))
            return {'m2m:cin':{'ty':4,'ri':'unit-cin','con':json.dumps(self.payloads[key])}}
        self.client.retrieve.side_effect=retrieve
        resources={'containers':{k:{'path':'/unit/'+k} for k in self.payloads}}
        self.app.context=SimpleNamespace(incident_id='inc-unit',clients={'resident':self.client,'responder':self.client},
            resources=resources,model=model,hash=HASH)
        self.app.busy=False

    def test_resident_has_only_fixed_approved_guidance(self):
        result=self.app.view('inc-unit','resident')
        self.assertEqual(result['route']['source_node'],'F7-R3')
        for key in ['population','residents','occupants','hazards']:self.assertNotIn(key,result)
        self.assertEqual(self.client.retrieve.call_count,2)
        with self.assertRaises(PermissionError):self.app.view('inc-unit','resident',diagnostics=True)
        self.assertEqual(self.client.retrieve.call_count,2)

    def test_responder_gets_correlated_moving_and_fixed_states(self):
        result=self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(result['population']['total'],85)
        self.assertEqual(len(result['residents']),85)
        self.assertEqual(len(result['hazards']['zones']),162)

    def test_stale_drops_direction_and_all_person_positions(self):
        self.payloads['controller/status']['observed_at_utc']='2020-01-01T00:00:00Z'
        result=self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(result['guidance_status'],'STALE');self.assertIsNone(result['route'])
        for key in ['population','residents','occupants']:self.assertNotIn(key,result)

    def test_busy_or_mismatched_frame_clears_guidance(self):
        self.app.busy=True
        result=self.app.view('inc-unit','resident')
        self.assertEqual(result['guidance_status'],'PENDING');self.assertIsNone(result['route'])
        self.app.busy=False;self.payloads['controller/status']['event_id']='different'
        result=self.app.view('inc-unit','resident')
        self.assertEqual(result['guidance_status'],'PENDING');self.assertIsNone(result['route'])

    def test_private_snapshot_mismatch_is_pending(self):
        self.payloads['controller/diagnostics']['route_version']=2
        result=self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(result['guidance_status'],'PENDING');self.assertIsNone(result['route'])

    def test_inconsistent_delivery_and_population_fail_closed(self):
        from onem2m.client import ProtocolError
        self.payloads['controller/status']['delivery']['ack_count']=True
        with self.assertRaises(ProtocolError):self.app.view('inc-unit','resident')
        self.payloads['controller/status']['delivery']['ack_count']=3
        self.payloads['controller/diagnostics']['population']['remaining']=0
        with self.assertRaises(ProtocolError):self.app.view('inc-unit','responder',diagnostics=True)

    def test_degraded_controller_does_not_serve_last_route_as_current(self):
        self.app.state='DEGRADED'
        result=self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(result['guidance_status'],'UNKNOWN');self.assertIsNone(result['route'])
        self.assertNotIn('residents',result)
        self.client.retrieve.assert_not_called()

    def test_historical_snapshot_available_after_expiry_without_refreshing_live_data(self):
        self.payloads['controller/status']['observed_at_utc']='2020-01-01T00:00:00Z'
        before=copy.deepcopy(self.app.context.model.snapshot())
        record=self.app.snapshot('inc-unit','responder')
        self.assertEqual(record['snapshot_kind'],'HISTORICAL');self.assertFalse(record['is_live'])
        self.assertEqual(record['guidance_status'],'HISTORICAL');self.assertIsNone(record['route'])
        self.assertEqual(record['snapshot_at_utc'],'2020-01-01T00:00:00Z')
        self.assertEqual(len(record['residents']),85)
        self.assertEqual(self.app.context.model.snapshot(),before)
        live=self.app.view('inc-unit','responder',diagnostics=True)
        self.assertEqual(live['guidance_status'],'STALE');self.assertNotIn('residents',live)
        self.client.create.assert_not_called()

    def test_snapshot_reads_committed_named_CINs_while_next_frame_is_pending(self):
        self.app.context.model.accept(frame(1));self.app.busy=True
        record=self.app.snapshot('inc-unit','responder')
        self.assertEqual(record['simulation_second'],0)
        self.assertEqual(record['route_version'],1)
        calls=[call.args[0] for call in self.client.retrieve.call_args_list]
        for path in ['/unit/controller/routes/route-1','/unit/controller/diagnostics/moving-1',
                     '/unit/occupancy/observations/occupancy-1','/unit/sensor/telemetry/frame-1']:
            self.assertIn(path,calls)
        self.assertNotIn('/unit/controller/diagnostics/la',calls)

    def test_snapshot_resident_or_wrong_incident_denied_before_CSE_reads(self):
        with self.assertRaises(PermissionError):self.app.snapshot('inc-unit','resident')
        with self.assertRaises(LookupError):self.app.snapshot('another','responder')
        self.client.retrieve.assert_not_called()

    def test_snapshot_rejects_inconsistent_saved_records(self):
        from onem2m.client import ProtocolError
        self.payloads['controller/diagnostics']['route_version']=2
        with self.assertRaises(ProtocolError):self.app.snapshot('inc-unit','responder')


class SnapshotHTTPPolicyTests(unittest.TestCase):
    def handler(self,role='responder',enabled=True):
        from backend.http_api import api_server
        with patch('backend.http_api.ThreadingHTTPServer') as server:
            app=Mock();auth=Mock(lifetime=1200);auth.role.return_value=role
            app.snapshot.return_value={'snapshot_kind':'HISTORICAL','is_live':False,'route':None}
            api_server('unit.invalid',3001,app,auth,'http://127.0.0.1:3001',Path('frontend/scenario'),snapshots=enabled)
            cls=server.call_args.args[1]
        handler=object.__new__(cls);handler.path='/api/v1/incidents/inc-unit/snapshot'
        handler.headers={'Host':'127.0.0.1:3001'};handler.send=Mock()
        return handler,app

    def test_snapshot_responder_access(self):
        handler,app=self.handler();handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],200)
        app.snapshot.assert_called_once_with('inc-unit','responder')

    def test_snapshot_resident_denied_without_app_data_read(self):
        handler,app=self.handler(role='resident');handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],403);app.snapshot.assert_not_called()

    def test_snapshot_unauthed_denied_and_legacy_route_disabled(self):
        handler,app=self.handler(role=None);handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],401);app.snapshot.assert_not_called()
        handler,app=self.handler(enabled=False);handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],404);app.snapshot.assert_not_called()


if __name__=='__main__':unittest.main()
