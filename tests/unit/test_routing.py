"""Actual algorithm tests T01-T03; no CSE or MEC integration claim."""
import copy
import json
from pathlib import Path
import unittest

from mec.risk.routing import BuildingGraph, RoutingError, synthetic_smoke_blocks

ROOT = Path(__file__).resolve().parents[2]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "fixtures/building_3f.json").read_text())
        self.graph = BuildingGraph(self.document)

    def assert_real_edges(self, result):
        for source, target in zip(result.path, result.path[1:]):
            self.assertIn(target, dict(self.graph.adjacency[source]))
        self.assertFalse(set(result.path) & set(result.blocked_nodes))

    def test_t01_baseline_computes_exit_a(self):
        result = self.graph.route("F3_ROOM1")
        self.assertEqual(result.target_exit, "EXIT_A")
        self.assertEqual(result.cost, 13)
        self.assertEqual(result.status, "ROUTE_AVAILABLE")
        self.assert_real_edges(result)

    def test_t02_smoke_blocks_a_and_computes_b(self):
        blocked = synthetic_smoke_blocks(self.graph, "F2_A", 90)
        result = self.graph.route("F3_ROOM1", blocked)
        self.assertEqual(blocked, {"F2_A"})
        self.assertEqual(result.target_exit, "EXIT_B")
        self.assertEqual(result.cost, 16)
        self.assertNotIn("F2_A", result.path)
        self.assert_real_edges(result)

    def test_t03_no_route_has_no_fabricated_exit_or_path(self):
        result = self.graph.route("F3_ROOM1", {"F2_A", "F2_B"})
        self.assertEqual(result.status, "NO_VERIFIED_ROUTE")
        self.assertIsNone(result.target_exit)
        self.assertEqual(result.path, ())
        self.assertIsNone(result.cost)

    def test_cost_changes_change_computed_exit(self):
        # Proves the result is computed, not a hard-coded baseline answer.
        changed = copy.deepcopy(self.document)
        for edge in changed["edges"]:
            if edge["from"] == "F3_C" and edge["to"] == "F3_A":
                edge["weight"] = 100
        result = BuildingGraph(changed).route("F3_ROOM1")
        self.assertEqual(result.target_exit, "EXIT_B")

    def test_blocked_source_and_all_exits_are_no_route(self):
        for blocked in ({"F3_ROOM1"}, {"EXIT_A", "EXIT_B"}):
            with self.subTest(blocked=blocked):
                self.assertEqual(self.graph.route("F3_ROOM1", blocked).status, "NO_VERIFIED_ROUTE")

    def test_source_at_exit_has_zero_cost(self):
        result = self.graph.route("EXIT_A")
        self.assertEqual(result.path, ("EXIT_A",))
        self.assertEqual(result.cost, 0)

    def test_unknown_route_inputs_are_errors(self):
        for source, blocked in (("unknown", set()), ("F3_ROOM1", {"unknown"})):
            with self.subTest(source=source), self.assertRaises(RoutingError):
                self.graph.route(source, blocked)

    def test_invalid_graphs_are_rejected(self):
        for weight in (-1, 0, True, float("nan"), float("inf")):
            graph = copy.deepcopy(self.document)
            graph["edges"][0]["weight"] = weight
            with self.subTest(weight=str(weight)), self.assertRaises(RoutingError):
                BuildingGraph(graph)
        graph = copy.deepcopy(self.document)
        graph["nodes"].append(graph["nodes"][0])
        with self.assertRaises(RoutingError):
            BuildingGraph(graph)

    def test_policy_threshold_and_invalid_smoke_input(self):
        self.assertEqual(synthetic_smoke_blocks(self.graph, "F2_A", 70), {"F2_A"})
        self.assertEqual(synthetic_smoke_blocks(self.graph, "F2_A", 69), set())
        for value in (True, -1, 101, float("nan")):
            with self.subTest(value=str(value)), self.assertRaises(RoutingError):
                synthetic_smoke_blocks(self.graph, "F2_A", value)

    def test_low_reading_does_not_clear_existing_block(self):
        active = synthetic_smoke_blocks(self.graph, "F2_A", 90)
        active |= synthetic_smoke_blocks(self.graph, "F2_A", 20)
        self.assertEqual(self.graph.route("F3_ROOM1", active).target_exit, "EXIT_B")
