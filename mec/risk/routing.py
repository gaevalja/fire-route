"""Computed routes on a synthetic graph; no real evacuation safety guarantee."""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import json
import math
from pathlib import Path


class RoutingError(ValueError):
    pass


@dataclass(frozen=True)
class RouteResult:
    status: str
    target_exit: str | None
    path: tuple[str, ...]
    cost: float | None
    blocked_nodes: tuple[str, ...]


class BuildingGraph:
    def __init__(self, document: dict):
        try:
            ids = [node["id"] for node in document["nodes"]]
            if (not ids or any(not isinstance(n, str) or not n for n in ids)
                    or len(ids) != len(set(ids))):
                raise RoutingError("Node IDs must be unique nonempty strings")
            self.nodes = frozenset(ids)
            exits = document["exits"]
            if not isinstance(exits, list) or not exits or not set(exits) <= self.nodes:
                raise RoutingError("Exits must reference known graph nodes")
            self.exits = frozenset(exits)
            self.origin = document["origin_node"]
            if self.origin not in self.nodes:
                raise RoutingError("Unknown graph origin")
            neighbors: dict[str, dict[str, float]] = {n: {} for n in ids}
            for edge in document["edges"]:
                source, target, weight = edge["from"], edge["to"], edge["weight"]
                if source not in self.nodes or target not in self.nodes:
                    raise RoutingError("Edge references an unknown node")
                if (isinstance(weight, bool) or not isinstance(weight, (int, float))
                        or not math.isfinite(weight) or weight <= 0):
                    raise RoutingError("Edge weights must be finite positive routing costs")
                if type(edge["bidirectional"]) is not bool:
                    raise RoutingError("Edge direction flag must be boolean")
                neighbors[source][target] = min(float(weight), neighbors[source].get(target, math.inf))
                if edge["bidirectional"]:
                    neighbors[target][source] = min(float(weight), neighbors[target].get(source, math.inf))
            self.adjacency = {node: tuple(sorted(edges.items())) for node, edges in neighbors.items()}
        except (KeyError, TypeError) as exc:
            raise RoutingError("Malformed building graph") from exc

    @classmethod
    def load(cls, path: Path) -> "BuildingGraph":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def route(self, source: str, blocked_nodes=frozenset()) -> RouteResult:
        blocked = frozenset(blocked_nodes)
        if source not in self.nodes or not blocked <= self.nodes:
            raise RoutingError("Route inputs reference unknown graph nodes")
        normalized = tuple(sorted(blocked))
        queue = [(0.0, (source,), source)]
        visited: set[str] = set()
        while queue:
            cost, path, node = heapq.heappop(queue)
            if node in visited or node in blocked:
                continue
            visited.add(node)
            if node in self.exits:
                return RouteResult("ROUTE_AVAILABLE", node, path, cost, normalized)
            for neighbor, weight in self.adjacency[node]:
                if neighbor not in blocked and neighbor not in visited:
                    heapq.heappush(queue, (cost + weight, path + (neighbor,), neighbor))
        return RouteResult("NO_VERIFIED_ROUTE", None, (), None, normalized)


def synthetic_smoke_blocks(graph: BuildingGraph, location: str, value: float, threshold: float = 70) -> frozenset[str]:
    """New blocking observations only; a low value never clears existing hazards."""
    if location not in graph.nodes:
        raise RoutingError("Unknown synthetic smoke location")
    for number in (value, threshold):
        if (isinstance(number, bool) or not isinstance(number, (int, float))
                or not math.isfinite(number) or not 0 <= number <= 100):
            raise RoutingError("Synthetic smoke index/threshold must be in 0..100")
    return frozenset({location}) if value >= threshold else frozenset()
