"""Callback processing unit tests; no actual CSE or socket is used."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.notifications import NotificationService, NotificationStore
from backend.evidence import Evidence
from simulator.events import fixture_nodes, synthetic_smoke

ROOT = Path(__file__).resolve().parents[2]


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "notify.sqlite3"
        self.nodes = fixture_nodes(ROOT / "fixtures/building_3f.json")
        self.event = synthetic_smoke(self.nodes, "fr_unit")
        self.store = NotificationStore(self.path)
        self.service = NotificationService(self.store, "/id-unit-cse", "4", self.nodes)
        self.ref = "/id-unit-cse/sub-unit"
        self.service.approve({self.ref})
        self.headers = {"X-M2M-Origin": "/id-unit-cse", "X-M2M-RI": "notify-unit-1",
                        "X-M2M-RVI": "4", "Content-Type": "application/json"}

    def body(self, event=None, ri="cin-unit", ref=None):
        return {"m2m:sgn": {"sur": ref or self.ref, "nev": {"net": 3,
                "rep": {"m2m:cin": {"ty": 4, "ri": ri, "con": json.dumps((event or self.event).to_dict())}}}}}

    def send(self, document, headers=None):
        return self.service.handle(self.headers if headers is None else headers, json.dumps(document).encode())

    def test_subscription_verification_is_not_a_sensor_event(self):
        reply = self.send({"m2m:sgn": {"sur": self.ref, "vrq": True}})
        self.assertEqual((reply.http_status, reply.rsc, reply.request_id), (200, 2000, "notify-unit-1"))
        self.assertEqual(self.store.verified_refs(), {self.ref})
        self.assertEqual(self.store.find(self.event.event_id), [])

    def test_unrelated_verification_ref_rejected(self):
        self.assertEqual(self.send({"m2m:sgn": {"sur": "/other/sub", "vrq": True}}).http_status, 403)

    def test_notification_persisted_before_success_and_survives_restart(self):
        self.assertEqual(self.send(self.body()).kind, "event")
        restarted = NotificationStore(self.path)
        rows = restarted.find(self.event.event_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], self.event.to_dict())
        self.assertEqual(rows[0]["cin_ri"], "cin-unit")

    def test_duplicate_callback_is_idempotent(self):
        self.assertEqual(self.send(self.body()).kind, "event")
        self.assertEqual(self.send(self.body()).kind, "duplicate")
        self.assertEqual(len(self.store.find(self.event.event_id)), 1)

    def test_conflicting_event_content_rejected(self):
        self.send(self.body())
        data = self.body()
        changed = self.event.to_dict()
        changed["value"] = 20
        data["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"] = json.dumps(changed)
        self.assertEqual(self.send(data).http_status, 409)
        self.assertEqual(self.store.find(self.event.event_id)[0]["event"]["value"], 90)

    def test_event_id_cannot_be_reused_for_different_cin(self):
        self.send(self.body())
        self.assertEqual(self.send(self.body(ri="another-cin")).http_status, 409)

    def test_concurrent_duplicates_commit_only_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: self.send(self.body()), range(20)))
        self.assertEqual(sum(r.kind == "event" for r in replies), 1)
        self.assertTrue(all(r.http_status == 200 for r in replies))
        self.assertEqual(len(self.store.find(self.event.event_id)), 1)

    def test_sender_subscription_and_headers_checked(self):
        bad_headers = [{**self.headers, "X-M2M-Origin": "Cattacker"},
                       {k: v for k, v in self.headers.items() if k != "X-M2M-RI"},
                       {**self.headers, "X-M2M-RVI": "5"},
                       {**self.headers, "Content-Type": "text/plain"}]
        for headers in bad_headers:
            with self.subTest(headers=list(headers)):
                self.assertGreaterEqual(self.send(self.body(), headers).http_status, 400)
        self.assertEqual(self.send(self.body(ref="/id-unit-cse/unapproved")).http_status, 403)
        self.assertFalse(self.store.find(self.event.event_id))

    def test_invalid_json_schema_and_oversized_body_rejected(self):
        for body in (b"<html>", b"[]", b"{}", b"x" * 65537):
            with self.subTest(size=len(body)):
                self.assertGreaterEqual(self.service.handle(self.headers, body).http_status, 400)
        document = self.body()
        document["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"] = {"invented": True}
        self.assertEqual(self.send(document).http_status, 400)

    def test_store_failure_never_returns_success(self):
        with patch.object(self.store, "add", side_effect=sqlite3.OperationalError("unit-only failure")):
            reply = self.send(self.body())
        self.assertEqual((reply.http_status, reply.rsc), (500, 5000))

    def test_dictionary_content_is_explicitly_supported(self):
        document = self.body()
        document["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"] = self.event.to_dict()
        self.assertEqual(self.send(document).http_status, 200)

    def test_header_case_is_insensitive(self):
        self.assertEqual(self.send(self.body(), {k.lower(): v for k, v in self.headers.items()}).http_status, 200)

    def test_evidence_records_handler_status_and_verification_kind(self):
        evidence = Evidence(Path(self.temp.name) / "evidence")
        service = NotificationService(self.store, "/id-unit-cse", "4", self.nodes, evidence)
        body = json.dumps({"m2m:sgn": {"sur": self.ref, "vrq": True}}).encode()
        reply = service.handle(self.headers, body)
        record = json.loads((evidence.path / "notifications.jsonl").read_text().splitlines()[-1])
        self.assertEqual(record["handler_http_status"], reply.http_status)
        self.assertEqual(record["handler_rsc"], 2000)
        self.assertEqual(record["processing_kind"], "verification")
        self.assertTrue(record["sender_matches_expected_cse"])
        self.assertNotIn("x-m2m-origin", record["request_headers"])
