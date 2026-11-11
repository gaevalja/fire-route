"""Application contract validation. These values are not standard CSE primitives."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from uuid import uuid4


class ContractError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fixture_nodes(path: Path) -> frozenset[str]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    nodes = [n["id"] for n in graph["nodes"]]
    if len(nodes) != len(set(nodes)) or graph["origin_node"] not in nodes:
        raise ContractError("Invalid fixture node definitions")
    for edge in graph["edges"]:
        weight = edge["weight"]
        if (edge["from"] not in nodes or edge["to"] not in nodes or isinstance(weight, bool)
                or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0):
            raise ContractError("Invalid fixture edge")
    if not graph["exits"] or not set(graph["exits"]) <= set(nodes):
        raise ContractError("Invalid fixture exits")
    return frozenset(nodes)


@dataclass(frozen=True)
class SensorEvent:
    schema_version: int
    event_id: str
    incident_id: str
    sensor_id: str
    sensor_type: str
    location_node: str
    value: float
    unit: str
    sequence: int
    timestamp_utc: str
    source: str
    data_origin: str

    @classmethod
    def parse(cls, data: dict, nodes: frozenset[str]) -> "SensorEvent":
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ContractError("SensorEvent must contain exactly the versioned contract fields")
        for name in ("event_id", "incident_id", "sensor_id", "sensor_type", "location_node", "unit", "timestamp_utc", "source", "data_origin"):
            value = data[name]
            if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(c in value for c in "\r\n"):
                raise ContractError(f"Invalid {name}")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ContractError("Unsupported schema_version")
        if type(data["sequence"]) is not int or data["sequence"] < 0:
            raise ContractError("sequence must be a nonnegative integer")
        value = data["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ContractError("value must be a finite number")
        units = {"synthetic_smoke_index": "unitless_0_100", "temperature_celsius": "degC"}
        if data["sensor_type"] not in units or units[data["sensor_type"]] != data["unit"]:
            raise ContractError("Unknown sensor type or mismatched unit")
        if data["sensor_type"] == "synthetic_smoke_index" and not 0 <= value <= 100:
            raise ContractError("Synthetic smoke index must be in 0..100")
        if data["data_origin"] not in {"SYNTHETIC", "PHYSICAL"}:
            raise ContractError("Unknown data provenance")
        if data["sensor_type"] == "synthetic_smoke_index" and data["data_origin"] != "SYNTHETIC":
            raise ContractError("Synthetic index cannot claim physical measurement")
        if data["location_node"] not in nodes:
            raise ContractError("Unknown fixture node")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", data["timestamp_utc"]):
            raise ContractError("timestamp_utc must use UTC RFC3339 syntax")
        try:
            time = datetime.fromisoformat(data["timestamp_utc"].replace("Z", "+00:00"))
            if time.utcoffset() is None or time.utcoffset().total_seconds() != 0:
                raise ValueError("not UTC")
        except ValueError as exc:
            raise ContractError("timestamp_utc must be timezone-aware UTC") from exc
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)


def synthetic_smoke(nodes: frozenset[str], namespace: str) -> SensorEvent:
    return SensorEvent.parse({
        "schema_version": 1, "event_id": "e-" + uuid4().hex, "incident_id": "inc-" + uuid4().hex,
        "sensor_id": "smoke-F2-A", "sensor_type": "synthetic_smoke_index", "location_node": "F2_A",
        "value": 90, "unit": "unitless_0_100", "sequence": 1, "timestamp_utc": utc_now(),
        "source": namespace + ":sensor", "data_origin": "SYNTHETIC",
    }, nodes)
