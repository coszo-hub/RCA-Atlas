import dataclasses
import socket
import unittest

from fastapi.testclient import TestClient

from atlas_map_gateway.app import create_app
from atlas_map_gateway.tests.fakes import SETTINGS, FakeNereus, deps

REF = "RS03AXPS-PC03A-4A-CTDPFA303"
OK = {"ok": True, "evidence_mode": "live", "source_url": "https://nereus.ooirsn.uw.edu/hasura/v1/graphql",
      "instruments": [
          {"designator": REF + "X", "operationalStatusCode": "RETIRED"},
          {"designator": REF, "operationalStatusCode": "OPERATIONAL",
           "latestDataStatusConnection": {"status": {"code": "OK", "checkedAt": "2026-09-23T11:58:00Z", "delay": 30}}}]}


class StatusTest(unittest.TestCase):
    def client(self, nereus):
        return TestClient(create_app(SETTINGS, deps(nereus=nereus)))

    def test_health(self):
        self.assertEqual(self.client(FakeNereus(OK)).get("/health").json(), {"ok": True})

    def test_exact_designator_match(self):
        r = self.client(FakeNereus(OK)).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"refdes": REF, "status": "OPERATIONAL",
                                    "data": {"code": "OK", "checkedAt": "2026-09-23T11:58:00Z", "delay": 30},
                                    "evidenceMode": "live", "source": "Nereus",
                                    "sourceUrl": "https://nereus.ooirsn.uw.edu/hasura/v1/graphql"})

    def test_unknown_refdes_is_404_without_upstream_call(self):
        n = FakeNereus(OK)
        r = self.client(n).get("/status/RS99XXXX-XX000-00-NOPE00000")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(n.calls, [])

    def test_not_tracked_by_nereus_is_404(self):
        r = self.client(FakeNereus({**OK, "instruments": []})).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["source"], "Nereus")

    def test_toolkit_error_is_502(self):
        r = self.client(FakeNereus({"ok": False, "error": {"type": "http_error", "message": "HTTP 500"}})).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json(), {"error": {"source": "Nereus", "message": "HTTP 500"}})

    def test_malformed_payload_is_502(self):
        r = self.client(FakeNereus({"ok": True})).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 502)

    def test_timeout_is_504(self):
        r = self.client(FakeNereus(exc=socket.timeout("timed out"))).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 504)

    def test_busy_limiter_is_503_with_display_source(self):
        app = create_app(dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01), deps(nereus=FakeNereus(OK)))
        with app.state.limiter.slot("Nereus"):
            r = TestClient(app).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json(), {"error": {"source": "Nereus", "message": "Nereus is busy; try again shortly"}})

    def test_evidence_mode_is_normalized(self):
        cases = {"live": "live", "live_cache": "live", "snapshot_fallback": "snapshot", "something_new": "something_new"}
        for raw, shown in cases.items():
            with self.subTest(raw=raw):
                r = self.client(FakeNereus({**OK, "evidence_mode": raw})).get(f"/status/{REF}")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["evidenceMode"], shown)

    def test_unexpected_failure_is_500_with_error_shape(self):
        # A non-dict instrument makes the route itself fail (AttributeError): the catch-all keeps the error contract.
        app = create_app(SETTINGS, deps(nereus=FakeNereus({**OK, "instruments": ["not-a-dict"]})))
        with self.assertLogs("atlas_map_gateway", level="ERROR"):
            r = TestClient(app, raise_server_exceptions=False).get(f"/status/{REF}")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {"error": {"source": "atlas", "message": "internal error"}})

    def test_shutdown_hook_runs_when_the_app_stops(self):
        stopped = []
        with TestClient(create_app(SETTINGS, deps(nereus=FakeNereus(OK)), on_shutdown=lambda: stopped.append(1))) as c:
            self.assertEqual(c.get("/health").json(), {"ok": True})
            self.assertEqual(stopped, [])
        self.assertEqual(stopped, [1])

    def test_status_is_cached(self):
        n = FakeNereus(OK)
        c = self.client(n)
        c.get(f"/status/{REF}")
        c.get(f"/status/{REF}")
        self.assertEqual(len(n.calls), 1)


if __name__ == "__main__":
    unittest.main()
