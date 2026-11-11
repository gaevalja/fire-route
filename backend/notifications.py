"""Durable SUB receiver; this is an AE endpoint, never a CSE."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from threading import Lock

from onem2m.client import strict_json
from simulator.events import ContractError, SensorEvent, utc_now

MAX_NOTIFICATION_BYTES = 65536


class NotificationConflict(ValueError):
    pass


class NotificationStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS verifications (
                    ref TEXT PRIMARY KEY, request_id TEXT NOT NULL, received_at_utc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY, subscription_ref TEXT NOT NULL,
                    event_id TEXT NOT NULL, cin_ri TEXT NOT NULL, payload TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, request_id TEXT NOT NULL, received_at_utc TEXT NOT NULL,
                    UNIQUE(subscription_ref,event_id), UNIQUE(subscription_ref,cin_ri));
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def verification(self, ref: str, request_id: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO verifications VALUES (?,?,?)", (ref, request_id, utc_now()))

    def verified_refs(self) -> set[str]:
        with self.connect() as db:
            return {row[0] for row in db.execute("SELECT ref FROM verifications")}

    def add(self, ref: str, cin_ri: str, event, request_id: str, *, message_id: str | None = None) -> bool:
        key = event.event_id if message_id is None else message_id
        payload = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.connect() as db:
            # Serialize compare/insert across notification worker threads.
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT event_id,cin_ri,payload_sha256 FROM notifications WHERE subscription_ref=? AND (event_id=? OR cin_ri=?)", (ref, key, cin_ri)).fetchone()
            if old:
                if old != (key, cin_ri, digest):
                    raise NotificationConflict("Notification ID reused with different content")
                return False
            db.execute("INSERT INTO notifications(subscription_ref,event_id,cin_ri,payload,payload_sha256,request_id,received_at_utc) VALUES(?,?,?,?,?,?,?)", (ref, key, cin_ri, payload, digest, request_id, utc_now()))
        return True

    def find(self, event_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT subscription_ref,cin_ri,payload,request_id,received_at_utc FROM notifications WHERE event_id=?", (event_id,)).fetchall()
        return [{"subscription_ref": r[0], "cin_ri": r[1], "event": strict_json(r[2]), "request_id": r[3], "received_at_utc": r[4]} for r in rows]

    def records(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT subscription_ref,cin_ri,payload,request_id,received_at_utc FROM notifications ORDER BY id").fetchall()
        return [{"subscription_ref": r[0], "cin_ri": r[1], "event": strict_json(r[2]), "request_id": r[3], "received_at_utc": r[4]} for r in rows]


@dataclass(frozen=True)
class NotificationReply:
    http_status: int
    rsc: int
    request_id: str
    kind: str


class NotificationService:
    def __init__(self, store: NotificationStore, cse_id: str, release: str, nodes: frozenset[str], evidence=None,
                 *, decoder=None, identity_field="event_id"):
        self.store, self.cse_id, self.release, self.nodes, self.evidence = store, cse_id, release, nodes, evidence
        self.allowed_refs: set[str] = set()
        self.lock = Lock()
        self.decoder = decoder or (lambda content: SensorEvent.parse(content, self.nodes))
        self.identity_field = identity_field
        self.decoders = {}

    def approve(self, refs: set[str], *, decoder=None, identity_field=None) -> None:
        with self.lock:
            self.allowed_refs.update(refs)
            for ref in refs:
                self.decoders[ref] = (decoder or self.decoder, identity_field or self.identity_field)

    def handle(self, headers: dict, body: bytes) -> NotificationReply:
        reply = self._handle(headers, body)
        if self.evidence:
            normalized = {k.lower(): str(v) for k, v in headers.items()}
            sender = normalized.get("x-m2m-origin", "")
            self.evidence.append("notifications.jsonl", {
                "request_id": reply.request_id,
                "request_headers": {k: v for k, v in normalized.items()
                                    if k in {"x-m2m-ri", "x-m2m-rvi", "content-type"}},
                "sender_matches_expected_cse": sender == self.cse_id,
                "sender_sha256": hashlib.sha256(sender.encode()).hexdigest(),
                "body": self._safe_body(body), "processing_kind": reply.kind,
                "handler_http_status": reply.http_status, "handler_rsc": reply.rsc,
            })
        return reply

    def _handle(self, headers: dict, body: bytes) -> NotificationReply:
        h = {k.lower(): str(v) for k, v in headers.items()}
        request_id = h.get("x-m2m-ri", "")
        kind = "rejected"
        if not request_id or len(request_id) > 256 or any(c in request_id for c in "\r\n"):
            return NotificationReply(400, 4000, "", "invalid_request_id")
        if h.get("x-m2m-origin") != self.cse_id:
            return NotificationReply(403, 4103, request_id, "unrecognized_sender")
        if h.get("x-m2m-rvi") not in {None, self.release}:
            return NotificationReply(400, 4000, request_id, "release_mismatch")
        media = h.get("content-type", "").split(";", 1)[0].lower()
        if media not in {"application/json", "application/vnd.onem2m-ntfy+json", "application/vnd.onem2m-res+json"}:
            return NotificationReply(415, 4000, request_id, "unsupported_content_type")
        if len(body) > MAX_NOTIFICATION_BYTES:
            return NotificationReply(413, 4000, request_id, "body_too_large")
        try:
            document = strict_json(body)
            signal = document["m2m:sgn"]
            ref = signal["sur"]
            if not isinstance(ref, str) or not ref or len(ref) > 2048:
                raise ValueError("invalid subscription ref")
            if signal.get("vrq") is True:
                if not ref.startswith(self.cse_id.rstrip("/") + "/"):
                    return NotificationReply(403, 4103, request_id, "unrecognized_verification_ref")
                self.store.verification(ref, request_id)
                kind = "verification"
                return NotificationReply(200, 2000, request_id, kind)
            with self.lock:
                permitted = ref in self.allowed_refs
                decoder, identity_field = self.decoders.get(ref, (self.decoder, self.identity_field))
            if not permitted:
                return NotificationReply(403, 4103, request_id, "unknown_subscription")
            if type(signal["nev"]["net"]) is not int or signal["nev"]["net"] != 3:
                raise ValueError("only child-creation notifications accepted")
            cin = signal["nev"]["rep"]["m2m:cin"]
            if type(cin.get("ty")) is not int or cin.get("ty") != 4 or not isinstance(cin.get("ri"), str) or not cin["ri"]:
                raise ValueError("invalid CIN")
            content = strict_json(cin["con"]) if isinstance(cin["con"], str) else cin["con"]
            event = decoder(content)
            if identity_field == "event_id":
                inserted = self.store.add(ref, cin["ri"], event, request_id)
            else:
                inserted = self.store.add(ref, cin["ri"], event, request_id, message_id=getattr(event, identity_field))
            kind = "event" if inserted else "duplicate"
            if self.evidence:
                self.evidence.event(hop="subscription_received", kind=kind, event_id=event.event_id, cin_ri=cin["ri"], subscription_ref=ref)
            return NotificationReply(200, 2000, request_id, kind)
        except NotificationConflict:
            return NotificationReply(409, 4105, request_id, "conflicting_duplicate")
        except (ValueError, TypeError, KeyError, UnicodeDecodeError, AttributeError, ContractError):
            return NotificationReply(400, 4000, request_id, "invalid_notification")
        except sqlite3.Error:
            return NotificationReply(500, 5000, request_id, "persistence_failed")

    @staticmethod
    def _safe_body(body):
        if len(body) > MAX_NOTIFICATION_BYTES:
            return "[OVERSIZED BODY OMITTED]"
        try:
            return strict_json(body)
        except (ValueError, UnicodeDecodeError):
            return "[INVALID JSON OMITTED]"


def notification_server(host: str, port: int, service: NotificationService) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.0 closes connections and avoids unsupported pipelining/chunked bodies.
        def log_message(self, *args):
            pass

        def reply(self, status: int, rsc: int, rqi: str = ""):
            self.send_response(status)
            self.send_header("X-M2M-RSC", str(rsc))
            self.send_header("X-M2M-RVI", service.release)
            if rqi:
                self.send_header("X-M2M-RI", rqi)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            if self.path != "/onem2m/notify":
                return self.reply(404, 4004)
            if self.headers.get("Transfer-Encoding"):
                return self.reply(400, 4000)
            try:
                length = int(self.headers["Content-Length"])
            except (TypeError, ValueError):
                return self.reply(411, 4000)
            if not 0 <= length <= MAX_NOTIFICATION_BYTES:
                return self.reply(413, 4000)
            self.connection.settimeout(5)
            try:
                body = self.rfile.read(length)
            except (OSError, TimeoutError):
                return self.reply(408, 4000)
            if len(body) != length:
                return self.reply(400, 4000)
            result = service.handle(dict(self.headers), body)
            self.reply(result.http_status, result.rsc, result.request_id)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
