"""Strict oneM2M HTTP binding client. No mock mode or CSE implementation."""
from __future__ import annotations

from dataclasses import dataclass
import json
import ssl
import time
from typing import Callable
from urllib import error, request
from urllib.parse import quote, urlsplit
from uuid import uuid4

from backend.config import http_url

MAX_RESPONSE_BYTES = 1024 * 1024
RESOURCE_ROOTS = {1: "m2m:acp", 2: "m2m:ae", 3: "m2m:cnt", 4: "m2m:cin", 9: "m2m:grp", 23: "m2m:sub"}


class CSEError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None, rsc: int | None = None):
        super().__init__(message)
        self.http_status, self.rsc = http_status, rsc


class TransportError(CSEError):
    pass


class ProtocolError(CSEError):
    pass


class ResourceConflict(CSEError):
    pass


@dataclass(frozen=True)
class WireResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class RejectRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTPTransport:
    def __init__(self):
        self.opener = request.build_opener(RejectRedirect(), request.HTTPSHandler(context=ssl.create_default_context()))

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> WireResponse:
        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=timeout)
        except error.HTTPError as exc:
            response = exc
        except (error.URLError, OSError, TimeoutError) as exc:
            # Do not interpolate a URL, credential-bearing exception or response body.
            raise TransportError(f"CSE transport unavailable ({type(exc).__name__})") from exc
        try:
            with response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ProtocolError("CSE response exceeds size limit")
                return WireResponse(response.code, dict(response.headers), data)
        except (OSError, TimeoutError) as exc:
            raise TransportError(f"CSE response interrupted ({type(exc).__name__})") from exc


def strict_json(data: bytes | str):
    def reject(value):
        raise ValueError("Non-finite JSON value")
    return json.loads(data, parse_constant=reject)


class CSEClient:
    def __init__(self, url: str, originator: str, release: str, *, timeout: float = 5,
                 transport: Callable | None = None, evidence=None, actor: str = "bootstrap"):
        self.url = http_url(url, "CSE_BASE_URL")
        if not originator or any(c in originator for c in "\r\n"):
            raise ValueError("Invalid originator")
        self.originator, self.release, self.timeout = originator, release, timeout
        self.transport = HTTPTransport() if transport is None else transport
        self.evidence, self.actor = evidence, actor

    def for_actor(self, originator: str, actor: str) -> "CSEClient":
        return CSEClient(self.url, originator, self.release, timeout=self.timeout,
                         transport=self.transport, evidence=self.evidence, actor=actor)

    def _request(self, method: str, path: str, resource_type: int | None = None, payload: dict | None = None,
                 *, aggregate: bool = False) -> dict:
        if (not path.startswith("/") or path.startswith("//") or any(c in path for c in "?#\r\n")
                or any(p in {".", ".."} for p in path.split("/"))):
            raise ValueError("Resource path must stay inside the configured CSE endpoint")
        rqi = "fr-" + uuid4().hex
        headers = {"X-M2M-Origin": self.originator, "X-M2M-RI": rqi, "X-M2M-RVI": self.release, "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/vnd.onem2m-res+json;ty=" + str(resource_type)
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        record = {"actor": self.actor, "method": method, "path": path, "request_id": rqi,
                  "request_headers": {k: v for k, v in headers.items() if k != "X-M2M-Origin"}, "request_body": payload}
        start = time.monotonic()
        try:
            wire = self.transport(method, self.url + quote(path, safe="/:~_-"), headers, body, self.timeout)
            rh = {k.lower(): v for k, v in wire.headers.items()}
            record.update(http_status=wire.status, response_headers={k: v for k, v in rh.items() if k in {"x-m2m-ri", "x-m2m-rvi", "x-m2m-rsc", "content-type"}})
            if 300 <= wire.status < 400:
                raise ProtocolError("CSE redirect rejected", http_status=wire.status)
            try:
                rsc = int(rh["x-m2m-rsc"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ProtocolError("Missing/invalid oneM2M response status", http_status=wire.status) from exc
            record["rsc"] = rsc
            media = rh.get("content-type", "").split(";", 1)[0].lower()
            if wire.body and media not in {"application/json", "application/vnd.onem2m-res+json"}:
                raise ProtocolError("Unexpected CSE response media type", http_status=wire.status, rsc=rsc)
            if rh.get("x-m2m-ri") != rqi:
                raise ProtocolError("oneM2M response request ID mismatch", http_status=wire.status, rsc=rsc)
            if rh.get("x-m2m-rvi") not in {None, self.release}:
                raise ProtocolError("oneM2M response release mismatch", http_status=wire.status, rsc=rsc)
            try:
                result = strict_json(wire.body) if wire.body else {}
                if not isinstance(result, dict):
                    raise ValueError("object required")
            except (ValueError, UnicodeDecodeError) as exc:
                raise ProtocolError("Invalid CSE JSON representation", http_status=wire.status, rsc=rsc) from exc
            record["response_body"] = result
            if not 200 <= wire.status < 300 or not 2000 <= rsc < 3000:
                raise CSEError(f"CSE operation denied/failed (HTTP {wire.status}, RSC {rsc})", http_status=wire.status, rsc=rsc)
            expected = 2000 if aggregate else (2001 if method == "POST" else 2000)
            if rsc != expected:
                raise ProtocolError(f"Unexpected oneM2M success status for {method}", http_status=wire.status, rsc=rsc)
            if aggregate:
                responses = result.get("m2m:agr", {}).get("m2m:rsp") if isinstance(result.get("m2m:agr"), dict) else None
                if (wire.status != 200 or not isinstance(responses, list) or not responses
                        or any(not isinstance(member, dict) or member.get("rqi") != rqi
                               or type(member.get("rsc")) is not int for member in responses)):
                    raise ProtocolError("Malformed/uncorrelated fan-out aggregate", http_status=wire.status, rsc=rsc)
            return result
        except CSEError as exc:
            record["error"] = type(exc).__name__
            raise
        finally:
            record["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
            if self.evidence:
                self.evidence.append("requests.jsonl", record)

    def retrieve(self, path: str) -> dict:
        return self._request("GET", path)

    def create(self, path: str, resource_type: int, attributes: dict) -> dict:
        if resource_type not in RESOURCE_ROOTS:
            raise ValueError("Unsupported P0 resource type")
        result = self._request("POST", path, resource_type, {RESOURCE_ROOTS[resource_type]: attributes})
        self.resource(result, resource_type)
        return result

    def fanout_create(self, path: str, attributes: dict) -> dict:
        if not path.endswith("/fopt"):
            raise ValueError("Fan-out CREATE must target the actual group fanOutPoint")
        # The aggregate is OK; each successful member CREATE is CREATED.
        return self._request("POST", path, 4, {"m2m:cin": attributes}, aggregate=True)

    @staticmethod
    def resource(result: dict, resource_type: int) -> dict:
        if not isinstance(result, dict):
            raise ProtocolError("CSE resource representation must be an object")
        value = result.get(RESOURCE_ROOTS[resource_type])
        if (not isinstance(value, dict) or type(value.get("ty")) is not int or value.get("ty") != resource_type
                or not isinstance(value.get("ri"), str) or not value["ri"]):
            raise ProtocolError("CSE resource representation/type/ID missing")
        if resource_type == 2 and (not isinstance(value.get("aei"), str) or not value["aei"]):
            raise ProtocolError("CSE did not return an AE-ID")
        return value

    def ensure(self, parent: str, resource_type: int, attributes: dict, *, creator: "CSEClient" | None = None) -> dict:
        name = attributes["rn"]
        if not isinstance(name, str) or not name or "/" in name:
            raise ValueError("Invalid resource name")
        path = parent.rstrip("/") + "/" + name
        try:
            result = self.retrieve(path)
        except CSEError as exc:
            if isinstance(exc, ProtocolError) or exc.rsc != 4004:
                raise
            try:
                result = (creator or self).create(parent, resource_type, attributes)
            except CSEError as conflict:
                if isinstance(conflict, ProtocolError) or conflict.rsc != 4105:
                    raise
                result = self.retrieve(path)
        value = self.resource(result, resource_type)
        for key, expected in attributes.items():
            if key == "et":
                continue  # Existing owned resources retain their expiration; never extend silently.
            actual = value.get(key)
            matches = set(expected) <= set(actual or []) if key == "lbl" else actual == expected
            if not matches:
                raise ResourceConflict(f"Existing resource differs at {key}; not overwritten")
        return value
