"""Owned, namespaced AE/CNT registration on an actual CSE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from onem2m.client import CSEClient, ProtocolError

AE_ROLES = {
    "sensor": "SmokeSensorAE", "controller": "FireRiskControllerAE",
    "display-a": "DisplayA_AE", "display-b": "DisplayB_AE", "display-c": "DisplayC_AE",
    "resident": "ResidentAppAE", "responder": "RescueAppAE", "occupancy": "OccupancyScenarioAE",
}


def bootstrap(client: CSEClient, base: str, namespace: str, callback: str, retention_seconds: int,
              *, decision_policies: bool = False, display_callbacks: dict[str, str] | None = None) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,47}", namespace):
        raise ValueError("Invalid run namespace")
    parent = "/" + base
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=retention_seconds)).strftime("%Y%m%dT%H%M%S")
    labels = ["fire-route", "namespace:" + namespace]
    display_callbacks = display_callbacks or {}
    if display_callbacks and set(display_callbacks) != {"display-a", "display-b", "display-c"}:
        raise ValueError("All three display callbacks are required")
    actors = {}
    for role, suffix in AE_ROLES.items():
        attrs = {"rn": namespace + "__" + suffix, "api": "Nfire-route.p0", "rr": role == "controller" or role in display_callbacks,
                 "srv": [client.release], "lbl": labels + ["role:" + role], "et": expiry}
        if role == "controller":
            attrs["poa"] = [callback]
        elif role in display_callbacks:
            attrs["poa"] = [display_callbacks[role]]
        resource = client.ensure(parent, 2, attrs, creator=client.for_actor("C", "ae-registration"))
        actors[role] = {"ae_id": resource["aei"], "ri": resource["ri"], "path": parent + "/" + attrs["rn"]}
    if len({a["ae_id"] for a in actors.values()}) != len(actors):
        raise ProtocolError("CSE did not provide distinct actor AE-IDs")
    policy_name = namespace + "__telemetry-policy"
    policy = client.ensure(parent, 1, {
        "rn": policy_name, "lbl": labels, "et": expiry,
        "pv": {"acr": [{"acor": [actors["sensor"]["ae_id"], actors["controller"]["ae_id"]], "acop": 3},
                         {"acor": [client.originator], "acop": 63}]},
        "pvs": {"acr": [{"acor": [client.originator], "acop": 63}]},
    })
    # P1 creates scoped policies before its CNTs, preserving P0's verified setup.
    decision_acps = {}
    if decision_policies:
        for name, readers in {"hazards": ["responder"], "routes": ["resident", "responder"]}.items():
            resource = client.ensure(parent, 1, {
                "rn": namespace + "__" + name + "-policy", "lbl": labels, "et": expiry,
                "pv": {"acr": [{"acor": [actors["controller"]["ae_id"]], "acop": 3},
                                {"acor": [actors[r]["ae_id"] for r in readers], "acop": 2},
                                {"acor": [client.originator], "acop": 63}]},
                "pvs": {"acr": [{"acor": [client.originator], "acop": 63}]},
            })
            decision_acps[name] = resource["ri"]
    containers = {}
    for role, names in {"sensor": ["telemetry"], "controller": ["hazards", "routes"],
                        "display-a": ["commands", "acks"], "display-b": ["commands", "acks"],
                        "display-c": ["commands", "acks"], "occupancy": ["observations"]}.items():
        for name in names:
            attrs = {"rn": name, "lbl": labels, "mni": 1000, "et": expiry}
            if role == "sensor":
                # Use the actual ACP resource ID, as in upstream ACME's ACP tests.
                attrs["acpi"] = [policy["ri"]]
            elif role == "controller" and name in decision_acps:
                attrs["acpi"] = [decision_acps[name]]
            elif role in display_callbacks:
                device, controller = actors[role]["ae_id"], actors["controller"]["ae_id"]
                writer, reader = (controller, device) if name == "commands" else (device, controller)
                display_policy = client.ensure(parent, 1, {
                    "rn": namespace + "__" + role + "-" + name + "-policy", "lbl": labels, "et": expiry,
                    "pv": {"acr": [{"acor": [writer], "acop": 3}, {"acor": [reader], "acop": 2},
                                    {"acor": [reader], "acop": 1, "acod": [{"ty": 3, "chty": [23]}]},
                                    {"acor": [client.originator], "acop": 63}]},
                    "pvs": {"acr": [{"acor": [client.originator], "acop": 63}]},
                })
                attrs["acpi"] = [display_policy["ri"]]
            resource = client.ensure(actors[role]["path"], 3, attrs)
            containers[role + "/" + name] = {"ri": resource["ri"], "path": actors[role]["path"] + "/" + name}
    return {"actors": actors, "containers": containers, "telemetry_policy_ri": policy["ri"], "namespace": namespace}
