"""Persist/reconcile the application outbox using actual CSE CIN resources."""
from __future__ import annotations

import hashlib
import json

from onem2m.client import CSEClient, ProtocolError, strict_json


def publish_pending(store, client: CSEClient, containers: dict, evidence=None) -> list[dict]:
    published = []
    for item in store.pending():
        records = {}
        suffix = hashlib.sha256(item["event_id"].encode()).hexdigest()
        for key, container_key in (("hazard", "controller/hazards"), ("route", "controller/routes")):
            parent = containers[container_key]["path"]
            name = key + "-" + suffix
            content_json = json.dumps(item[key], sort_keys=True, separators=(",", ":"), allow_nan=False)
            attrs = {"rn": name, "cnf": "application/json:0", "con": content_json}
            # Always GET before CREATE, including recovery after an ambiguous POST.
            # CSEClient never automatically retries a POST.
            created = client.ensure(parent, 4, attrs)
            read = client.resource(client.retrieve(parent + "/" + name), 4)
            content = strict_json(read["con"]) if isinstance(read["con"], str) else read["con"]
            if read["ri"] != created["ri"] or content != item[key]:
                raise ProtocolError("Decision CIN read-back differs from durable outbox")
            records[key] = {"path": parent + "/" + name, "ri": read["ri"], "content": content}
        # A partial write stays pending. A restart reconciles existing named CINs.
        store.delivered(item["event_id"])
        record = {"event_id": item["event_id"], **records}
        published.append(record)
        if evidence:
            evidence.append("decisions.jsonl", record)
            evidence.event(hop="route_CIN_readback", event_id=item["event_id"],
                           incident_id=item["route"]["incident_id"], route_version=item["route"]["route_version"],
                           route_status=item["route"]["status"], cin_ri=records["route"]["ri"])
    return published
