"""Independent display process, durable application state and actual ACK writes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import sqlite3
from threading import Thread
from uuid import uuid4

from backend.evidence import Evidence
from backend.notifications import NotificationService, NotificationStore, notification_server
from onem2m.client import CSEClient, CSEError, ProtocolError, TransportError, strict_json
from simulator.commands import DisplayAck, DisplayCommand, utc_time
from simulator.events import utc_now


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)


def ack_name(command_id):
    return 'ack-' + hashlib.sha256(command_id.encode()).hexdigest()


class DisplayState:
    def __init__(self, path, device_id, incident_id, controller_source, source, exits, *, max_skew=5):
        self.path, self.device_id, self.incident_id = Path(path), device_id, incident_id
        self.controller_source, self.source, self.exits, self.max_skew = controller_source, source, exits, max_skew
        self.path.parent.mkdir(parents=True, exist_ok=True)
        identity = encoded([device_id, incident_id, controller_source, source, sorted(exits), max_skew])
        with self.connect() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands (command_id TEXT PRIMARY KEY, digest TEXT NOT NULL, ack TEXT NOT NULL, posted INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS current (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, command_id TEXT NOT NULL, route_exit TEXT, status TEXT NOT NULL, expires TEXT NOT NULL);
            ''')
            old = db.execute('SELECT value FROM identity WHERE id=1').fetchone()
            if old and old[0] != identity:
                raise ValueError('Display identity/policy changed; migration required')
            db.execute('INSERT OR IGNORE INTO identity VALUES (1,?)', (identity,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def apply(self, command, *, now=None):
        command = DisplayCommand.parse(command.to_dict(), self.exits)
        now = datetime.now(timezone.utc) if now is None else now
        if now.utcoffset() is None or now.utcoffset().total_seconds() != 0:
            raise ValueError('Display clock must use UTC')
        digest = hashlib.sha256(encoded(command.to_dict()).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT digest,ack FROM commands WHERE command_id=?', (command.command_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Command ID reused with different payload')
                return DisplayAck.parse(json.loads(old[1]))
            current = db.execute('SELECT version FROM current WHERE id=1').fetchone()
            reason = 'APPLIED'
            if command.incident_id != self.incident_id:
                reason = 'UNKNOWN_INCIDENT'
            elif command.source != self.controller_source:
                reason = 'UNEXPECTED_SOURCE'
            elif utc_time(command.expires_at_utc) <= now:
                reason = 'EXPIRED'
            elif (utc_time(command.timestamp_utc)-now).total_seconds() > self.max_skew:
                reason = 'FUTURE'
            elif current and command.route_version <= current[0]:
                reason = 'OUTDATED'
            if reason == 'APPLIED':
                db.execute('INSERT INTO current VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,command_id=excluded.command_id,route_exit=excluded.route_exit,status=excluded.status,expires=excluded.expires',
                           (command.route_version, command.command_id, command.route_exit, command.guidance_status, command.expires_at_utc))
            ack = DisplayAck(1, 'ack-' + uuid4().hex, command.command_id, self.device_id,
                             command.incident_id, command.event_id, command.route_version,
                             'APPLIED' if reason == 'APPLIED' else 'REJECTED', reason,
                             now.isoformat(timespec='milliseconds').replace('+00:00','Z'), self.source, 'SYNTHETIC')
            db.execute('INSERT INTO commands(command_id,digest,ack) VALUES(?,?,?)', (command.command_id, digest, encoded(ack.to_dict())))
            return ack

    def pending(self):
        with self.connect() as db:
            rows = db.execute('SELECT ack,attempts FROM commands WHERE posted=0 ORDER BY rowid').fetchall()
        return [(DisplayAck.parse(json.loads(r[0])), r[1]) for r in rows]

    def attempt(self, command_id):
        with self.connect() as db:
            db.execute('UPDATE commands SET attempts=attempts+1 WHERE command_id=?', (command_id,))

    def posted(self, command_id):
        with self.connect() as db:
            db.execute('UPDATE commands SET posted=1 WHERE command_id=?', (command_id,))

    def expire(self, *, now=None):
        now = datetime.now(timezone.utc) if now is None else now
        with self.connect() as db:
            row = db.execute('SELECT expires,status FROM current WHERE id=1').fetchone()
            if row and utc_time(row[0]) <= now and row[1] != 'STALE':
                db.execute("UPDATE current SET route_exit=NULL,status='STALE' WHERE id=1")

    @staticmethod
    def snapshot(path):
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT version,command_id,route_exit,status FROM current WHERE id=1').fetchone()
        return dict(zip(['route_version','command_id','route_exit','guidance_status'], row)) if row else None


def device_worker(config, stop, messages):
    """Spawn entrypoint receives only this device's public AE identity, never admin."""
    server = thread = None
    try:
        evidence = Evidence(Path(config['directory']) / 'wire')
        evidence.write('device.json', {'pid': os.getpid(), 'role': config['role'], 'ae_id': config['ae_id'], 'input': 'SYNTHETIC'})
        client = CSEClient(config['cse_url'], config['ae_id'], config['release'], timeout=config['request_timeout'], evidence=evidence, actor=config['role'])
        inbox = NotificationStore(Path(config['directory']) / 'notifications.sqlite3')
        service = NotificationService(inbox, config['cse_id'], config['release'], frozenset(), evidence,
                    decoder=lambda content: DisplayCommand.parse(content, config['exits']), identity_field='command_id')
        server = notification_server(config['bind_host'], config['port'], service)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        sub = client.ensure(config['commands'], 23, {'rn': 'display-sub', 'nu': [config['callback']], 'enc': {'net': [3]}, 'nct': 1})
        refs = {sub['ri'], config['commands'] + '/display-sub', config['cse_id'].rstrip('/') + '/' + sub['ri']}
        if not refs & inbox.verified_refs():
            raise ProtocolError('Display SUB verification missing')
        service.approve(refs)
        actual_sub = client.resource(client.retrieve(config['commands'] + '/display-sub'), 23)
        if actual_sub['ri'] != sub['ri']:
            raise ProtocolError('Display SUB read-back differs')
        state = DisplayState(config['state_path'], config['ae_id'], config['incident_id'], config['controller_source'], config['source'], config['exits'], max_skew=config['max_skew'])
        messages.put({'kind':'ready', 'role':config['role'], 'pid':os.getpid(), 'ae_id':config['ae_id'], 'sub_ri':sub['ri'], 'evidence':str(evidence.path)})
        seen = set()
        while not stop.is_set():
            for row in inbox.records():
                command = DisplayCommand.parse(row['event'], config['exits'])
                if command.command_id not in seen:
                    ack = state.apply(command)
                    evidence.event(hop='device_applied', **ack.to_dict())
                    seen.add(command.command_id)
            for ack, attempts in state.pending():
                if attempts >= config['retry_limit'] + 1:
                    raise ProtocolError('Display ACK retry budget exhausted')
                state.attempt(ack.command_id)
                try:
                    attrs = {'rn': ack_name(ack.command_id), 'cnf':'application/json:0', 'con':encoded(ack.to_dict())}
                    created = client.ensure(config['acks'], 4, attrs)
                    read = client.resource(client.retrieve(config['acks'] + '/' + attrs['rn']), 4)
                    if read['ri'] != created['ri'] or strict_json(read['con']) != ack.to_dict():
                        raise ProtocolError('Device ACK CIN read-back differs')
                    state.posted(ack.command_id)
                    evidence.event(hop='device_ACK_CIN', ack_id=ack.ack_id, command_id=ack.command_id, cin_ri=read['ri'])
                except TransportError:
                    evidence.event(hop='ACK_transport_interrupted', command_id=ack.command_id, attempt=attempts+1)
                    stop.wait(0.25)
            state.expire()
            stop.wait(0.05)
    except Exception as exc:
        messages.put({'kind':'error', 'role':config['role'], 'error':type(exc).__name__})
    finally:
        if server and thread and thread.is_alive():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
