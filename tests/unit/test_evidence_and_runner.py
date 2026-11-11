import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.config import Settings
from backend.evidence import Evidence, redact
from backend.p0 import probe, run, subscription_refs
from onem2m.bootstrap import bootstrap
from onem2m.client import ProtocolError


class EvidenceAndRunnerTests(unittest.TestCase):
    def test_recursive_redaction_including_json_cin_content(self):
        data = {"Authorization": "secret-1", "nested": {"api_token": "secret-2"},
                "con": json.dumps({"password": "secret-3", "event_id": "e"})}
        text = json.dumps(redact(data))
        self.assertNotIn("secret-1", text)
        self.assertNotIn("secret-2", text)
        self.assertNotIn("secret-3", text)
        self.assertIn("event_id", text)

    def test_atomic_summary_and_real_request_log_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Evidence(Path(directory))
            evidence.write("summary.json", {"state": "BLOCKED", "token": "secret"})
            evidence.append("requests.jsonl", {"headers": {"authorization": "secret"}, "rsc": 4103})
            self.assertNotIn("secret", (evidence.path / "summary.json").read_text())
            self.assertNotIn("secret", (evidence.path / "requests.jsonl").read_text())
            self.assertEqual(json.loads((evidence.path / "summary.json").read_text())["state"], "BLOCKED")

    def test_configured_credential_also_redacted_inside_acp_and_debug_text(self):
        data = {"pv": {"acr": [{"acor": ["private-admin-value", "public-device"]}]},
                "m2m:dbg": "Denied private-admin-value", "con": json.dumps({"opaque": "private-admin-value"})}
        text = json.dumps(redact(data, ("private-admin-value",)))
        self.assertNotIn("private-admin-value", text)
        self.assertIn("public-device", text)

    def test_denied_socket_produces_blocked_evidence_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(evidence_root=Path(directory))
            with patch("backend.p0.socket.socket", side_effect=PermissionError("unit environment denial")):
                result, path = run(settings, require_target_python=False)
            self.assertEqual(result["state"], "BLOCKED")
            self.assertEqual(result["pass"], 0)
            self.assertEqual(result["latency_samples"], 0)
            self.assertFalse(json.loads((path / "meta.json").read_text())["real_CSE"])

    def test_probe_requires_actual_csebase_release_and_resource_types(self):
        c = Mock(release="4")
        cb = {"ty": 5, "cst": 1, "csi": "/unit-cse", "ri": "unit-base",
              "srv": ["4"], "srt": [1, 2, 3, 4, 23]}
        c.retrieve.return_value = {"m2m:cb": cb}
        self.assertEqual(probe(c, "base"), cb)
        for broken in ({}, {**cb, "srv": ["5"]}, {**cb, "cst": 9}, {**cb, "srt": [2, 3, 4]}):
            c.retrieve.return_value = {"m2m:cb": broken}
            with self.subTest(keys=list(broken)), self.assertRaises(ProtocolError):
                probe(c, "base")

    def test_subscription_refs_use_actual_returned_identity(self):
        self.assertIn("/id-cse/sub-actual", subscription_refs("/id-cse", "/base/ae/cnt/sub", {"ri": "sub-actual"}))

    def test_bootstrap_uses_distinct_returned_actor_ids_and_owned_names(self):
        client = Mock(release="4", originator="CAdmin")
        counter = iter(range(100))
        def ensure(parent, ty, attrs, **kwargs):
            n = next(counter)
            result = {"ri": f"fixture-{n}", "ty": ty, **attrs}
            if ty == 2:
                result["aei"] = f"C-fixture-actor-{n}"
            return result
        client.ensure.side_effect = ensure
        result = bootstrap(client, "base", "fr_unit", "http://unit.invalid/onem2m/notify", 86400)
        self.assertEqual(len(result["actors"]), 8)
        self.assertEqual(len({x["ae_id"] for x in result["actors"].values()}), 8)
        self.assertIn("sensor/telemetry", result["containers"])
        self.assertTrue(all("fr_unit__" in x["path"] for x in result["actors"].values()))
        policy_call = [c for c in client.ensure.call_args_list if c.args[1] == 1][0]
        allowed = policy_call.args[2]["pv"]["acr"][0]["acor"]
        self.assertEqual(set(allowed), {result["actors"]["sensor"]["ae_id"], result["actors"]["controller"]["ae_id"]})

    def test_duplicate_actor_ids_fail_instead_of_simulating_devices(self):
        client = Mock(release="4")
        client.ensure.return_value = {"aei": "C-same-id", "ri": "unit"}
        with self.assertRaises(ProtocolError):
            bootstrap(client, "base", "fr_unit", "http://unit.invalid/onem2m/notify", 86400)
