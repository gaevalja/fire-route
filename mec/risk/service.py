"""Independent FireRoute risk provider, registered through actual official MEC APIs."""
import copy
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
from threading import Event, Lock, Thread

from backend.evidence import Evidence, source_identity
from mec.service_client import LocalHTTP, register_risk
from onem2m.client import strict_json
from simulator.commands import utc_time
from simulator.evacuation import Evacuation, FrameOrderError
from simulator.scenario_frames import ScenarioFrame, source_manifest


def fresh(frame, now=None):
    now=now or datetime.now(timezone.utc)
    age=(now-utc_time(frame.data['timestamp_utc'])).total_seconds()
    if not -5<=age<30:raise ValueError('EXPIRED_OR_FUTURE_FRAME')


class RiskJournal:
    def __init__(self, path, *, compare=False):
        self.path=path;self.lock=Lock();self.models=OrderedDict()
        self.compare=compare
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS frames (incident TEXT, seq INTEGER, frame TEXT, result TEXT, PRIMARY KEY(incident,seq))')

    def apply(self, raw):
        frame=ScenarioFrame.parse(raw,source_manifest()['bundle_sha256']);fresh(frame)
        incident=raw['incident_id'];sequence=raw['sequence']
        encoded=json.dumps(raw,sort_keys=True,allow_nan=False)
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            old=db.execute('SELECT frame,result FROM frames WHERE incident=? AND seq=?',(incident,sequence)).fetchone()
            if old:
                if old[0]!=encoded:raise FrameOrderError('CONFLICTING_FRAME')
                latest=db.execute('SELECT MAX(seq) FROM frames WHERE incident=?',(incident,)).fetchone()[0]
                if latest!=sequence:raise FrameOrderError('OUTDATED_FRAME')
                return strict_json(old[1])
            if incident not in self.models:
                model=Evacuation(compare=self.compare)
                for row in db.execute('SELECT frame FROM frames WHERE incident=? ORDER BY seq',(incident,)):
                    model.accept(ScenarioFrame.parse(strict_json(row[0])))
            else:model=copy.deepcopy(self.models[incident])
            if db.execute('SELECT COUNT(*) FROM frames').fetchone()[0]>=20000:raise ValueError('FRAME_LIMIT')
            model.accept(frame)
            result=model.snapshot()
            db.execute('INSERT INTO frames VALUES (?,?,?,?)',(incident,sequence,encoded,json.dumps(result,sort_keys=True,allow_nan=False)))
            db.commit();self.models[incident]=model;self.models.move_to_end(incident)
            if len(self.models)>16:self.models.popitem(last=False)
            return result


def handler(journal, access_key, state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body):
            raw=json.dumps(body,allow_nan=False,separators=(',',':')).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if self.path!='/health':return self.reply(404,{'state':'NOT_FOUND'})
            self.reply(200 if state.get('ready') else 503,{'state':'READY' if state.get('ready') else 'STARTING',
                'registration':state.get('registration'),'kind':'FIREROUTE_RISK_SERVICE_NOT_MEC_PLATFORM'})
        def do_POST(self):
            if self.path!='/v1/frames':return self.reply(404,{'state':'NOT_FOUND'})
            supplied=self.headers.get('X-FireRoute-Key','')
            if not access_key or not supplied.isascii() or not hmac.compare_digest(supplied,access_key):return self.reply(403,{'state':'DENIED'})
            if not state.get('ready'):return self.reply(503,{'state':'UNKNOWN','route':None})
            self.connection.settimeout(8)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=65536 or self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':
                    raise ValueError('BAD_BODY')
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('SHORT_BODY')
                result=journal.apply(strict_json(raw))
            except (ValueError,KeyError,TypeError,RecursionError):
                return self.reply(422,{'state':'REJECTED','guidance_status':'UNKNOWN','route':None})
            except (OSError,sqlite3.Error):
                return self.reply(503,{'state':'UNKNOWN','route':None})
            self.reply(200,{'schema_version':1,'state':'ACCEPTED','result':result,
                'provider':'FIREROUTE_CUSTOM_RISK','deployment':'EXTERNAL_COMPOSE_APP_REGISTERED_WITH_OFFICIAL_MEC'})
    return Handler


def main():
    if not re.fullmatch('[0-9a-f]{64}',os.environ.get('FR_RISK_ACCESS_KEY','')):
        print(json.dumps({'state':'BLOCKED','reason':'PRIVATE_RISK_ACCESS_CONFIGURATION_REQUIRED'}),flush=True)
        return 2
    directory=Path(os.environ.get('FR_PROVIDER_STATE','/state'));directory.mkdir(parents=True,exist_ok=True)
    ev=Evidence(Path(os.environ.get('EVIDENCE_ROOT','evidence')),
                secret_values=(os.environ.get('FR_RISK_ACCESS_KEY',''),))
    state={};journal=RiskJournal(directory/'risk.sqlite3',compare=os.getenv('FIREROUTE_POLICY_COMPARISON') == '1')
    server=ThreadingHTTPServer(('0.0.0.0',8081),handler(journal,os.environ.get('FR_RISK_ACCESS_KEY',''),state))
    server.daemon_threads=True
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        target=directory/'registration.json'
        saved=strict_json(target.read_bytes()) if target.exists() else None
        def save(data):
            temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(data));temporary.replace(target)
        controller=LocalHTTP('http://mec-controller',aliases=('mec-controller',),evidence=ev)
        platform=LocalHTTP('http://mec-platform',aliases=('mec-platform',),evidence=ev)
        registration=register_risk(controller,platform,'FireRoute Risk v1',saved=saved,save=save)
        state.update(ready=True,registration=registration)
        ev.write('registration.json',registration);ev.write('meta.json',source_identity(Path.cwd()))
        print(json.dumps({'state':'RISK_SERVICE_READY','app_id':registration['app_id'],
            'service_id':registration['service_id'],'Hosted':'NOT_CONTACTED','evidence':str(ev.path)}),flush=True)
        stop=Event()
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
        stop.wait()
    except Exception as exc:
        ev.write('summary.json',{'state':'FAIL','reason':type(exc).__name__,'Hosted':'NOT_CONTACTED'})
        print(json.dumps({'state':'FAIL','reason':type(exc).__name__,'evidence':str(ev.path)}),flush=True)
        return 1
    finally:
        state['ready']=False;server.shutdown();server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
