"""Actual-CSE T05 runner. Environment failures never produce PASS."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import errno
import json
import platform
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from uuid import uuid4

from backend.config import ConfigurationError, Settings
from backend.evidence import Evidence, source_identity
from backend.notifications import NotificationService, NotificationStore, notification_server
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient, CSEError, ProtocolError, TransportError, strict_json
from simulator.events import fixture_nodes, synthetic_smoke

ROOT = Path(__file__).resolve().parents[1]


def default_fixture() -> Path:
    source = ROOT / "fixtures/building_3f.json"
    return source if source.is_file() else Path(sys.prefix) / "share/fire-route/fixtures/building_3f.json"


class IntegrationBlocked(RuntimeError):
    pass


def probe(client: CSEClient, base: str) -> dict:
    result = client.retrieve("/" + base)
    cb = result.get("m2m:cb")
    if (not isinstance(cb, dict) or type(cb.get("ty")) is not int or cb.get("ty") != 5
            or type(cb.get("cst")) is not int or cb.get("cst") not in {1, 2, 3}
            or not isinstance(cb.get("csi"), str) or not cb["csi"].startswith("/")
            or not isinstance(cb.get("ri"), str)):
        raise ProtocolError("Endpoint did not return a oneM2M CSEBase with actual type/ID")
    if client.release not in cb.get("srv", []):
        raise ProtocolError("Selected oneM2M release is not advertised by the actual CSE")
    for resource_type in (1, 2, 3, 4, 23):
        if resource_type not in cb.get("srt", []):
            raise ProtocolError("Actual CSE does not advertise a required P0 resource type")
    return cb


def wait_for_cse(client: CSEClient, settings: Settings) -> dict:
    deadline = time.monotonic() + settings.startup_timeout
    while True:
        try:
            return probe(client, settings.cse_base)
        except TransportError as exc:
            if time.monotonic() >= deadline:
                raise IntegrationBlocked("Actual CSE endpoint unreachable within startup budget") from exc
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))


def subscription_refs(cse_id: str, path: str, resource: dict) -> set[str]:
    ri = resource["ri"]
    return {path, ri, cse_id.rstrip("/") + "/" + ri.lstrip("/")}


def run(settings: Settings, *, require_target_python: bool = True) -> tuple[dict, Path]:
    evidence = Evidence(settings.evidence_root, secret_values=(settings.admin_originator,))
    namespace = "fr_" + uuid4().hex[:16]
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "phase": "P0", "test": "T05",
                "namespace": namespace, "python": platform.python_version(), "platform": platform.platform(),
                "settings": settings.public(), "deployment_option": "standalone_dev_CSE_NOT_MEC",
                "real_CSE": False, "real_MEC": False, "input": "SYNTHETIC", **source_identity(ROOT)}
    metadata["observed_cse_runtime"] = None
    evidence.write("meta.json", metadata)
    server = worker = None
    summary = {"test": "T05", "state": "NOT_RUN", "pass": 0, "fail": 0, "blocked": 0,
               "all_device_acks": "NOT_RUN", "MEC": "unavailable", "latency_samples": 0}
    try:
        if settings.runtime_info:
            if not settings.runtime_info.is_file():
                raise IntegrationBlocked("CSE runtime metadata not available")
            metadata["observed_cse_runtime"] = strict_json(settings.runtime_info.read_bytes())
            evidence.write("meta.json", metadata)
        if require_target_python and sys.version_info < (3, 11):
            raise IntegrationBlocked("Product runtime requires Python >=3.11; use the Python 3.12 Compose profile")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
                pass
        except OSError as exc:
            raise IntegrationBlocked("Runtime denies network socket creation; real CSE test cannot run") from exc
        nodes = fixture_nodes(default_fixture())
        admin = CSEClient(settings.cse_url, settings.admin_originator, settings.release,
                          timeout=settings.request_timeout, evidence=evidence)
        cb = wait_for_cse(admin, settings)
        metadata.update(real_CSE=True, actual_cse_base=cb)
        evidence.write("meta.json", metadata)
        store = NotificationStore(evidence.path / "notification-state.sqlite3")
        service = NotificationService(store, cb["csi"], settings.release, nodes, evidence)
        try:
            server = notification_server(settings.bind_host, settings.bind_port, service)
        except OSError as exc:
            if exc.errno in {errno.EPERM, errno.EACCES, errno.EADDRINUSE}:
                raise IntegrationBlocked("Notification listener unavailable (permissions or occupied port)") from exc
            raise
        worker = Thread(target=server.serve_forever, name="fireroute-p0-notifications", daemon=True)
        worker.start()
        resources = bootstrap(admin, settings.cse_base, namespace, settings.notification_url, settings.retention_seconds)
        evidence.write("resources.json", resources)
        controller = admin.for_actor(resources["actors"]["controller"]["ae_id"], "controller")
        sensor = admin.for_actor(resources["actors"]["sensor"]["ae_id"], "sensor")
        telemetry = resources["containers"]["sensor/telemetry"]["path"]
        attrs = {"rn": "controller-sub", "nu": [settings.notification_url], "enc": {"net": [3]},
                 "nct": 1, "lbl": ["fire-route", "namespace:" + namespace]}
        sub = controller.ensure(telemetry, 23, attrs)
        refs = subscription_refs(cb["csi"], telemetry + "/controller-sub", sub)
        verified = store.verified_refs() & refs
        if not verified:
            raise ProtocolError("SUB creation did not produce the matching actual verification callback")
        service.approve(refs)
        # Re-read the actual SUB, rather than inferring persistence from CREATE.
        actual_sub = controller.resource(controller.retrieve(telemetry + "/controller-sub"), 23)
        if actual_sub["ri"] != sub["ri"]:
            raise ProtocolError("SUB read-back resource ID mismatch")
        event = synthetic_smoke(nodes, namespace)
        evidence.event(hop="sensor_generated", event_id=event.event_id, incident_id=event.incident_id,
                       timestamp_utc=event.timestamp_utc, data_origin="SYNTHETIC")
        cin_name = "event-" + uuid4().hex
        cin = sensor.resource(sensor.create(telemetry, 4, {"rn": cin_name, "cnf": "application/json:0",
                                     "con": json.dumps(event.to_dict(), separators=(",", ":"), allow_nan=False)}), 4)
        readback = sensor.resource(sensor.retrieve(telemetry + "/" + cin_name), 4)
        con = strict_json(readback["con"]) if isinstance(readback["con"], str) else readback["con"]
        if readback["ri"] != cin["ri"] or con != event.to_dict():
            raise ProtocolError("CIN read-back does not match generated sensor event")
        deadline = time.monotonic() + settings.notification_timeout
        while not store.find(event.event_id) and time.monotonic() < deadline:
            time.sleep(0.05)
        matches = store.find(event.event_id)
        if len(matches) != 1 or matches[0]["cin_ri"] != cin["ri"] or matches[0]["event"] != event.to_dict():
            raise ProtocolError("Actual matching CIN notification not durably received within deadline")
        summary.update(state="PASS", **{"pass": 1}, event_id=event.event_id, incident_id=event.incident_id,
                       cin_ri=cin["ri"], sub_ri=sub["ri"], verification_refs=sorted(verified),
                       notification_count=len(matches), actual_ae_count=len(resources["actors"]))
        evidence.write("assertions.json", {"CSEBase_readback": True, "distinct_AE_IDs": True,
                       "SUB_verification": True, "SUB_readback": True, "CIN_readback": True,
                       "matching_durable_notification": True, "source_event": event.to_dict(),
                       "received_notification": matches[0]})
    except IntegrationBlocked as exc:
        summary.update(state="BLOCKED", blocked=1, reason=str(exc))
    except (CSEError, ConfigurationError, ValueError, KeyError, OSError) as exc:
        # No raw exception payload/URL is printed or persisted here.
        summary.update(state="FAIL", fail=1, reason=str(exc) if isinstance(exc, CSEError) else type(exc).__name__)
    except Exception as exc:
        summary.update(state="FAIL", fail=1, reason="Unexpected runner error: " + type(exc).__name__)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
            if worker is not None:
                worker.join(timeout=5)
        evidence.write("summary.json", summary)
    return summary, evidence.path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    try:
        settings = Settings.load()
        if args.evidence_root:
            from dataclasses import replace
            settings = replace(settings, evidence_root=args.evidence_root)
        summary, path = run(settings)
    except (ConfigurationError, ValueError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}))
        return 2
    output = json.dumps({"evidence": str(path), **summary}, sort_keys=True)
    (path / "tests.txt").write_text("command: " + json.dumps(sys.orig_argv) + "\n" + output + "\n", encoding="utf-8")
    print(output)
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[summary["state"]]


if __name__ == "__main__":
    raise SystemExit(main())
