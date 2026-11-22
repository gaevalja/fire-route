"""Python counterpart of config.js + engine.js for headless evacuation training.

The source scenario advances its fire/smoke state once per minute, using the
previous minute for every zone.  Values between minute boundaries are a linear
interpolation shown one second at a time.  This module keeps the same rule but
can jump straight to a requested second, which avoids rebuilding all 162 zone
records for every intervening second during training.

Only ``zones`` and ``snapshot()`` are observations.  The private next-minute
state must never be passed to the evacuee policy.
"""

from __future__ import annotations

from pathlib import Path
import json
import math
import subprocess
from typing import Any


FLOORS = 10
ROOF_FLOOR = 11
ROOMS_ON_FIRST_FLOOR = 4
ROOMS_ON_UPPER_FLOOR = 9
CORRIDOR_SEGMENTS = 5
WIND_OPTIONS = (1, 5, 10, 15)
DEFAULT_WIND = 5
SECONDS_PER_MINUTE = 60
ZONE_SIZE = {
    "room": 1,
    "corridor": 1,
    "stair": 2,
    "elevator": 1,
    "lobby": 5,
    "roof": 5,
}
INITIAL_FIRE = 18.0
MAX_LEVEL = 100.0
SMOKE_ABOVE_FIRE_CAP = 30.0
ROOF_SMOKE_CAP = 30.0
FIRE_GROWTH_PER_MINUTE = 6.5
FIRE_GROWTH_ACCELERATION_FULL_AT = 70.0
FIRE_GROWTH_MAX_MULTIPLIER = 2.0
FIRE_SPREAD_PER_MINUTE = 0.16
ROOM_FIRE_RESISTANCE_FACTOR = 0.193
SMOKE_GENERATION_PER_FIRE = 0.8
SMOKE_SPREAD_PER_MINUTE = 0.8
SMOKE_DIRECT_FIRE_TRANSFER = 0.7
WIND_MULTIPLIER = {1: 0.75, 5: 1.0, 10: 1.3, 15: 1.6}
COLLAPSE_FIRE_THRESHOLD = 55.0
COLLAPSE_MAX_PROBABILITY = 0.001
MAX_COLLAPSED_ZONES = 2

_templates: list[dict[str, Any]] = []
_fire_edges: dict[str, set[str]] = {}
_smoke_in: dict[str, set[str]] = {}


def _add_zone(zone_id: str, zone_type: str, floor: int, label: str) -> None:
    _templates.append(
        {
            "id": zone_id,
            "type": zone_type,
            "floor": floor,
            "label": label,
            "size": ZONE_SIZE[zone_type],
        }
    )
    _fire_edges[zone_id] = set()
    if zone_type != "corridor":
        _smoke_in[zone_id] = set()


def _fire_link(a: str, b: str) -> None:
    _fire_edges[a].add(b)
    _fire_edges[b].add(a)


def _smoke_link(a: str, b: str) -> None:
    _smoke_in[a].add(b)
    _smoke_in[b].add(a)


def _smoke_one_way(source: str, destination: str) -> None:
    _smoke_in[destination].add(source)


def _build_topology() -> None:
    for floor in range(1, FLOORS + 1):
        room_count = ROOMS_ON_FIRST_FLOOR if floor == 1 else ROOMS_ON_UPPER_FLOOR
        for room in range(1, room_count + 1):
            _add_zone(f"F{floor}-R{room}", "room", floor, f"방 {room}")
        if floor == 1:
            _add_zone("F1-L", "lobby", floor, "로비")
        else:
            for segment in range(1, CORRIDOR_SEGMENTS + 1):
                _add_zone(f"F{floor}-C{segment}", "corridor", floor, f"복도 {segment}")
            _smoke_in[f"F{floor}-C"] = set()
        _add_zone(f"F{floor}-SA", "stair", floor, "비상계단 A")
        _add_zone(f"F{floor}-SB", "stair", floor, "비상계단 B")
        _add_zone(f"F{floor}-E", "elevator", floor, "엘리베이터")
    _add_zone("F11-ROOF", "roof", ROOF_FLOOR, "옥상")

    for zone_id in ("F1-R1", "F1-R2", "F1-R3", "F1-R4", "F1-SA", "F1-SB", "F1-E"):
        _fire_link("F1-L", zone_id)
        _smoke_link("F1-L", zone_id)

    for floor in range(2, FLOORS + 1):
        smoke_corridor = f"F{floor}-C"
        for segment in range(1, CORRIDOR_SEGMENTS + 1):
            corridor = f"F{floor}-C{segment}"
            top_room = f"F{floor}-R{segment}"
            _fire_link(corridor, top_room)
            _smoke_link(smoke_corridor, top_room)
            if segment < CORRIDOR_SEGMENTS:
                _fire_link(corridor, f"F{floor}-C{segment + 1}")
        for segment, suffix in enumerate(("R6", "R7", "E", "R8", "R9"), start=1):
            zone_id = f"F{floor}-{suffix}"
            _fire_link(f"F{floor}-C{segment}", zone_id)
            _smoke_link(smoke_corridor, zone_id)
        _fire_link(f"F{floor}-C1", f"F{floor}-SA")
        _fire_link(f"F{floor}-C5", f"F{floor}-SB")
        _smoke_link(smoke_corridor, f"F{floor}-SA")
        _smoke_link(smoke_corridor, f"F{floor}-SB")

    for floor in range(1, FLOORS):
        for side in ("A", "B"):
            lower = f"F{floor}-S{side}"
            upper = f"F{floor + 1}-S{side}"
            _fire_link(lower, upper)
            _smoke_one_way(lower, upper)
    for side in ("A", "B"):
        _fire_link(f"F10-S{side}", "F11-ROOF")
        _smoke_one_way(f"F10-S{side}", "F11-ROOF")


_build_topology()
ZONE_IDS = tuple(zone["id"] for zone in _templates)
ROOM_IDS = tuple(zone["id"] for zone in _templates if zone["type"] == "room")
ZONE_TYPES = {zone["id"]: zone["type"] for zone in _templates}
MOVE_NEIGHBORS = {
    zone_id: tuple(neighbor for neighbor in ZONE_IDS if neighbor in neighbors)
    for zone_id, neighbors in _fire_edges.items()
}


def _normalize_seed(seed: int | str) -> int:
    """Mirror the JavaScript uint32 seed conversion for the supported inputs."""
    try:
        number = float(seed)
    except (TypeError, ValueError):
        number = float("nan")
    if number != number or number in (float("inf"), float("-inf")):
        value = 2166136261
        for char in str(seed):
            value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
        return value or 1
    return (int(number) & 0xFFFFFFFF) or 1


def _next_random(state: int) -> tuple[int, float]:
    state = (1664525 * state + 1013904223) & 0xFFFFFFFF
    return state, state / 4294967296.0


def collapse_probability(fire: float) -> float:
    if fire < COLLAPSE_FIRE_THRESHOLD:
        return 0.0
    exposure = (fire - COLLAPSE_FIRE_THRESHOLD) / (MAX_LEVEL - COLLAPSE_FIRE_THRESHOLD)
    return COLLAPSE_MAX_PROBABILITY * exposure * exposure


def _clamp(value: float) -> float:
    return min(MAX_LEVEL, max(0.0, value))


def fire_growth_multiplier(fire: float) -> float:
    """Accelerate a burning zone's own growth, capped once fire reaches 70."""
    progress = min(max(fire, 0.0), FIRE_GROWTH_ACCELERATION_FULL_AT) / FIRE_GROWTH_ACCELERATION_FULL_AT
    return 1.0 + progress * (FIRE_GROWTH_MAX_MULTIPLIER - 1.0)


class FireSimulator:
    """Scenario state with the same visible values and random draws as engine.js."""

    def __init__(self, seed: int | str, wind: int = DEFAULT_WIND,
                 ignition_id: str | None = None):
        if wind not in WIND_OPTIONS:
            raise ValueError(f"wind must be one of {WIND_OPTIONS}")
        self.seed = _normalize_seed(seed)
        self.wind = wind
        self.second = 0
        self.minute = 0
        self.ended = False
        self.rng_state, draw = _next_random(self.seed)
        selected_ignition = (ROOM_IDS[int(draw * len(ROOM_IDS))]
                             if ignition_id is None or ignition_id == "" else str(ignition_id))
        if selected_ignition not in ROOM_IDS:
            raise ValueError(f"Ignition must start in a room: {selected_ignition}")
        self.ignition_id = selected_ignition
        self.zones: dict[str, dict[str, Any]] = {
            template["id"]: {**template, "fire": 0.0, "smoke": 0.0, "collapsed": False}
            for template in _templates
        }
        self.zones[self.ignition_id]["fire"] = INITIAL_FIRE
        self._minute_anchor: dict[str, dict[str, Any]] | None = None
        self._minute_target: tuple[dict[str, dict[str, Any]], int, bool] | None = None

    @staticmethod
    def _current_smoke(zones: dict[str, dict[str, Any]], smoke_id: str) -> float:
        if smoke_id.endswith("-C"):
            return zones[f"{smoke_id}1"]["smoke"]
        return zones[smoke_id]["smoke"]

    @staticmethod
    def _current_fire_for_smoke(zones: dict[str, dict[str, Any]], smoke_id: str) -> float:
        if not smoke_id.endswith("-C"):
            return zones[smoke_id]["fire"]
        return sum(zones[f"{smoke_id}{segment}"]["fire"] for segment in range(1, CORRIDOR_SEGMENTS + 1)) / CORRIDOR_SEGMENTS

    def _calculate_next_minute(self) -> tuple[dict[str, dict[str, Any]], int, bool]:
        old = self.zones
        wind_factor = WIND_MULTIPLIER[self.wind]
        next_zones: dict[str, dict[str, Any]] = {}
        for template in _templates:
            zone_id = template["id"]
            zone = old[zone_id]
            max_neighbor_fire = max((old[other]["fire"] for other in _fire_edges[zone_id]), default=0.0)
            resistance = ROOM_FIRE_RESISTANCE_FACTOR if zone["type"] == "room" and zone_id != self.ignition_id else 1.0
            growth = (FIRE_GROWTH_PER_MINUTE * fire_growth_multiplier(zone["fire"])
                      * resistance / zone["size"] if zone["fire"] > 0 else 0.0)
            incoming = max_neighbor_fire * FIRE_SPREAD_PER_MINUTE * wind_factor * resistance / zone["size"]
            next_zones[zone_id] = {**zone, "fire": _clamp(zone["fire"] + growth + incoming)}

        for smoke_id, incoming_ids in _smoke_in.items():
            old_smoke = self._current_smoke(old, smoke_id)
            max_neighbor_smoke = max((self._current_smoke(old, other) for other in incoming_ids), default=0.0)
            max_neighbor_fire = max((self._current_fire_for_smoke(old, other) for other in incoming_ids), default=0.0)
            size = ZONE_SIZE["corridor"] * CORRIDOR_SEGMENTS if smoke_id.endswith("-C") else old[smoke_id]["size"]
            generated = self._current_fire_for_smoke(old, smoke_id) * SMOKE_GENERATION_PER_FIRE / size
            transported = max(0.0, max_neighbor_smoke - old_smoke) * SMOKE_SPREAD_PER_MINUTE * wind_factor
            from_neighbor_fire = max_neighbor_fire * SMOKE_DIRECT_FIRE_TRANSFER * wind_factor
            fire_cap = self._current_fire_for_smoke(next_zones, smoke_id) + SMOKE_ABOVE_FIRE_CAP
            smoke = min(_clamp(old_smoke + generated + max(transported, from_neighbor_fire)), fire_cap)
            if smoke_id == "F11-ROOF":
                smoke = min(smoke, ROOF_SMOKE_CAP)
            if smoke_id.endswith("-C"):
                for segment in range(1, CORRIDOR_SEGMENTS + 1):
                    next_zones[f"{smoke_id}{segment}"]["smoke"] = smoke
            else:
                next_zones[smoke_id]["smoke"] = smoke

        collapsed_count = sum(zone["collapsed"] for zone in old.values())
        rng_state = self.rng_state
        for template in _templates:
            if collapsed_count >= MAX_COLLAPSED_ZONES:
                break
            zone_id = template["id"]
            zone = next_zones[zone_id]
            if zone["collapsed"] or zone["type"] in ("stair", "elevator"):
                continue
            probability = collapse_probability(old[zone_id]["fire"])
            if probability == 0.0:
                continue
            rng_state, draw = _next_random(rng_state)
            if draw < probability:
                zone["collapsed"] = True
                collapsed_count += 1
        ended = all(next_zones[zone_id]["fire"] >= MAX_LEVEL for zone_id in ZONE_IDS)
        return next_zones, rng_state, ended

    def step_seconds(self, seconds: int = 1) -> None:
        """Advance to a visible second; jumps within a minute are equivalent to 1s steps."""
        if not isinstance(seconds, int) or seconds < 0:
            raise ValueError("seconds must be a nonnegative integer")
        remaining = seconds
        while remaining > 0 and not self.ended:
            if self._minute_target is None:
                self._minute_anchor = self.zones
                self._minute_target = self._calculate_next_minute()
            until_boundary = SECONDS_PER_MINUTE - self.second % SECONDS_PER_MINUTE
            jump = min(remaining, until_boundary)
            self.second += jump
            remaining -= jump
            target_zones, target_rng, target_ended = self._minute_target
            if self.second % SECONDS_PER_MINUTE == 0:
                self.zones = target_zones
                self.rng_state = target_rng
                self.ended = target_ended
                self.minute = self.second // SECONDS_PER_MINUTE
                self._minute_anchor = None
                self._minute_target = None
            else:
                progress = (self.second % SECONDS_PER_MINUTE) / SECONDS_PER_MINUTE
                anchor = self._minute_anchor
                assert anchor is not None
                self.zones = {
                    zone_id: {
                        **before,
                        "fire": before["fire"] + (target_zones[zone_id]["fire"] - before["fire"]) * progress,
                        "smoke": before["smoke"] + (target_zones[zone_id]["smoke"] - before["smoke"]) * progress,
                    }
                    for zone_id, before in anchor.items()
                }

    def snapshot(self) -> dict[str, Any]:
        """Return visible state only, without future minute targets or RNG state."""
        return {
            "second": self.second,
            "minute": self.minute,
            "seed": self.seed,
            "wind": self.wind,
            "ignitionId": self.ignition_id,
            "ended": self.ended,
            "zones": {zone_id: zone.copy() for zone_id, zone in self.zones.items()},
        }


def assert_js_parity(
    cases: tuple[tuple[int, int, tuple[int, ...]] |
                 tuple[int, int, tuple[int, ...], str], ...] | None = None,
) -> None:
    """Fail if Python scenario physics has drifted from the browser engine.

    This starts Node only for a few sampled scenarios.  Training itself stays
    entirely in Python and never calls Node for an individual environment step.
    """
    if cases is None:
        cases = (
            (2026, 1, (0, 30, 60, 90)),
            (2026, 5, (0, 30, 60, 90)),
            (2026, 10, (0, 30, 60, 90)),
            (2026, 15, (0, 30, 60, 90)),
            (12, 5, (1499, 1500)),  # Reaches actual collapses by 25 minutes.
            (2026, 5, (0, 30, 60, 90), "F10-R9"),
        )
    javascript = r"""
require('./config.js');
require('./engine.js');
const { createSimulation, stepSimulation } = globalThis.FireEvacEngine;
const [seed, wind, targetsText, ignitionId] = process.argv.slice(1);
const targets = JSON.parse(targetsText);
let state = createSimulation({ seed: Number(seed), wind: Number(wind), ignitionId });
const records = [];
for (const target of targets) {
  while (state.second < target && !state.ended) state = stepSimulation(state);
  records.push({
    second: state.second,
    ignitionId: state.ignitionId,
    ended: state.ended,
    rngState: state.rngState,
    zones: Object.fromEntries(Object.entries(state.zones).map(([id, z]) =>
      [id, { fire: z.fire, smoke: z.smoke, collapsed: z.collapsed }]))
  });
}
process.stdout.write(JSON.stringify(records));
"""
    for case in cases:
        seed, wind, target_seconds = case[:3]
        ignition_id = case[3] if len(case) == 4 else None
        if tuple(sorted(target_seconds)) != target_seconds:
            raise ValueError("Parity sample seconds must be increasing")
        try:
            process = subprocess.run(
                ["node", "-e", javascript, str(seed), str(wind), json.dumps(target_seconds),
                 ignition_id or ""],
                cwd=Path(__file__).resolve().parent,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Node and the current config.js/engine.js are required for parity checking") from exc
        expected = json.loads(process.stdout)
        actual = FireSimulator(seed, wind, ignition_id=ignition_id)
        for sample, target in zip(expected, target_seconds):
            actual.step_seconds(max(0, target - actual.second))
            prefix = f"seed={seed}, wind={wind}, ignition={ignition_id}, second={target}"
            if actual.second != sample["second"]:
                raise AssertionError(f"{prefix}: time differs from JavaScript")
            if actual.ignition_id != sample["ignitionId"]:
                raise AssertionError(f"{prefix}: ignition differs from JavaScript")
            if actual.ended != sample["ended"]:
                raise AssertionError(f"{prefix}: terminal state differs from JavaScript")
            if actual.rng_state != sample["rngState"]:
                raise AssertionError(f"{prefix}: collapse RNG state differs from JavaScript")
            for zone_id in ZONE_IDS:
                left = actual.zones[zone_id]
                right = sample["zones"][zone_id]
                if left["collapsed"] != right["collapsed"]:
                    raise AssertionError(f"{prefix}, zone={zone_id}: collapse differs from JavaScript")
                for field in ("fire", "smoke"):
                    if not math.isclose(left[field], right[field], rel_tol=1e-11, abs_tol=1e-9):
                        raise AssertionError(
                            f"{prefix}, zone={zone_id}: {field} differs: Python={left[field]}, JS={right[field]}"
                        )


__all__ = [
    "ZONE_IDS", "ROOM_IDS", "ZONE_TYPES", "MOVE_NEIGHBORS", "FireSimulator",
    "collapse_probability", "fire_growth_multiplier", "WIND_OPTIONS", "DEFAULT_WIND",
    "ROOF_SMOKE_CAP", "assert_js_parity",
]
