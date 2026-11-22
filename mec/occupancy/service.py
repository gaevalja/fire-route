"""Independent FireRoute occupancy-estimate provider, registered through actual official MEC APIs.

A second MEC service beside the risk provider. It consumes only anonymous
access-passage batches with their aligned Wi-Fi/BLE presence-scan batches
and keeps a per-incident SQLite journal so a restart
rebuilds the same estimate. Retention is explicit: the newest
RETAINED_INCIDENTS incidents are kept; older incidents are pruned when a new
incident starts, and one incident is capped at MAX_BATCHES_PER_INCIDENT.
"""
from collections import OrderedDict
from contextlib import closing
import copy
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
from mec.occupancy.estimator import OccupancyEstimator, BatchOrderError
from mec.risk.evacuation import Navigation
from mec.service_client import LocalHTTP, OCCUPANCY_ENDPOINT, OCCUPANCY_SERVICE, register_service
from onem2m.client import strict_json
from simulator.access import parse_batch
from simulator.commands import utc_time
from simulator.presence import parse_scan_batch

RETAINED_INCIDENTS = 32
MAX_BATCHES_PER_INCIDENT = 5000
MAX_REQUEST_BATCHES = 64
MAX_BODY = 1024*1024


def fresh_batch(batch, now=None):
    now = now or datetime.now(timezone.utc)
    age = (now-utc_time(batch['timestamp_utc'])).total_seconds()
    if not -5 <= age < 30:
        raise ValueError('EXPIRED_OR_FUTURE_BATCH')


def parse_unit(raw, navigation):
    """One access batch plus the presence-scan batch covering the same frames."""
    if not isinstance(raw, dict) or set(raw) != {'access', 'presence'}:
        raise ValueError('INVALID_EVIDENCE_UNIT')
    access, presence = parse_batch(raw['access'], navigation), parse_scan_batch(raw['presence'], navigation)
    if (any(access[k] != presence[k] for k in ('incident_id', 'sequence_from', 'sequence_to', 'timestamp_utc'))
            or access['sensing_policy_sha256'] != presence['sensing_policy_sha256']):
        raise ValueError('PRESENCE_SCANS_NOT_ALIGNED')
    return {'access': access, 'presence': presence}


class OccupancyJournal:
    def __init__(self, path, navigation=None, sensing=None):
        self.path = path
        self.lock = Lock()
        self.models = OrderedDict()
        self.navigation = navigation or Navigation()
        self.sensing = sensing
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS incidents (incident TEXT PRIMARY KEY, created INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS batches (incident TEXT, seq_to INTEGER, seq_from INTEGER, '
                       'batch TEXT, result TEXT, PRIMARY KEY(incident,seq_to))')

    def estimator(self):
        return OccupancyEstimator(self.navigation, self.sensing)

    def apply(self, raw):
        unit = parse_unit(raw, self.navigation)
        batch = unit['access']
        incident, last = batch['incident_id'], batch['sequence_to']
        encoded = json.dumps(unit, sort_keys=True, allow_nan=False)
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            old = db.execute('SELECT batch,result FROM batches WHERE incident=? AND seq_to=?', (incident, last)).fetchone()
            if old:
                # Catch-up resubmission of an applied batch returns its stored result.
                if old[0] != encoded:
                    raise BatchOrderError('CONFLICTING_BATCH')
                return strict_json(old[1])
            known = db.execute('SELECT 1 FROM incidents WHERE incident=?', (incident,)).fetchone()
            if incident in self.models:
                model = copy.deepcopy(self.models[incident])
            else:
                model = self.estimator()
                for row in db.execute('SELECT batch FROM batches WHERE incident=? ORDER BY seq_to', (incident,)):
                    stored = strict_json(row[0])
                    model.apply(stored['access'], stored['presence'])
            if db.execute('SELECT COUNT(*) FROM batches WHERE incident=?', (incident,)).fetchone()[0] >= MAX_BATCHES_PER_INCIDENT:
                raise ValueError('INCIDENT_BATCH_LIMIT')
            model.apply(batch, unit['presence'])
            result = model.snapshot()
            if not known:
                order = db.execute('SELECT COALESCE(MAX(created),0)+1 FROM incidents').fetchone()[0]
                db.execute('INSERT INTO incidents VALUES (?,?)', (incident, order))
                stale = [row[0] for row in db.execute(
                    'SELECT incident FROM incidents ORDER BY created DESC LIMIT -1 OFFSET ?', (RETAINED_INCIDENTS,))]
                for name in stale:
                    db.execute('DELETE FROM batches WHERE incident=?', (name,))
                    db.execute('DELETE FROM incidents WHERE incident=?', (name,))
                    self.models.pop(name, None)
            db.execute('INSERT INTO batches VALUES (?,?,?,?,?)', (incident, last, batch['sequence_from'], encoded,
                       json.dumps(result, sort_keys=True, allow_nan=False)))
            self.models[incident] = model
            self.models.move_to_end(incident)
            if len(self.models) > 16:
                self.models.popitem(last=False)
            return result

    def apply_many(self, batches):
        if not isinstance(batches, list) or not 1 <= len(batches) <= MAX_REQUEST_BATCHES:
            raise ValueError('INVALID_BATCH_LIST')
        # Only the newest input must be current; older catch-up input is history.
        fresh_batch(parse_unit(batches[-1], self.navigation)['access'])
        result = None
        for raw in batches:
            result = self.apply(raw)
        return result


def handler(journal, access_key, state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            raw = json.dumps(body, allow_nan=False, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path != '/health':
                return self.reply(404, {'state': 'NOT_FOUND'})
            self.reply(200 if state.get('ready') else 503, {'state': 'READY' if state.get('ready') else 'STARTING',
                'registration': state.get('registration'), 'kind': 'FIREROUTE_OCCUPANCY_SERVICE_NOT_MEC_PLATFORM'})

        def do_POST(self):
            if self.path != '/v1/batches':
                return self.reply(404, {'state': 'NOT_FOUND'})
            supplied = self.headers.get('X-FireRoute-Key', '')
            if not access_key or not supplied.isascii() or not hmac.compare_digest(supplied, access_key):
                return self.reply(403, {'state': 'DENIED'})
            if not state.get('ready'):
                return self.reply(503, {'state': 'UNKNOWN', 'estimate': None})
            self.connection.settimeout(8)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if (not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding')
                        or self.headers.get_content_type() != 'application/json'):
                    raise ValueError('BAD_BODY')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('SHORT_BODY')
                body = strict_json(raw)
                if not isinstance(body, dict) or set(body) != {'batches'}:
                    raise ValueError('BAD_FIELDS')
                estimate = journal.apply_many(body['batches'])
            except (ValueError, KeyError, TypeError, RecursionError):
                return self.reply(422, {'state': 'REJECTED', 'estimate': None})
            except (OSError, sqlite3.Error):
                return self.reply(503, {'state': 'UNKNOWN', 'estimate': None})
            self.reply(200, {'schema_version': 1, 'state': 'ACCEPTED', 'estimate': estimate,
                'provider': 'FIREROUTE_OCCUPANCY_SERVICE',
                'deployment': 'EXTERNAL_COMPOSE_APP_REGISTERED_WITH_OFFICIAL_MEC'})
    return Handler


def main():
    if not re.fullmatch('[0-9a-f]{64}', os.environ.get('FR_RISK_ACCESS_KEY', '')):
        print(json.dumps({'state': 'BLOCKED', 'reason': 'PRIVATE_PROVIDER_ACCESS_CONFIGURATION_REQUIRED'}), flush=True)
        return 2
    directory = Path(os.environ.get('FR_PROVIDER_STATE', '/state'))
    directory.mkdir(parents=True, exist_ok=True)
    ev = Evidence(Path(os.environ.get('EVIDENCE_ROOT', 'evidence')), secret_values=(os.environ.get('FR_RISK_ACCESS_KEY', ''),))
    state = {}
    journal = OccupancyJournal(directory/'occupancy.sqlite3')
    server = ThreadingHTTPServer(('0.0.0.0', 8082), handler(journal, os.environ.get('FR_RISK_ACCESS_KEY', ''), state))
    server.daemon_threads = True
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        target = directory/'registration.json'
        saved = strict_json(target.read_bytes()) if target.exists() else None
        def save(data):
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(data))
            temporary.replace(target)
        controller = LocalHTTP('http://mec-controller', aliases=('mec-controller',), evidence=ev)
        platform = LocalHTTP('http://mec-platform', aliases=('mec-platform',), evidence=ev)
        registration = register_service(controller, platform, OCCUPANCY_SERVICE, OCCUPANCY_ENDPOINT, saved=saved, save=save)
        state.update(ready=True, registration=registration)
        ev.write('registration.json', registration)
        ev.write('meta.json', source_identity(Path.cwd()))
        print(json.dumps({'state': 'OCCUPANCY_SERVICE_READY', 'app_id': registration['app_id'],
            'service_id': registration['service_id'], 'Hosted': 'NOT_CONTACTED', 'evidence': str(ev.path)}), flush=True)
        stop = Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        stop.wait()
    except Exception as exc:
        ev.write('summary.json', {'state': 'FAIL', 'reason': type(exc).__name__, 'Hosted': 'NOT_CONTACTED'})
        print(json.dumps({'state': 'FAIL', 'reason': type(exc).__name__, 'evidence': str(ev.path)}), flush=True)
        return 1
    finally:
        state['ready'] = False
        server.shutdown()
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
