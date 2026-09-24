import dataclasses
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from atlas_map_gateway import seismic
from atlas_map_gateway.app import create_app
from atlas_map_gateway.tests.fakes import FIX, SETTINGS, FakeEarthScope, deps

MSEED = FIX / "axcc1_hhz_20260901.mseed"
OK = {"ok": True, "file": str(MSEED), "source_url": "https://service.earthscope.org/fdsnws/dataselect/1/query?x"}


class DecodeTest(unittest.TestCase):
    def test_decode_fixture(self):
        d = seismic.decode(MSEED)
        self.assertEqual(d["rate"], 200.0)
        self.assertEqual(len(d["samples"]), 12001)
        self.assertEqual((min(d["samples"]), max(d["samples"])), (-35842, -33044))
        self.assertEqual(d["start"], "2026-09-01T00:00:00Z")


class WaveformRouteTest(unittest.TestCase):
    def test_window_ends_two_minutes_before_now_and_is_thinned(self):
        es = FakeEarthScope(OK)
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1", params={"minutes": 10})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(es.calls, [("OO", "AXCC1", "HHZ", "2026-09-23T11:48:00Z", "2026-09-23T11:58:00Z", "--")])
        self.assertLessEqual(len(body["points"]), 2000)
        self.assertEqual(body["rawCount"], 12001)
        self.assertEqual(body["rate"], 200.0)
        self.assertIn(-35842, [p[1] for p in body["points"]])

    def test_minutes_capped(self):
        r = TestClient(create_app(SETTINGS, deps(earthscope=FakeEarthScope(OK)))).get("/waveform/OO.AXCC1", params={"minutes": 61})
        self.assertEqual(r.status_code, 422)

    def test_unknown_station_404(self):
        r = TestClient(create_app(SETTINGS, deps(earthscope=FakeEarthScope(OK)))).get("/waveform/OO.NOPE")
        self.assertEqual(r.status_code, 404)

    def test_bad_station_id_422(self):
        r = TestClient(create_app(SETTINGS, deps(earthscope=FakeEarthScope(OK)))).get("/waveform/OO_AXCC1")
        self.assertEqual(r.status_code, 422)

    def test_no_data_is_empty_series(self):
        es = FakeEarthScope({"ok": False, "error": {"type": "no_data", "message": "EarthScope returned no waveform data"}})
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["points"], [])
        self.assertEqual(r.json()["message"], "No recording in this window.")

    def test_busy_limiter_is_503_with_display_source(self):
        busy = dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01)
        app = create_app(busy, deps(earthscope=FakeEarthScope(OK)))
        with app.state.limiter.slot("EarthScope"):
            r = TestClient(app).get("/waveform/OO.AXCC1")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["source"], "EarthScope")


if __name__ == "__main__":
    unittest.main()
