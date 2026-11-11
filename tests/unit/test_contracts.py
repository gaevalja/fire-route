import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from backend.config import ConfigurationError, Settings, read_dotenv
from simulator.events import ContractError, SensorEvent, fixture_nodes, synthetic_smoke

ROOT = Path(__file__).resolve().parents[2]


class SensorContractTests(unittest.TestCase):
    def setUp(self):
        self.nodes = fixture_nodes(ROOT / "fixtures/building_3f.json")
        self.event = synthetic_smoke(self.nodes, "fr_test")

    def test_generated_event_is_valid_and_unique(self):
        other = synthetic_smoke(self.nodes, "fr_test")
        self.assertNotEqual(self.event.event_id, other.event_id)
        self.assertEqual(SensorEvent.parse(self.event.to_dict(), self.nodes), self.event)
        self.assertEqual(self.event.data_origin, "SYNTHETIC")

    def test_temperature_retains_physical_unit_without_smoke_policy(self):
        d = self.event.to_dict()
        d.update(sensor_type="temperature_celsius", unit="degC", value=32.5, data_origin="PHYSICAL")
        self.assertEqual(SensorEvent.parse(d, self.nodes).value, 32.5)

    def test_invalid_schema_and_boundary_inputs(self):
        cases = [("schema_version", True), ("schema_version", 2), ("sequence", True), ("sequence", -1),
                 ("value", True), ("value", float("nan")), ("value", float("inf")), ("value", 101),
                 ("value", -1), ("unit", "ppm"), ("location_node", "REAL_PERSON_POSITION"),
                 ("data_origin", "PHYSICAL"), ("timestamp_utc", "2026-11-11T01:00:00"),
                 ("timestamp_utc", "2026-11-11T01:00:00+09:00"), ("event_id", ""),
                 ("timestamp_utc", "2026-11-11 01:00:00+00:00"),
                 ("source", "bad\r\nsource"), ("sensor_type", "unverified_fire_detector")]
        for field, value in cases:
            with self.subTest(field=field, value=str(value)):
                d = self.event.to_dict()
                d[field] = value
                with self.assertRaises(ContractError):
                    SensorEvent.parse(d, self.nodes)

    def test_missing_and_extra_fields_rejected(self):
        d = self.event.to_dict()
        del d["event_id"]
        with self.assertRaises(ContractError):
            SensorEvent.parse(d, self.nodes)
        d = self.event.to_dict()
        d["certified_safe"] = True
        with self.assertRaises(ContractError):
            SensorEvent.parse(d, self.nodes)

    def test_smoke_zero_and_hundred_are_valid(self):
        for value in (0, 100):
            d = self.event.to_dict()
            d["value"] = value
            self.assertEqual(SensorEvent.parse(d, self.nodes).value, value)

    def test_fixture_has_valid_nodes_and_rejects_bad_edges(self):
        self.assertEqual(len(self.nodes), 10)
        data = json.loads((ROOT / "fixtures/building_3f.json").read_text())
        for value in (0, -1, True, float("nan")):
            with self.subTest(weight=str(value)), tempfile.TemporaryDirectory() as directory:
                graph = copy.deepcopy(data)
                graph["edges"][0]["weight"] = value
                path = Path(directory) / "graph.json"
                path.write_text(json.dumps(graph))
                with self.assertRaises(ContractError):
                    fixture_nodes(path)


class ConfigurationTests(unittest.TestCase):
    def test_safe_local_defaults(self):
        s = Settings.load({}, Path("/nonexistent-fire-route-test-env"))
        self.assertEqual(s.release, "4")
        self.assertEqual(s.cse_mode, "real")
        self.assertNotIn("admin_originator", s.public())

    def test_environment_overrides_dotenv_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('# comment\nCSE_BASE_RESOURCE="test-base"\nUNUSED=$(touch should-not-exist)\n')
            self.assertEqual(read_dotenv(path)["UNUSED"], "$(touch should-not-exist)")
            self.assertEqual(Settings.load({"CSE_BASE_RESOURCE": "override"}, path).cse_base, "override")
            self.assertFalse((Path(directory) / "should-not-exist").exists())

    def test_invalid_configurations(self):
        cases = [{"cse_url": "https://user:secret@example.org"}, {"cse_url": "file:///etc/passwd"},
                 {"cse_url": "https://example.org?token=secret"}, {"cse_base": "../other"},
                 {"release": "VERIFY_INSTALLED_RELEASE"}, {"admin_originator": "bad\r\nHeader"},
                 {"cse_mode": "mock"}, {"mec_mode": "real"}, {"demo_mode": "physical"},
                 {"request_timeout": float("nan")}, {"ack_timeout": 0}, {"retry_limit": 6},
                 {"bind_port": 65536}, {"retention_seconds": 1},
                 {"notification_url": "http://example.org/wrong"}]
        for kwargs in cases:
            with self.subTest(fields=list(kwargs)), self.assertRaises(ConfigurationError):
                Settings(**kwargs)

    def test_invalid_dotenv_and_numeric_value_have_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("BROKEN_SECRET_LINE")
            with self.assertRaises(ConfigurationError) as error:
                read_dotenv(path)
            self.assertNotIn("BROKEN_SECRET_LINE", str(error.exception))
        with self.assertRaises(ConfigurationError) as error:
            Settings.load({"RETRY_LIMIT": "secret-value"}, Path("/missing"))
        self.assertNotIn("secret-value", str(error.exception))
