"""Offline contracts/state and protocol fixtures; no actual Group/ACK evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import queue
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.config import Settings
from backend.delivery import AckSet, DeliverySession, display_callbacks
from backend.notifications import NotificationService, NotificationStore
from backend.p1_routes import run
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient, ProtocolError, WireResponse
from onem2m.groups import member_cins
from simulator.commands import DisplayAck, DisplayCommand
from simulator.displays import DisplayState
from simulator.events import ContractError

NOW = datetime(2026,11,11,13,tzinfo=timezone.utc)
EXITS = {'EXIT_A','EXIT_B'}


def command(**kwargs):
    base = DisplayCommand(1,'unit-command','unit-incident','unit-event',1,'DISPLAY_ROUTE','EXIT_A',
                          'ROUTE_AVAILABLE',(NOW+timedelta(seconds=30)).isoformat(),NOW.isoformat(),'unit:controller','SYNTHETIC')
    return replace(base,**kwargs)


def ack(device='C-unit-a', **kwargs):
    base = DisplayAck(1,'ack-'+device,'unit-command',device,'unit-incident','unit-event',1,
                      'APPLIED','APPLIED',NOW.isoformat(),'unit:'+device,'SYNTHETIC')
    return replace(base,**kwargs)


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'display.sqlite3'
        self.state = self.reopen()

    def reopen(self):
        return DisplayState(self.path,'C-unit-a','unit-incident','unit:controller','unit:display-a',EXITS)

    def test_apply_then_clear_route_removes_old_exit(self):
        applied = self.state.apply(command(),now=NOW)
        self.assertEqual((applied.device_id,applied.status),('C-unit-a','APPLIED'))
        self.assertEqual(self.state.snapshot(self.path)['route_exit'],'EXIT_A')
        clear = command(command_id='clear-unit',route_version=2,action='CLEAR_ROUTE',route_exit=None,guidance_status='NO_VERIFIED_ROUTE')
        self.assertEqual(self.state.apply(clear,now=NOW).status,'APPLIED')
        self.assertIsNone(self.state.snapshot(self.path)['route_exit'])
        self.assertEqual(self.state.snapshot(self.path)['guidance_status'],'NO_VERIFIED_ROUTE')

    def test_duplicate_after_restart_keeps_same_ack_and_one_application(self):
        first = self.state.apply(command(),now=NOW)
        second = self.reopen().apply(command(),now=NOW+timedelta(days=1))
        self.assertEqual(first,second)
        self.assertEqual(len(self.state.pending()),1)
        self.state.posted(first.command_id)
        self.assertEqual(self.reopen().pending(),[])

    def test_concurrent_duplicate_creates_single_ack(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _:self.state.apply(command(),now=NOW),range(20)))
        self.assertEqual(len({a.ack_id for a in replies}),1)
        self.assertEqual(len(self.state.pending()),1)

    def test_expired_command_is_rejected_without_directions(self):
        result = self.state.apply(command(),now=NOW+timedelta(seconds=30))
        self.assertEqual((result.status,result.reason),('REJECTED','EXPIRED'))
        self.assertIsNone(self.state.snapshot(self.path))

    def test_expiry_clears_previously_applied_directions(self):
        self.state.apply(command(),now=NOW)
        self.state.expire(now=NOW+timedelta(seconds=30))
        snapshot = self.state.snapshot(self.path)
        self.assertEqual((snapshot['route_exit'],snapshot['guidance_status']),(None,'STALE'))
        self.assertEqual(snapshot['route_version'],1)

    def test_old_or_equal_version_never_replaces_new_guidance(self):
        self.state.apply(command(route_version=2,route_exit='EXIT_B'),now=NOW)
        for version in [1,2]:
            result=self.state.apply(command(command_id='old-'+str(version),route_version=version),now=NOW)
            self.assertEqual(result.reason,'OUTDATED')
        self.assertEqual(self.state.snapshot(self.path)['route_exit'],'EXIT_B')

    def test_wrong_incident_source_and_future_time_rejected(self):
        cases=[(command(incident_id='other'), 'UNKNOWN_INCIDENT'),(command(source='other'), 'UNEXPECTED_SOURCE'),
               (command(timestamp_utc=(NOW+timedelta(seconds=6)).isoformat()), 'FUTURE')]
        for item,reason in cases:
            result=self.state.apply(item,now=NOW)
            self.assertEqual((result.status,result.reason),('REJECTED',reason))
            # Distinct payloads cannot reuse a command ID, even if rejected.
            self.state=DisplayState(Path(self.temp.name)/('new-'+reason+'.sqlite3'),'C-unit-a','unit-incident','unit:controller','unit:display-a',EXITS)

    def test_conflicting_command_id_is_not_overwritten(self):
        self.state.apply(command(),now=NOW)
        with self.assertRaises(ValueError):
            self.state.apply(command(route_exit='EXIT_B'),now=NOW)
        self.assertEqual(self.state.snapshot(self.path)['route_exit'],'EXIT_A')

    def test_schema_action_nullability_and_timestamp_boundaries(self):
        original=command().to_dict()
        for update in [{'route_version':True},{'schema_version':True},{'action':'OTHER'}, {'route_exit':None},
                       {'action':'CLEAR_ROUTE'},{'guidance_status':'UNKNOWN'}, {'route_exit':'F2_A'},
                       {'expires_at_utc':NOW.isoformat()},{'timestamp_utc':'2026-11-11'}, {'data_origin':'PHYSICAL'}, {'extra':1}]:
            with self.subTest(update=update),self.assertRaises(ContractError):
                DisplayCommand.parse({**original,**update},EXITS)

    def test_status_command_has_no_direction(self):
        status=command(action='DISPLAY_STATUS',route_exit=None,guidance_status='UNKNOWN')
        self.assertEqual(self.state.apply(status,now=NOW).status,'APPLIED')
        self.assertIsNone(self.state.snapshot(self.path)['route_exit'])


class AckTests(unittest.TestCase):
    def test_late_worker_error_cannot_be_reported_as_success(self):
        session=object.__new__(DeliverySession)
        session.messages=queue.Queue()
        session.messages.put({'kind':'error','role':'display-a','error':'ProtocolError'})
        with self.assertRaises(ProtocolError):
            session.check_workers()

    def test_three_replays_from_one_device_stay_incomplete(self):
        tracker=AckSet(command(),{'C-unit-a','C-unit-b','C-unit-c'})
        for _ in range(3):
            tracker.add(ack().to_dict(),'C-unit-a')
        self.assertEqual(tracker.missing,{'C-unit-b','C-unit-c'})

    def test_three_actual_bindings_complete_the_set(self):
        tracker=AckSet(command(),{'C-unit-a','C-unit-b','C-unit-c'})
        for device in tracker.expected:
            tracker.add(ack(device).to_dict(),device)
        self.assertFalse(tracker.missing)

    def test_wrong_binding_version_event_and_source_never_count(self):
        for data,bound in [(ack().to_dict(),'C-unit-b'),(ack(route_version=2).to_dict(),'C-unit-a'),
                           (ack(event_id='other').to_dict(),'C-unit-a'),(ack(source='wrong').to_dict(),'C-unit-a')]:
            tracker=AckSet(command(),{'C-unit-a','C-unit-b'},sources={'C-unit-a':'unit:C-unit-a'})
            with self.assertRaises(ProtocolError):
                tracker.add(data,bound)
            self.assertEqual(len(tracker.missing),2)

    def test_rejected_and_reused_ack_identity_do_not_count(self):
        tracker=AckSet(command(),{'C-unit-a','C-unit-b'})
        with self.assertRaises(ProtocolError):
            tracker.add(ack(status='REJECTED',reason='EXPIRED').to_dict(),'C-unit-a')
        tracker.add(ack().to_dict(),'C-unit-a')
        with self.assertRaises(ProtocolError):
            tracker.add(ack('C-unit-b',ack_id=ack().ack_id).to_dict(),'C-unit-b')
        self.assertEqual(tracker.missing,{'C-unit-b'})

    def test_older_command_ack_is_ignored(self):
        tracker=AckSet(command(),{'C-unit-a'})
        self.assertFalse(tracker.add(ack(command_id='older').to_dict(),'C-unit-a'))
        self.assertEqual(len(tracker.missing),1)


class GroupProtocolTests(unittest.TestCase):
    @staticmethod
    def aggregate():
        return {'m2m:agr':{'m2m:rsp':[{'rsc':2001,'rqi':'unit-rqi','pc':{'m2m:cin':{'ty':4,'ri':'cin-'+n,'pi':n}}} for n in ['cnt-a','cnt-b','cnt-c']]}}

    def test_aggregate_all_three_actual_parent_ids_required(self):
        self.assertEqual(set(member_cins(self.aggregate(),{'cnt-a','cnt-b','cnt-c'})),{'cnt-a','cnt-b','cnt-c'})

    def test_partial_unknown_duplicate_and_invalid_members_fail(self):
        for kind in ['partial','unknown','duplicate','reused-cin','failed','boolean-status','no-pc','invalid-envelope']:
            data=self.aggregate();rows=data['m2m:agr']['m2m:rsp']
            if kind=='partial': rows.pop()
            elif kind=='unknown': rows[0]['pc']['m2m:cin']['pi']='other'
            elif kind=='duplicate': rows[0]['pc']['m2m:cin']['pi']='cnt-b'
            elif kind=='reused-cin': rows[0]['pc']['m2m:cin']['ri']='cin-cnt-b'
            elif kind=='failed': rows[1]['rsc']=4103
            elif kind=='boolean-status': rows[1]['rsc']=True
            elif kind=='no-pc': rows[1]['pc']=[]
            else: data={'m2m:agr':[]}
            with self.subTest(kind=kind),self.assertRaises(ProtocolError):
                member_cins(data,{'cnt-a','cnt-b','cnt-c'})

    def test_fanout_OK_envelope_preserves_strict_normal_CREATE(self):
        def transport(method,url,headers,body,timeout):
            data=self.aggregate()
            for row in data['m2m:agr']['m2m:rsp']: row['rqi']=headers['X-M2M-RI']
            return WireResponse(200,{'X-M2M-RSC':'2000','X-M2M-RI':headers['X-M2M-RI'],'Content-Type':'application/json'},json.dumps(data).encode())
        client=CSEClient('http://unit.invalid','C-unit','4',transport=transport)
        self.assertIn('m2m:agr',client.fanout_create('/unit/group/fopt',{'con':'unit'}))
        with self.assertRaises(ProtocolError): client.create('/unit/cnt',4,{'con':'unit'})
        with self.assertRaises(ValueError): client.fanout_create('/unit/not-fopt',{})

    def test_inner_request_id_mismatch_is_rejected(self):
        def transport(method,url,headers,body,timeout):
            return WireResponse(200,{'X-M2M-RSC':'2000','X-M2M-RI':headers['X-M2M-RI'],'Content-Type':'application/json'},json.dumps(self.aggregate()).encode())
        with self.assertRaises(ProtocolError):
            CSEClient('http://unit.invalid','C-unit','4',transport=transport).fanout_create('/unit/group/fopt',{'con':'unit'})

    def test_opt_in_policies_keep_devices_from_forging_commands_and_controller_from_forging_acks(self):
        client=Mock(release='4',originator='unit-admin')
        def ensure(parent,ty,attrs,**kwargs):
            return {**attrs,'ri':attrs['rn'],'ty':ty,**({'aei':'C-'+attrs['rn']} if ty==2 else {})}
        client.ensure.side_effect=ensure
        callbacks={r:f'http://unit.invalid:800{i}/onem2m/notify' for i,r in enumerate(['display-a','display-b','display-c'],1)}
        result=bootstrap(client,'unit-base','fr_unit','http://unit.invalid/onem2m/notify',86400,decision_policies=True,display_callbacks=callbacks)
        self.assertEqual(result['telemetry_policy_ri'],'fr_unit__telemetry-policy')
        policies=[c.args[2] for c in client.ensure.call_args_list if c.args[1]==1]
        device=result['actors']['display-a']['ae_id'];controller=result['actors']['controller']['ae_id']
        for suffix,reader in [('display-a-commands-policy',device),('display-a-acks-policy',controller)]:
            policy=next(p for p in policies if p['rn'].endswith(suffix))
            creates=[r for r in policy['pv']['acr'] if reader in r['acor'] and r['acop']&1]
            self.assertEqual(creates,[{'acor':[reader],'acop':1,'acod':[{'ty':3,'chty':[23]}]}])

    def test_callback_ports_and_blocked_group_runner(self):
        self.assertEqual(display_callbacks(Settings())['display-c'],'http://127.0.0.1:8003/onem2m/notify')
        with tempfile.TemporaryDirectory() as directory:
            with patch('backend.p1_routes.socket.socket',side_effect=PermissionError('unit denial')):
                summary,path=run(Settings(evidence_root=Path(directory)),require_target_python=False,with_displays=True)
            self.assertEqual((summary['test'],summary['state'],summary['pass']),('P1_GROUP','BLOCKED',0))


class TypedNotificationTests(unittest.TestCase):
    def test_commands_and_acks_use_their_own_ids_without_sensor_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            store=NotificationStore(Path(directory)/'notifications.sqlite3')
            service=NotificationService(store,'/unit-cse','4',frozenset())
            service.approve({'/unit-cse/command-sub'},decoder=lambda d:DisplayCommand.parse(d,EXITS),identity_field='command_id')
            service.approve({'/unit-cse/ack-sub'},decoder=DisplayAck.parse,identity_field='ack_id')
            for ref,data,key in [('/unit-cse/command-sub',command().to_dict(),'unit-command'),('/unit-cse/ack-sub',ack().to_dict(),ack().ack_id)]:
                body={'m2m:sgn':{'sur':ref,'nev':{'net':3,'rep':{'m2m:cin':{'ty':4,'ri':'unit-'+key,'con':json.dumps(data)}}}}}
                headers={'X-M2M-Origin':'/unit-cse','X-M2M-RI':'unit-rqi','Content-Type':'application/json'}
                wire=json.dumps(body).encode()
                self.assertEqual(service.handle(headers,wire).kind,'event')
                self.assertEqual(service.handle(headers,wire).kind,'duplicate')
                self.assertEqual(store.find(key)[0]['event'],data)
            self.assertEqual(len(store.records()),2)
