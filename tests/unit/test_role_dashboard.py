"""Offline role/auth/read-model regressions; no actual CSE/HTTP success claimed."""
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from backend.auth import AuthStore,digest,prepare_access
from backend.config import Settings
from backend.http_api import api_server
from backend.views import LiveViews
from backend.notifications import NotificationStore
from mec.risk.routing import BuildingGraph
from onem2m.client import ProtocolError,TransportError
from simulator.events import ContractError
from simulator.occupancy import OccupancyObservation

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,11,12,10,tzinfo=timezone.utc)


class AuthTests(unittest.TestCase):
    def test_long_running_notification_reads_close_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            store=NotificationStore(Path(directory)/'unit.sqlite3')
            with store.connect() as db:self.assertEqual(db.execute('SELECT 1').fetchone(),(1,))
            with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')

    def setUp(self):
        self.now=100
        self.auth=AuthStore({'resident':digest('unit-resident'),'responder':digest('unit-responder')},clock=lambda:self.now,lifetime=10)

    def test_role_code_cannot_escalate(self):
        token,state=self.auth.login('resident','unit-resident','unit-peer')
        self.assertEqual((state,self.auth.role(token)),('OK','resident'))
        self.assertIsNone(self.auth.login('responder','unit-resident','unit-peer')[0])
        self.assertIsNone(self.auth.role('invented-cookie'))
        self.assertIsNone(self.auth.login([],{},'unit-peer')[0])

    def test_session_expiry_and_logout(self):
        token,_=self.auth.login('responder','unit-responder','unit-peer')
        self.now=110
        self.assertIsNone(self.auth.role(token))
        token,_=self.auth.login('responder','unit-responder','unit-peer')
        self.auth.logout(token);self.assertIsNone(self.auth.role(token))

    def test_failed_login_rate_limit_and_recovery(self):
        for _ in range(5):self.assertEqual(self.auth.login('responder','wrong','peer')[1],'UNAUTHORIZED')
        self.assertEqual(self.auth.login('responder','unit-responder','peer')[1],'RATE_LIMITED')
        self.now+=60
        self.assertEqual(self.auth.login('responder','unit-responder','peer')[1],'OK')

    def test_access_files_private_stable_and_mismatch_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);prepare_access(p)
            before=(p/'access-codes.json').read_bytes()
            self.assertEqual((p/'access-codes.json').stat().st_mode&0o777,0o600)
            self.assertEqual((p/'auth.json').stat().st_mode&0o777,0o600)
            prepare_access(p);self.assertEqual((p/'access-codes.json').read_bytes(),before)
            hashes=json.loads((p/'auth.json').read_text());hashes['resident']=digest('different')
            (p/'auth.json').write_text(json.dumps(hashes))
            with self.assertRaises(ValueError):prepare_access(p)
            self.assertEqual((p/'access-codes.json').read_bytes(),before)

    def test_incomplete_or_world_readable_access_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);prepare_access(p);(p/'access-codes.json').chmod(0o644)
            with self.assertRaises(ValueError):prepare_access(p)
            (p/'auth.json').unlink()
            with self.assertRaises(ValueError):prepare_access(p)


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.graph=BuildingGraph.load(ROOT/'fixtures/building_3f.json')
        self.resources={'containers':{k:{'path':'/unit/'+k} for k in ['controller/routes','controller/status','controller/hazards','controller/diagnostics','occupancy/observations']}}
        self.base={'schema_version':1,'incident_id':'inc-unit','event_id':'e-unit','route_version':1,'timestamp_utc':NOW.isoformat(),'source':'unit','data_origin':'SYNTHETIC'}
        route=self.graph.route(self.graph.origin)
        self.payloads={
            'controller/routes':{**self.base,'source_node':self.graph.origin,'target_exit':route.target_exit,'path':list(route.path),'blocked_nodes':[],'status':route.status},
            'controller/status':{**self.base,'observed_at_utc':NOW.isoformat(),'delivery':{'state':'ALL_ACKED','ack_count':3,'expected_ack_count':3}},
            'controller/hazards':{**self.base,'blocked_nodes':[]},
            'controller/diagnostics':{**self.base,'devices':[{'device':'display-a','status':'APPLIED','ack_timestamp_utc':NOW.isoformat(),'private':'must-not-leak'}],'sensors':[]},
            'occupancy/observations':{'schema_version':1,'incident_id':'inc-unit','data_origin':'SYNTHETIC','observations':[
                {'schema_version':1,'event_id':'o-unit','incident_id':'inc-unit','zone_id':'F3_ROOM1','remaining_count':None,'sequence':1,'timestamp_utc':NOW.isoformat(),'source':'unit:occupancy','data_origin':'SYNTHETIC'}]}}
        self.paths=[]
        def retrieve(path):
            self.paths.append(path)
            key=path.removeprefix('/unit/').removesuffix('/la')
            return {'m2m:cin':{'ri':'unit-'+key,'ty':4,'con':json.dumps(self.payloads[key])}}
        from onem2m.client import CSEClient
        self.client=Mock();self.client.retrieve.side_effect=retrieve;self.client.resource.side_effect=CSEClient.resource
        self.views=LiveViews({'resident':self.client,'responder':self.client},self.resources,self.graph,'inc-unit',Settings())

    def test_resident_has_approved_route_without_diagnostics_or_occupants(self):
        view=self.views.read('resident',now=NOW)
        self.assertEqual(view['route']['target_exit'],'EXIT_A')
        for key in ['occupants','sensors','devices','hazards']:self.assertNotIn(key,view)
        self.assertEqual(len(self.paths),2)
        with self.assertRaises(PermissionError):self.views.read('resident',diagnostics=True,now=NOW)
        self.assertEqual(len(self.paths),2)

    def test_stale_future_or_mismatched_version_has_no_directions(self):
        for now,status in [(NOW+timedelta(seconds=30),'STALE'),(NOW-timedelta(seconds=6),'UNKNOWN')]:
            result=self.views.read('resident',now=now)
            self.assertEqual(result['guidance_status'],status);self.assertIsNone(result['route'])
        self.payloads['controller/status']['route_version']=2
        result=self.views.read('resident',now=NOW)
        self.assertEqual(result['guidance_status'],'PENDING');self.assertIsNone(result['route'])

    def test_responder_occupants_unknown_not_zero_and_fields_filtered(self):
        view=self.views.read('responder',diagnostics=True,now=NOW)
        self.assertIsNone(view['occupants'][0]['remaining_count'])
        self.assertEqual(view['occupants'][0]['status'],'UNKNOWN')
        self.assertNotIn('private',view['devices'][0])
        self.payloads['occupancy/observations']['observations'][0]['remaining_count']=2
        view=self.views.read('responder',diagnostics=True,now=NOW+timedelta(seconds=31))
        self.assertIsNone(view['occupants'][0]['remaining_count'])
        self.assertEqual(view['devices'][0]['status'],'STALE')

    def test_actual_no_route_shape_has_no_directions(self):
        route=self.payloads['controller/routes']
        route.update(blocked_nodes=['F2_A','F2_B'],status='NO_VERIFIED_ROUTE',target_exit=None,path=[])
        view=self.views.read('resident',now=NOW)
        self.assertEqual(view['guidance_status'],'NO_VERIFIED_ROUTE');self.assertIsNone(view['route'])

    def test_malformed_delivery_or_route_not_trusted(self):
        self.payloads['controller/status']['delivery']['ack_count']=True
        with self.assertRaises(ProtocolError):self.views.read('resident',now=NOW)
        self.payloads['controller/status']['delivery']['ack_count']=3
        self.payloads['controller/routes']['path']=['F3_ROOM1','EXIT_B']
        with self.assertRaises(ProtocolError):self.views.read('resident',now=NOW)

    def test_responder_correlation_change_is_pending(self):
        self.payloads['controller/diagnostics']['event_id']='older'
        result=self.views.read('responder',diagnostics=True,now=NOW)
        self.assertEqual(result['guidance_status'],'PENDING');self.assertIsNone(result['route'])


class HTTPPolicyTests(unittest.TestCase):
    def handler(self,role='resident',path='/api/v1/incidents/inc-unit/responder'):
        with patch('backend.http_api.ThreadingHTTPServer') as server:
            app=Mock();auth=Mock(lifetime=1200);auth.role.return_value=role
            api_server('unit.invalid',3000,app,auth,'http://127.0.0.1:3000',ROOT/'frontend')
            cls=server.call_args.args[1]
        handler=object.__new__(cls)
        handler.path=path;handler.headers={'Host':'127.0.0.1:3000','Origin':'http://127.0.0.1:3000','Content-Type':'application/json'}
        handler.client_address=('unit-peer',1);handler.send=Mock();handler.rfile=BytesIO()
        return handler,app,auth

    def test_direct_responder_GET_denied_before_data_read(self):
        handler,app,_=self.handler();handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],403);app.view.assert_not_called()

    def test_unauthed_API_and_arbitrary_static_path_denied(self):
        handler,_,_=self.handler(role=None,path='/api/v1/status');handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],401)
        handler,_,_=self.handler(path='/../../.env');handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],404)

    def test_cross_origin_and_resident_scenario_write_denied(self):
        handler,app,_=self.handler(path='/api/v1/scenario')
        handler.headers['Origin']='https://foreign.invalid';handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0],403);app.enqueue.assert_not_called()
        handler,app,_=self.handler(path='/api/v1/scenario');body=b'{"action":"fire_a"}'
        handler.headers['Content-Length']=str(len(body));handler.connection=Mock();handler.rfile=BytesIO(body);handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0],403);app.enqueue.assert_not_called()

    def test_CSE_failure_returns_unknown_without_cached_direction(self):
        handler,app,_=self.handler(path='/api/v1/incidents/inc-unit/resident')
        app.view.side_effect=TransportError('unit transport interrupted');handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0],503)
        self.assertIsNone(handler.send.call_args.args[1]['route'])
        self.assertEqual(handler.send.call_args.args[1]['guidance_status'],'UNKNOWN')

    def test_cookie_security_flags(self):
        handler,_,_=self.handler()
        value=handler.session_cookie('unit-cookie')
        self.assertIn('HttpOnly',value);self.assertIn('SameSite=Strict',value)


class OccupancyTests(unittest.TestCase):
    def test_invalid_counts_or_physical_claim_rejected(self):
        row={'schema_version':1,'event_id':'unit','incident_id':'inc-unit','zone_id':'F3_ROOM1','remaining_count':None,'sequence':1,'timestamp_utc':NOW.isoformat(),'source':'unit','data_origin':'SYNTHETIC'}
        for update in [{'remaining_count':True},{'remaining_count':-1},{'data_origin':'PHYSICAL'},{'zone_id':'missing'},{'sequence':True}]:
            with self.subTest(update=update),self.assertRaises(ContractError):
                OccupancyObservation.parse({**row,**update},{'F3_ROOM1'})
