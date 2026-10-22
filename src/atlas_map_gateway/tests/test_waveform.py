import dataclasses
from datetime import datetime
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from atlas_map_gateway import seismic
from atlas_map_gateway.app import create_app
from atlas_map_gateway.tests.fakes import FIX, SETTINGS, FakeEarthScope, deps

MSEED = FIX / "axcc1_hhz_20260901.mseed"
OK = {"ok": True, "file": str(MSEED), "source_url": "https://service.earthscope.org/fdsnws/dataselect/1/query?x"}
NO_DATA = {"ok": False, "error": {"type": "no_data", "message": "EarthScope returned no waveform data"}}


class LaggingEarthScope(FakeEarthScope):
    """Serves the fixture only for windows that begin before the archive's newest data."""

    def __init__(self, archived_until):
        super().__init__(OK)
        self.archived_until = archived_until

    def download_waveform(self, network, station, channel, begin, end, location="--"):
        self.calls.append((network, station, channel, begin, end, location))
        return OK if begin < self.archived_until else NO_DATA


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
        self.assertEqual(r.json()["message"], "No recording in the last 24 hours.")
        self.assertEqual(len(es.calls), 1 + 12 + 3 * 4)   # the live window, every archive-lag probe, then BHZ, MHZ, LHZ back an hour

    def test_lagging_archive_serves_the_newest_window_instead_of_nothing(self):
        es = LaggingEarthScope(archived_until="2026-09-23T10:40:00Z")   # 80 minutes behind the 12:00 clock
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1", params={"minutes": 10})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rawCount"], 12001)
        self.assertIsNone(r.json()["message"])
        # The live window and the 15/30/60-minute probes are empty; the 90-minute probe finds data. That is over an
        # hour behind, so the lower-rate channels are tried at the live window; they lag too, so HHZ's window stays.
        self.assertEqual([(c[2], c[4]) for c in es.calls][:6],
                         [("HHZ", "2026-09-23T11:58:00Z"), ("HHZ", "2026-09-23T11:43:00Z"), ("HHZ", "2026-09-23T11:28:00Z"),
                          ("HHZ", "2026-09-23T10:58:00Z"), ("HHZ", "2026-09-23T10:28:00Z"), ("HHZ", "2026-09-23T10:28:00Z")])
        self.assertEqual({c[2] for c in es.calls[6:]}, {"BHZ", "MHZ", "LHZ"})   # each looked back up to an hour, all lagging
        self.assertEqual(r.json()["channel"], "HHZ")
        self.assertNotIn("requestedChannel", r.json())

    def test_a_stalled_high_rate_channel_gives_way_to_a_current_lower_rate_one(self):
        class StalledHigh(FakeEarthScope):   # 200 and 40 samples/s stopped; 8 samples/s current, as on 2026-10-21
            def download_waveform(self, network, station, channel, begin, end, location="--"):
                self.calls.append((network, station, channel, begin, end, location))
                return OK if channel[0] in "ML" else NO_DATA
        es = StalledHigh(OK)
        app = TestClient(create_app(SETTINGS, deps(earthscope=es)))
        r = app.get("/waveform/OO.AXCC1", params={"minutes": 10})
        self.assertEqual((r.json()["channel"], r.json()["requestedChannel"]), ("MHZ", "HHZ"))
        self.assertEqual(r.json()["rawCount"], 12001)
        self.assertIsNone(r.json()["message"])
        # BHZ and MHZ were probed with one-minute windows; only the MHZ window that is returned was a full download.
        span = lambda c: (datetime.fromisoformat(c[4].replace("Z", "+00:00")) - datetime.fromisoformat(c[3].replace("Z", "+00:00"))).seconds // 60
        lower = [(c[2], span(c)) for c in es.calls if c[2] != "HHZ"]
        self.assertEqual(lower, [("BHZ", 1), ("BHZ", 1), ("BHZ", 1), ("BHZ", 1), ("MHZ", 1), ("MHZ", 10)])
        es.calls.clear()
        app.get("/waveform/OO.AXCC1", params={"minutes": 10})
        self.assertEqual(es.calls, [])   # the fallback outcome and the window are cached
        h = app.get("/waveform/OO.AXCC1/health").json()
        self.assertTrue(h["recording"])
        self.assertEqual((h["channel"], h["requestedChannel"]), ("MHZ", "HHZ"))

    def test_lower_rate_channels_keep_sensor_and_component(self):
        from atlas_map_gateway.routes_data import lower_rate_channels
        self.assertEqual(lower_rate_channels("HHZ"), ["BHZ", "MHZ", "LHZ"])
        self.assertEqual(lower_rate_channels("EHZ"), ["SHZ", "MHZ", "LHZ"])
        self.assertEqual(lower_rate_channels("HDH"), ["BDH", "MDH", "LDH"])
        self.assertEqual(lower_rate_channels("LHZ"), [])

    def test_channels_the_map_does_not_show_are_never_probed(self):
        es = LaggingEarthScope(archived_until="2026-09-23T10:40:00Z")
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1", params={"channel": "LHZ"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["points"], [])
        self.assertEqual(len(es.calls), 1)   # the requested window only: no archive-lag probes
        self.assertEqual(r.json()["message"], "No recording in this window.")

    def test_health_reports_the_archive_delay(self):
        es = LaggingEarthScope(archived_until="2026-09-23T10:40:00Z")
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1/health")
        self.assertTrue(r.json()["recording"])
        self.assertEqual(r.json()["latestMs"], 1788220860000)   # the fixture's last sample, 2026-09-01T00:01:00Z
        self.assertEqual(r.json()["delayMinutes"], 22 * 1440 + 719)   # to the fake clock's 2026-09-23T12:00:00Z

    def test_health_reports_recent_waveform_availability_without_claiming_operational_status(self):
        r = TestClient(create_app(SETTINGS, deps(earthscope=FakeEarthScope(OK)))).get("/waveform/OO.AXCC1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["station"], "OO.AXCC1")
        self.assertTrue(r.json()["recording"])
        self.assertNotIn("status", r.json())

    def test_channel_must_be_three_letters_or_digits(self):
        for channel in ("HH*", "HHZ,HHN", "hhz", "HH", "HHZZ", "H?Z", ""):
            with self.subTest(channel=channel):
                es = FakeEarthScope(OK)
                r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1", params={"channel": channel})
                self.assertEqual(r.status_code, 422)
                self.assertEqual(r.json()["error"]["source"], "atlas")
                self.assertEqual(es.calls, [])
        es = FakeEarthScope(OK)
        r = TestClient(create_app(SETTINGS, deps(earthscope=es))).get("/waveform/OO.AXCC1", params={"channel": "HHN"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(es.calls[0][2], "HHN")

    def test_request_dir_is_deleted_after_decoding(self):
        root = Path(tempfile.mkdtemp(prefix="atlas-gateway-test-"))
        self.addCleanup(shutil.rmtree, root, True)
        request_dir = root / "requests" / "earthscope-20260923T115800Z-abc123def456"
        request_dir.mkdir(parents=True)
        shutil.copy(MSEED, request_dir / "OO.AXCC1.blank.HHZ.20260923T114800Z.mseed")
        (request_dir / "manifest.json").write_text("{}")
        es = FakeEarthScope({**OK, "file": str(request_dir / "OO.AXCC1.blank.HHZ.20260923T114800Z.mseed")})
        r = TestClient(create_app(SETTINGS, deps(earthscope=es, earthscope_root=root))).get("/waveform/OO.AXCC1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rawCount"], 12001)
        self.assertFalse(request_dir.exists())
        self.assertTrue((root / "requests").is_dir())   # only the request's own dir goes

    def test_files_outside_the_gateway_root_are_never_deleted(self):
        root = Path(tempfile.mkdtemp(prefix="atlas-gateway-test-"))
        self.addCleanup(shutil.rmtree, root, True)
        for owned_root in (None, root):   # no root configured, and a root the fixture is not under
            with self.subTest(root=owned_root):
                r = TestClient(create_app(SETTINGS, deps(earthscope=FakeEarthScope(OK), earthscope_root=owned_root))).get("/waveform/OO.AXCC1")
                self.assertEqual(r.status_code, 200)
                self.assertTrue(MSEED.exists())
        self.assertFalse(seismic.discard_request_dir(root / "stray.mseed", root))   # directly in the root: not a request dir
        self.assertTrue(root.exists())

    def test_corrupt_miniseed_is_500_and_still_cleaned_up(self):
        root = Path(tempfile.mkdtemp(prefix="atlas-gateway-test-"))
        self.addCleanup(shutil.rmtree, root, True)
        request_dir = root / "requests" / "earthscope-20260923T115800Z-000000000000"
        request_dir.mkdir(parents=True)
        (request_dir / "bad.mseed").write_bytes(b"this is not miniseed" * 50)
        es = FakeEarthScope({**OK, "file": str(request_dir / "bad.mseed")})
        app = create_app(SETTINGS, deps(earthscope=es, earthscope_root=root))
        with self.assertLogs("atlas_map_gateway", level="ERROR"):
            r = TestClient(app, raise_server_exceptions=False).get("/waveform/OO.AXCC1")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.json(), {"error": {"source": "atlas", "message": "internal error"}})
        self.assertFalse(request_dir.exists())

    def test_busy_limiter_is_503_with_display_source(self):
        busy = dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01)
        app = create_app(busy, deps(earthscope=FakeEarthScope(OK)))
        with app.state.limiter.slot("EarthScope"):
            r = TestClient(app).get("/waveform/OO.AXCC1")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["source"], "EarthScope")


if __name__ == "__main__":
    unittest.main()
