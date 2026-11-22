"""Explicit local model/SQLite/HTTP fixtures, never actual MEC/CSE evidence."""
import copy
from datetime import datetime, timedelta, timezone
import io
from email.message import Message as Headers
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from infra.mec.patch_couch_auth import patched
from infra.mec_services import private_environment
from mec.interworking.worker import Outbox, analyse, decode_request, digest
from mec.interworking.client import verified_result, VerifiedRemoteSnapshot, remove_observer
from mec.risk.service import RiskJournal, fresh, handler
from mec.service_client import LocalHTTP, ServiceError, discover_risk, register_risk
from onem2m.client import CSEClient, CSEError, ProtocolError, TransportError, WireResponse
from simulator.evacuation import Evacuation, FrameOrderError
from simulator.scenario_frames import PROFILE, ZONES, emission, source_manifest

HASH=source_manifest()['bundle_sha256']
APP='00000000-0000-4000-8000-000000000001';SID='00000000-0000-4000-8000-000000000002'


def frame(second=0):
    return emission({'schema_version':1,'profile_id':PROFILE,'source_manifest_sha256':HASH,'seed':59,
        'wind_mps':5,'simulation_second':second,'ended':False,
        'zones':[{'zone_id':n,'fire_index':0,'smoke_index':0,'collapsed':False} for n in ZONES]},
        'inc-unit','unit:source',HASH)


def request_frame(value=None):
    return {'schema_version':1,'kind':'FireRouteRiskRequest','event_id':'req-'+uuid4().hex,
            'frame':(value or frame()).to_dict()}


def service():
    return {'serInstanceId':SID,'serName':'FireRoute Risk v1','version':'1.0','state':'ACTIVE','serializer':'JSON',
            'transportInfo':{'endpoint':{'uris':['http://mec-risk:8081/v1/frames']}}}


class RiskPersistenceTests(unittest.TestCase):
    def test_exact_duplicate_does_not_move_and_restart_recovers_same_model(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'risk.db';journal=RiskJournal(p);model=Evacuation()
            for second in range(3):
                value=frame(second);model.accept(value)
                self.assertEqual(journal.apply(value.to_dict()),model.snapshot())
                self.assertEqual(journal.apply(value.to_dict()),model.snapshot())
            restarted=RiskJournal(p);value=frame(3);model.accept(value)
            self.assertEqual(restarted.apply(value.to_dict()),model.snapshot())
            with sqlite3.connect(p) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM frames').fetchone()[0],4)

    def test_conflict_skipped_old_and_context_inputs_do_not_advance(self):
        with tempfile.TemporaryDirectory() as d:
            journal=RiskJournal(Path(d)/'risk.db');zero=frame();one=frame(1)
            journal.apply(zero.to_dict());good=journal.apply(one.to_dict())
            conflict=copy.deepcopy(one.to_dict());conflict['event_id']='conflict'
            for bad in [conflict,zero.to_dict(),frame(3).to_dict()]:
                with self.assertRaises(FrameOrderError):journal.apply(bad)
            self.assertEqual(journal.apply(one.to_dict()),good)

    def test_expired_nonfinite_and_invalid_frame_fail_without_journal_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'risk.db';journal=RiskJournal(p)
            expired=frame().to_dict();expired['timestamp_utc']='2020-01-01T00:00:00Z'
            nonfinite=frame().to_dict();nonfinite['zones'][0]['fire_index']=float('nan')
            for bad in [expired,nonfinite,{}]:
                with self.assertRaises(ValueError):journal.apply(bad)
            with sqlite3.connect(p) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM frames').fetchone()[0],0)

    def test_future_and_boundary_freshness(self):
        value=frame();stamp=datetime.fromisoformat(value.data['timestamp_utc'].replace('Z','+00:00'))
        fresh(value,stamp+timedelta(seconds=29))
        for now in [stamp+timedelta(seconds=30),stamp-timedelta(seconds=6)]:
            with self.assertRaises(ValueError):fresh(value,now)


class NativeRegistrationFixtureTests(unittest.TestCase):
    def clients(self, existing=False):
        controller=Mock();controller.call.side_effect=lambda method,path,*args,**kw: {'id':APP,'name':'FireRoute Risk v1','nodeName':'mep1'}
        platform=Mock()
        def call(method,path,body=None,**kwargs):
            if path.endswith('/confirm_ready'):return None
            if path.endswith('/'+SID):return service()
            return service() if method=='POST' else [service()] if existing else []
        platform.call.side_effect=call
        return controller,platform

    def test_native_assigned_app_and_service_ids_are_not_submitted_as_invented_ids(self):
        controller,platform=self.clients();saved=[]
        result=register_risk(controller,platform,'FireRoute Risk v1',save=lambda x:saved.append(copy.deepcopy(x)))
        self.assertEqual(result['app_id'],APP);self.assertEqual(result['service_id'],SID)
        self.assertNotIn('id',controller.call.call_args_list[0].args[2])
        posts=[c for c in platform.call.call_args_list if c.args[0]=='POST' and c.args[1].endswith('/services')]
        self.assertEqual(len(posts),1);self.assertNotIn('serInstanceId',posts[0].args[2])
        self.assertTrue(saved[0]['app_create_attempted']);self.assertTrue(any(x.get('service_create_attempted') for x in saved))

    def test_restart_verifies_owned_registration_without_recreating_app_or_service(self):
        controller,platform=self.clients(existing=True)
        result=register_risk(controller,platform,'FireRoute Risk v1',saved={'app_id':APP,'name':'FireRoute Risk v1','service_create_attempted':True})
        self.assertEqual(result['service_id'],SID)
        self.assertFalse(any(c.args[0]=='POST' for c in controller.call.call_args_list))
        self.assertFalse(any(c.args[0]=='POST' and c.args[1].endswith('/services') for c in platform.call.call_args_list))

    def test_ambiguous_app_create_is_not_replayed(self):
        controller,platform=self.clients();controller.call.return_value=[];controller.call.side_effect=None
        with self.assertRaises(ServiceError):register_risk(controller,platform,'FireRoute Risk v1',saved={'name':'FireRoute Risk v1','app_create_attempted':True})
        self.assertEqual(controller.call.call_count,1);self.assertEqual(controller.call.call_args.args[0],'GET')

    def test_ambiguous_service_create_is_not_replayed(self):
        controller,platform=self.clients()
        with self.assertRaises(ServiceError):register_risk(controller,platform,'FireRoute Risk v1',saved={'name':'FireRoute Risk v1','app_id':APP,'service_create_attempted':True})
        self.assertFalse(any(c.args[0]=='POST' and c.args[1].endswith('/services') for c in platform.call.call_args_list))

    def test_discovery_rejects_missing_duplicate_inactive_and_unapproved_endpoint(self):
        platform=Mock()
        bad=service();bad['transportInfo']['endpoint']['uris']=['http://169.254.169.254/latest']
        inactive=service();inactive['state']='INACTIVE'
        for rows in [[],[service(),service()],[bad],[inactive],[None],{}]:
            platform.call.return_value=rows
            with self.assertRaises(ServiceError):discover_risk(platform,'FireRoute Risk v1',SID)

    def test_local_client_rejects_public_hosts_unsafe_paths_and_nonfinite_body(self):
        with self.assertRaises(ValueError):LocalHTTP('http://8.8.8.8')
        client=LocalHTTP('http://127.0.0.1');client.opener=Mock()
        for path in ['/../admin','/x?url=external','http://external']:
            with self.assertRaises(ValueError):client.call('GET',path)
        with self.assertRaises(ValueError):client.call('POST','/v1/frames',{'a':float('nan')})
        client.opener.open.assert_not_called()


class ProjectIPEFixtureTests(unittest.TestCase):
    def test_typed_request_does_not_allow_remote_url_or_arbitrary_operation(self):
        document=request_frame();self.assertEqual(decode_request(document).to_dict(),document)
        for bad in [{**document,'url':'http://public'}, {**document,'kind':'Shell'}, {**document,'event_id':'../x'}]:
            with self.assertRaises(ValueError):decode_request(bad)

    def test_real_boundary_projection_binds_source_and_keeps_individual_residents_private(self):
        document=request_frame();model=Evacuation();model.accept(frame_from(document));full=model.snapshot()
        platform=Mock();platform.call.return_value=[service()]
        provider=Mock();provider.call.return_value={'state':'ACCEPTED','result':full}
        result=analyse(document,platform,provider,{'app_id':APP,'service_id':SID})
        self.assertEqual(result['state'],'ACCEPTED');self.assertEqual(result['result_sha256'],digest(full))
        self.assertEqual(result['analysis']['population'],full['population']);self.assertNotIn('residents',result['analysis'])

    def test_invalid_unavailable_or_expired_result_cannot_return_old_route(self):
        document=request_frame();platform=Mock();platform.call.return_value=[service()]
        provider=Mock();provider.call.side_effect=ServiceError()
        result=analyse(document,platform,provider,{'app_id':APP,'service_id':SID})
        self.assertEqual(result['state'],'UNKNOWN');self.assertIsNone(result['route']);self.assertIsNone(result['analysis'])
        document['frame']['timestamp_utc']='2020-01-01T00:00:00Z';provider.call.reset_mock()
        result=analyse(document,platform,provider,{'app_id':APP,'service_id':SID})
        self.assertEqual(result['state'],'UNKNOWN');provider.call.assert_not_called()

    def test_bad_reply_identity_or_response_that_expires_in_transit_fails_closed(self):
        document=request_frame();model=Evacuation();model.accept(frame_from(document));full=model.snapshot()
        platform=Mock();platform.call.return_value=[service()];provider=Mock()
        provider.call.return_value={'state':'ACCEPTED','result':{**full,'event_id':'wrong'}}
        self.assertEqual(analyse(document,platform,provider,{'app_id':APP,'service_id':SID})['state'],'UNKNOWN')
        provider.call.return_value={'state':'ACCEPTED','result':full}
        with patch('mec.interworking.worker.fresh',side_effect=[None,ValueError('expired')]):
            self.assertIsNone(analyse(document,platform,provider,{'app_id':APP,'service_id':SID})['route'])

    def test_outbox_no_uncertain_CIN_create_replay_then_actual_read_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            outbox=Outbox(Path(d)/'out.db');client=Mock();client.resource=CSEClient.resource
            client.retrieve.side_effect=CSEError('fixture not found',http_status=404,rsc=4004)
            client.create.side_effect=TransportError('fixture lost response')
            doc=request_frame();calculate=Mock(return_value={'event_id':doc['event_id'],'state':'UNKNOWN','route':None})
            with self.assertRaises(TransportError):outbox.process(doc,calculate,client,'/unit/results')
            self.assertIsNone(outbox.process(doc,calculate,client,'/unit/results'))
            self.assertEqual(client.create.call_count,1);calculate.assert_called_once()
            payload=calculate.return_value
            client.retrieve.side_effect=None;client.retrieve.return_value={'m2m:cin':{'ty':4,'ri':'unit-CIN','con':json.dumps(payload)}}
            self.assertEqual(outbox.process(doc,calculate,client,'/unit/results'),payload)
            self.assertEqual(client.create.call_count,1)
            self.assertIn(doc['event_id'],Outbox(Path(d)/'out.db').completed)
            conflict=copy.deepcopy(doc);conflict['frame']['event_id']='different'
            with self.assertRaises(ProtocolError):outbox.process(conflict,calculate,client,'/unit/results')

    def test_pending_result_expiry_clears_the_route_before_any_CIN_create(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'out.db';outbox=Outbox(path);doc=request_frame()
            old={'state':'ACCEPTED','analysis':{'unit':'old'},'route':{'path':['old']},
                 'valid_until_utc':'2020-01-01T00:00:00Z'}
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO output VALUES (?,?,?,?,?)',(doc['event_id'],digest(doc),json.dumps(old),'PREPARED',None))
            stored={};client=Mock();client.resource=CSEClient.resource
            def retrieve(_):
                if not stored:raise CSEError('fixture missing',http_status=404,rsc=4004)
                return {'m2m:cin':stored}
            def create(parent,kind,attrs):
                stored.update(ty=4,ri='unit-late',con=attrs['con']);return {'m2m:cin':stored}
            client.retrieve.side_effect=retrieve;client.create.side_effect=create
            calculate=Mock();result=outbox.process(doc,calculate,client,'/unit/results')
            self.assertEqual(result['state'],'UNKNOWN');self.assertIsNone(result['route']);self.assertIsNone(result['analysis'])
            calculate.assert_not_called();client.create.assert_called_once()

    def test_outbox_permission_denial_never_triggers_resource_creation(self):
        with tempfile.TemporaryDirectory() as d:
            outbox=Outbox(Path(d)/'out.db');doc=request_frame();client=Mock()
            client.retrieve.side_effect=CSEError('fixture denial',http_status=403,rsc=4103)
            with self.assertRaises(CSEError):outbox.process(doc,lambda _: {'state':'UNKNOWN'},client,'/unit/results')
            client.create.assert_not_called()


def frame_from(document):
    from simulator.scenario_frames import ScenarioFrame
    return ScenarioFrame.parse(document['frame'])


class LocalPreparationTests(unittest.TestCase):
    def test_private_configuration_is_stable_separated_and_refuses_symlinks_or_public_mode(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'couch.env';private_environment(p);before=p.read_bytes();private_environment(p)
            self.assertEqual(p.read_bytes(),before);self.assertEqual(p.stat().st_mode & 0o777,0o600)
            self.assertNotIn(b'FR_RISK',before)
            key=Path(d)/'risk.env';private_environment(key,kind='risk');self.assertNotIn(b'COUCHDB',key.read_bytes())
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):private_environment(link)
            p.chmod(0o644)
            with self.assertRaises(ValueError):private_environment(p)

    def test_reviewed_build_auth_patch_changes_only_two_literals_and_import(self):
        source='import (\n"context"\n)\n'+('Username: "admin", Password: "admin"\n'*2)
        result=patched(source)
        self.assertEqual(result.count('os.Getenv("COUCHDB_PASSWORD")'),2)
        self.assertNotIn('Password: "admin"',result)
        with self.assertRaises(ValueError):patched(source+'"context"')


class ProviderHTTPFixtureTests(unittest.TestCase):
    """Exercise real handler methods with in-memory request fixtures; no server."""
    def operation(self,body,*,key='a'*64,media='application/json',size=None,ready=True):
        journal=Mock();journal.apply.return_value={'event_id':'unit-event'}
        cls=handler(journal,'a'*64,{'ready':ready})
        obj=object.__new__(cls);obj.path='/v1/frames';obj.headers=Headers()
        obj.headers['X-FireRoute-Key']=key;obj.headers['Content-Type']=media
        obj.headers['Content-Length']=str(len(body) if size is None else size)
        obj.rfile=io.BytesIO(body);obj.connection=Mock();obj.reply=Mock()
        obj.do_POST()
        return obj.reply.call_args.args,journal

    def test_missing_wrong_nonascii_identity_is_denied_before_parsing_or_computation(self):
        for key in ['', 'b'*64, 'wrong-\u00e9']:
            (status,_),journal=self.operation(b'{}',key=key)
            self.assertEqual(status,403);journal.apply.assert_not_called()

    def test_oversize_wrong_media_truncated_and_nonfinite_requests_are_rejected(self):
        for body,kwargs in [(b'{}',{'size':65537}),(b'{}',{'media':'text/plain'}),
                            (b'{',{'size':10}),(b'{"x":NaN}',{})]:
            (status,payload),journal=self.operation(body,**kwargs)
            self.assertEqual(status,422);self.assertIsNone(payload['route']);journal.apply.assert_not_called()

    def test_starting_provider_returns_unknown_and_valid_private_request_calls_model_once(self):
        (status,payload),journal=self.operation(b'{}',ready=False)
        self.assertEqual(status,503);self.assertIsNone(payload['route']);journal.apply.assert_not_called()
        (status,payload),journal=self.operation(b'{}')
        self.assertEqual(status,200);self.assertEqual(payload['state'],'ACCEPTED');journal.apply.assert_called_once_with({})


class MecDashboardDecisionTests(unittest.TestCase):
    def fixture(self):
        document=request_frame();model=Evacuation();model.accept(frame_from(document));full=model.snapshot()
        platform=Mock();platform.call.return_value=[service()];provider=Mock()
        provider.call.return_value={'state':'ACCEPTED','result':full}
        response=analyse(document,platform,provider,{'app_id':APP,'service_id':SID})
        return document,model,full,response

    def test_verified_remote_snapshot_preserves_private_state_and_delegates_graph(self):
        document,model,full,reply=self.fixture()
        result=verified_result(reply,document['frame'],full)
        wrapped=VerifiedRemoteSnapshot(model,result)
        self.assertEqual(wrapped.snapshot(),full);self.assertIs(wrapped.navigation,model.navigation)
        self.assertIs(wrapped.last,model.last)

    def test_unknown_wrong_source_hash_projection_and_expiry_do_not_authorize_publish(self):
        document,model,full,reply=self.fixture()
        mutations=[{'state':'UNKNOWN'}, {'source_event_id':'wrong'}, {'result_sha256':'0'*64},
                   {'analysis':{}},{'valid_until_utc':'2020-01-01T00:00:00Z'},
                   {'valid_until_utc':'2099-01-01T00:00:00Z'}, {'route':None}]
        for change in mutations:
            with self.subTest(change=next(iter(change))),self.assertRaises(ProtocolError):
                verified_result({**reply,**change},document['frame'],full)

    def test_optional_session_injection_keeps_the_default_factory_unmodified(self):
        from backend.config import Settings
        from backend.scenario_demo import ScenarioApp
        with tempfile.TemporaryDirectory() as d:
            settings=Settings(evidence_root=Path(d))
            normal=ScenarioApp(settings,Path(d)/'trace')
            self.assertIsNone(normal.session_factory)
            factory=Mock();optional=ScenarioApp(settings,Path(d)/'trace',session_factory=factory)
            self.assertIs(optional.session_factory,factory)

    def test_MEC_publication_failure_never_falls_back_to_local_route(self):
        from backend.config import Settings
        from mec.dashboard import MecSession
        with tempfile.TemporaryDirectory() as d:
            context=MecSession(Settings(evidence_root=Path(d)))
            with self.assertRaises(ProtocolError):context.publish()


class ObserverCleanupTests(unittest.TestCase):
    def reference(self):
        return {'path':'/unit/results/observer-unit','ri':'sub-unit','owner':'owner:unit','callback':'http://unit.invalid/onem2m/notify'}

    def test_single_delete_requires_correlated_HTTP_200_and_DELETED_RSC(self):
        for status,rsc,okay in [(200,'2002',True),(200,'2000',False),(202,'2002',False),(500,'2002',False)]:
            calls=[]
            def transport(method,url,headers,body,timeout):
                calls.append((method,body))
                return WireResponse(status,{'X-M2M-RI':headers['X-M2M-RI'],'X-M2M-RSC':rsc,'X-M2M-RVI':'4'},b'')
            client=CSEClient('http://unit.invalid','C-unit','4',transport=transport)
            if okay:self.assertEqual(client.delete('/unit/sub'),{})
            else:
                with self.assertRaises(CSEError):client.delete('/unit/sub')
            self.assertEqual(calls,[('DELETE',None)])
        transport=Mock(side_effect=TransportError('fixture uncertain DELETE'))
        with self.assertRaises(TransportError):CSEClient('http://unit.invalid','C-unit','4',transport=transport).delete('/unit/sub')
        transport.assert_called_once()

    def test_observer_cleanup_proves_ownership_then_native_absence(self):
        ref=self.reference();admin=Mock();admin.resource=CSEClient.resource
        before={'m2m:sub':{'ty':23,'ri':ref['ri'],'nu':[ref['callback']],'lbl':[ref['owner']]}}
        admin.retrieve.side_effect=[before,CSEError('fixture absent',http_status=404,rsc=4004)]
        remove_observer(admin,ref);admin.delete.assert_called_once_with(ref['path'])
        self.assertEqual(admin.retrieve.call_count,2)

    def test_unowned_or_replaced_observer_is_never_deleted(self):
        ref=self.reference()
        for changes in [{'ri':'other'},{'nu':['http://other.invalid']},{'lbl':['owner:other']}]:
            admin=Mock();admin.resource=CSEClient.resource
            admin.retrieve.return_value={'m2m:sub':{'ty':23,'ri':ref['ri'],'nu':[ref['callback']],'lbl':[ref['owner']],**changes}}
            with self.assertRaises(ProtocolError):remove_observer(admin,ref)
            admin.delete.assert_not_called()


if __name__=='__main__':unittest.main()
