"""Ordered synthetic incidents and a durable outbox for actual CSE decisions.

This store is application recovery state. It is never a replacement for a CSE.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from mec.risk.routing import BuildingGraph, synthetic_smoke_blocks
from simulator.events import SensorEvent


class EventConflict(ValueError):
    pass


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class IncidentStore:
    def __init__(self, path: Path, graph: BuildingGraph, source: str, *, sensor_ttl=30.0,
                 max_clock_skew=5.0, smoke_threshold=70.0):
        for value in (sensor_ttl, max_clock_skew):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid incident time budget")
        synthetic_smoke_blocks(graph, graph.origin, 0, smoke_threshold)
        self.path, self.graph, self.source = path, graph, source
        self.sensor_ttl, self.max_clock_skew, self.threshold = sensor_ttl, max_clock_skew, smoke_threshold
        path.parent.mkdir(parents=True, exist_ok=True)
        policy = canonical({"schema_version": 1, "source": source, "origin": graph.origin,
                            "exits": sorted(graph.exits), "graph": graph.adjacency,
                            "sensor_ttl": sensor_ttl, "max_clock_skew": max_clock_skew,
                            "synthetic_smoke_threshold": smoke_threshold})
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS policy (id INTEGER PRIMARY KEY CHECK(id=1), content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS incidents (incident_id TEXT PRIMARY KEY, version INTEGER NOT NULL, blocked TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sensors (
                    incident_id TEXT NOT NULL, source TEXT NOT NULL, sensor_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL, observed_at TEXT NOT NULL, binding TEXT NOT NULL,
                    PRIMARY KEY(incident_id,source,sensor_id));
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, outcome TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, version INTEGER NOT NULL,
                    hazard TEXT NOT NULL, route TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(incident_id,version));
            """)
            row = db.execute("SELECT content FROM policy WHERE id=1").fetchone()
            if row and row[0] != policy:
                raise EventConflict("Incident policy/graph/source changed; explicit migration required")
            db.execute("INSERT OR IGNORE INTO policy VALUES (1,?)", (policy,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def accept(self, value: SensorEvent, *, now: datetime | None = None) -> dict:
        event = SensorEvent.parse(value.to_dict(), self.graph.nodes)
        if event.data_origin != "SYNTHETIC":
            raise ValueError("Initial incident policy accepts synthetic observations only")
        current = datetime.now(timezone.utc) if now is None else now
        if current.utcoffset() is None or current.utcoffset().total_seconds() != 0:
            raise ValueError("Incident clock must be timezone-aware UTC")
        digest = hashlib.sha256(canonical(event.to_dict()).encode()).hexdigest()
        stamp = instant(event.timestamp_utc)
        binding = canonical([event.sensor_type, event.location_node, event.data_origin])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT digest,outcome FROM events WHERE event_id=?", (event.event_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise EventConflict("Event ID reused with different content")
                return {"state": "DUPLICATE" if old[1] == "ACCEPTED" else old[1], "event_id": event.event_id}
            prior = db.execute("SELECT sequence,observed_at,binding FROM sensors WHERE incident_id=? AND source=? AND sensor_id=?",
                               (event.incident_id, event.source, event.sensor_id)).fetchone()
            if prior and binding != prior[2]:
                raise EventConflict("Sensor identity changed its node/type/provenance")
            age = (current - stamp).total_seconds()
            outcome = "ACCEPTED"
            if prior and (event.sequence <= prior[0] or stamp < instant(prior[1])):
                outcome = "IGNORED_OUTDATED"
            elif age > self.sensor_ttl:
                outcome = "IGNORED_STALE"
            elif age < -self.max_clock_skew:
                outcome = "IGNORED_FUTURE"
            db.execute("INSERT INTO events VALUES (?,?,?)", (event.event_id, digest, outcome))
            if outcome != "ACCEPTED":
                return {"state": outcome, "event_id": event.event_id}
            prior_incident = db.execute("SELECT version,blocked FROM incidents WHERE incident_id=?", (event.incident_id,)).fetchone()
            version = prior_incident[0] + 1 if prior_incident else 1
            blocked = set(json.loads(prior_incident[1])) if prior_incident else set()
            if event.sensor_type == "synthetic_smoke_index":
                blocked.update(synthetic_smoke_blocks(self.graph, event.location_node, event.value, self.threshold))
            result = self.graph.route(self.graph.origin, blocked)
            envelope = {"schema_version": 1, "event_id": event.event_id, "incident_id": event.incident_id,
                        "route_version": version, "timestamp_utc": current.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                        "source": self.source, "data_origin": "SYNTHETIC"}
            hazard = {**envelope, "observed_node": event.location_node, "sensor_id": event.sensor_id,
                      "sensor_type": event.sensor_type, "value": event.value, "unit": event.unit,
                      "blocked_nodes": sorted(blocked), "synthetic_smoke_threshold": self.threshold}
            route = {**envelope, "source_node": self.graph.origin, "target_exit": result.target_exit,
                     "path": list(result.path), "blocked_nodes": list(result.blocked_nodes),
                     "status": result.status, "reason": "SYNTHETIC_DEMO_POLICY", "routing_cost": result.cost}
            db.execute("INSERT INTO incidents VALUES (?,?,?) ON CONFLICT(incident_id) DO UPDATE SET version=excluded.version,blocked=excluded.blocked",
                       (event.incident_id, version, canonical(sorted(blocked))))
            db.execute("INSERT INTO sensors VALUES (?,?,?,?,?,?) ON CONFLICT(incident_id,source,sensor_id) DO UPDATE SET sequence=excluded.sequence,observed_at=excluded.observed_at,binding=excluded.binding",
                       (event.incident_id, event.source, event.sensor_id, event.sequence, event.timestamp_utc, binding))
            db.execute("INSERT INTO outbox(event_id,incident_id,version,hazard,route) VALUES(?,?,?,?,?)",
                       (event.event_id, event.incident_id, version, canonical(hazard), canonical(route)))
            return {"state": "ACCEPTED", "event_id": event.event_id, "route": route}

    def pending(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT event_id,hazard,route FROM outbox WHERE delivered=0 ORDER BY rowid").fetchall()
        return [{"event_id": r[0], "hazard": json.loads(r[1]), "route": json.loads(r[2])} for r in rows]

    def delivered(self, event_id: str) -> None:
        with self.connect() as db:
            if db.execute("UPDATE outbox SET delivered=1 WHERE event_id=?", (event_id,)).rowcount != 1:
                raise EventConflict("Unknown outbox event")
