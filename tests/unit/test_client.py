"""Transport fixtures are unit-only; no fake CSE service is started."""
import json
import unittest

from onem2m.client import CSEClient, CSEError, ProtocolError, RejectRedirect, ResourceConflict, TransportError, WireResponse


class FixtureTransport:
    def __init__(self, responder=None):
        self.calls = []
        self.responder = responder

    def __call__(self, method, url, headers, body, timeout):
        call = {"method": method, "url": url, "headers": headers, "body": body, "timeout": timeout}
        self.calls.append(call)
        if self.responder:
            return self.responder(call)
        return response(call, {"m2m:cnt": {"ty": 3, "ri": "cnt-fixture", "rn": "telemetry"}}, 200 if method == "GET" else 201, "2000" if method == "GET" else "2001")


def response(call, body, status=200, rsc="2000", **headers):
    h = {"X-M2M-RI": call["headers"]["X-M2M-RI"], "X-M2M-RSC": rsc,
         "X-M2M-RVI": "4", "Content-Type": "application/json"}
    h.update(headers)
    return WireResponse(status, h, json.dumps(body).encode())


class ClientTests(unittest.TestCase):
    def client(self, transport=None):
        return CSEClient("http://unit.invalid", "C-unit", "4", transport=transport or FixtureTransport())

    def test_headers_resource_type_and_unique_request_ids(self):
        t = FixtureTransport()
        c = self.client(t)
        c.create("/base/ae", 3, {"rn": "telemetry"})
        c.retrieve("/base/ae/telemetry")
        self.assertIn("ty=3", t.calls[0]["headers"]["Content-Type"])
        self.assertEqual(t.calls[0]["headers"]["X-M2M-Origin"], "C-unit")
        self.assertNotEqual(t.calls[0]["headers"]["X-M2M-RI"], t.calls[1]["headers"]["X-M2M-RI"])
        self.assertEqual(json.loads(t.calls[0]["body"]), {"m2m:cnt": {"rn": "telemetry"}})

    def test_http_success_does_not_hide_onem2m_denial(self):
        c = self.client(FixtureTransport(lambda call: response(call, {}, 200, "4103")))
        with self.assertRaises(CSEError) as error:
            c.retrieve("/base")
        self.assertEqual(error.exception.rsc, 4103)

    def test_onem2m_success_does_not_hide_http_failure(self):
        c = self.client(FixtureTransport(lambda call: response(call, {}, 500, "2000")))
        with self.assertRaises(CSEError):
            c.retrieve("/base")

    def test_mismatched_ids_release_missing_status_and_invalid_json(self):
        mutations = [lambda w: WireResponse(w.status, {**w.headers, "X-M2M-RI": "unrelated"}, w.body),
                     lambda w: WireResponse(w.status, {**w.headers, "X-M2M-RVI": "5"}, w.body),
                     lambda w: WireResponse(w.status, {k: v for k, v in w.headers.items() if k != "X-M2M-RSC"}, w.body),
                     lambda w: WireResponse(w.status, w.headers, b"<html>not-CSE</html>"),
                     lambda w: WireResponse(w.status, w.headers, b'{"value": NaN}'),
                     lambda w: WireResponse(w.status, w.headers, b'[]')]
        for mutation in mutations:
            with self.subTest(case=mutations.index(mutation)), self.assertRaises(ProtocolError):
                self.client(FixtureTransport(lambda call: mutation(response(call, {})))).retrieve("/base")

    def test_redirects_are_not_followed_with_originator(self):
        self.assertIsNone(RejectRedirect().redirect_request(None, None, 302, "", {}, "http://other.invalid"))
        with self.assertRaises(ProtocolError):
            self.client(FixtureTransport(lambda call: response(call, {}, 302, "2000"))).retrieve("/base")

    def test_invalid_paths_do_not_call_transport(self):
        t = FixtureTransport()
        c = self.client(t)
        for path in ("http://other.invalid", "//other.invalid", "/base/../other", "/base?token=x", "/base\r\n"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                c.retrieve(path)
        self.assertFalse(t.calls)

    def test_distinct_actor_client_uses_returned_id(self):
        t = FixtureTransport()
        c = self.client(t).for_actor("C-returned-by-CSE", "sensor")
        c.retrieve("/base")
        self.assertEqual(t.calls[0]["headers"]["X-M2M-Origin"], "C-returned-by-CSE")

    def test_missing_resource_created_once_without_post_retry(self):
        def respond(call):
            if call["method"] == "GET":
                return response(call, {}, 404, "4004")
            return response(call, {"m2m:cnt": {"ty": 3, "ri": "actual-fixture-id", "rn": "telemetry", "lbl": ["owned"]}}, 201, "2001")
        t = FixtureTransport(respond)
        value = self.client(t).ensure("/base/ae", 3, {"rn": "telemetry", "lbl": ["owned"]})
        self.assertEqual(value["ri"], "actual-fixture-id")
        self.assertEqual([c["method"] for c in t.calls], ["GET", "POST"])

    def test_existing_unowned_resource_not_overwritten(self):
        t = FixtureTransport()
        with self.assertRaises(ResourceConflict):
            self.client(t).ensure("/base/ae", 3, {"rn": "telemetry", "lbl": ["my-namespace"]})
        self.assertEqual(len(t.calls), 1)

    def test_existing_denial_is_not_treated_as_not_found(self):
        t = FixtureTransport(lambda call: response(call, {}, 403, "4103"))
        with self.assertRaises(CSEError):
            self.client(t).ensure("/base", 3, {"rn": "telemetry"})
        self.assertEqual(len(t.calls), 1)

    def test_malformed_not_found_never_triggers_resource_creation(self):
        def respond(call):
            wire = response(call, {}, 404, "4004")
            return WireResponse(wire.status, wire.headers, b"not JSON")
        t = FixtureTransport(respond)
        with self.assertRaises(ProtocolError):
            self.client(t).ensure("/base", 3, {"rn": "telemetry"})
        self.assertEqual(len(t.calls), 1)

    def test_wrong_response_media_type_is_rejected(self):
        t = FixtureTransport(lambda call: response(call, {}, **{"Content-Type": "text/html"}))
        with self.assertRaises(ProtocolError):
            self.client(t).retrieve("/base")

    def test_transport_failure_does_not_replay_create(self):
        def fail(call):
            raise TransportError("unit transport interruption")
        t = FixtureTransport(fail)
        with self.assertRaises(TransportError):
            self.client(t).create("/base", 3, {"rn": "telemetry"})
        self.assertEqual(len(t.calls), 1)

    def test_ae_response_requires_actual_id(self):
        t = FixtureTransport(lambda call: response(call, {"m2m:ae": {"ty": 2, "ri": "ri-fixture"}}, 201, "2001"))
        with self.assertRaises(ProtocolError):
            self.client(t).create("/base", 2, {"rn": "ae"})
