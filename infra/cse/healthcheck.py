"""A health probe queries the upstream CSE, not a parallel REST health server."""
import json
from urllib.request import Request, urlopen
from uuid import uuid4

rqi = "fire-route-health-" + uuid4().hex
req = Request("http://127.0.0.1:8080/fire-route-dev", headers={
    "X-M2M-Origin": "CAdmin", "X-M2M-RI": rqi, "X-M2M-RVI": "4", "Accept": "application/json"})
with urlopen(req, timeout=3) as response:
    body = json.load(response)
    if (response.status != 200 or response.headers.get("X-M2M-RSC") != "2000"
            or response.headers.get("X-M2M-RI") != rqi
            or body.get("m2m:cb", {}).get("ty") != 5):
        raise SystemExit(1)
