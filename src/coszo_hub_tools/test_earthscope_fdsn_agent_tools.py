import json
import tempfile
import unittest
from pathlib import Path

from earthscope_fdsn_agent_tools import EarthScopeFDSNToolkit, dispatch_earthscope


class FakeEarthScopeHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, *, url, params, max_bytes):
        self.calls.append({"url": url, "params": params, "max_bytes": max_bytes})
        if "/station/1/query" in url and params.get("format") == "text":
            text = (
                "#Network|Station|Location|Channel|Latitude|Longitude|Elevation|Depth|Azimuth|Dip|SensorDescription|Scale|ScaleFreq|ScaleUnits|SampleRate|StartTime|EndTime\n"
                "OO|HYS14||MHZ|44.5691|-125.1479|-767.0|767.0|0.0|-90.0|OBS|1.0|1.0|M/S|8.0|2022-01-01T00:00:00|\n"
            )
            return 200, {"Content-Type": "text/plain"}, text.encode(), url
        if "/station/1/query" in url and params.get("format") == "xml":
            return 200, {"Content-Type": "application/xml"}, b"<FDSNStationXML><Network code='OO'/></FDSNStationXML>", url
        if "/dataselect/1/query" in url:
            return 200, {"Content-Type": "application/vnd.fdsn.mseed"}, b"MSEED-DATA", url
        if "/availability/1/query" in url:
            return 410, {"Content-Type": "text/plain"}, b"Gone", url
        raise AssertionError(f"unexpected URL {url}")


class EarthScopeToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.http = FakeEarthScopeHTTP()
        self.toolkit = EarthScopeFDSNToolkit(runtime_root=Path(self.temp.name) / "EarthScope", http_get=self.http)

    def tearDown(self):
        self.temp.cleanup()

    def selection(self):
        return {"network": "OO", "station": "HYS14", "location": "--", "channel": "MHZ",
                "begin": "2026-09-01T00:00:00Z", "end": "2026-09-01T01:00:00Z"}

    def test_status_and_plan_are_offline(self):
        status = self.toolkit.status()
        self.assertFalse(status["public_data_credentials_required"])
        plan = self.toolkit.plan_waveform(**self.selection())
        self.assertFalse(plan["live_request_executed"])
        self.assertEqual(plan["duration_hours"], 1)
        self.assertEqual(self.http.calls, [])

    def test_waveform_limit_and_exact_station(self):
        args = self.selection(); args["end"] = "2026-09-03T00:00:00Z"
        result = dispatch_earthscope(self.toolkit, "earthscope_plan_waveform", args)
        self.assertFalse(result["ok"])
        self.assertIn("maximum", result["error"]["message"])
        args = self.selection(); args["station"] = "HYS*"
        result = dispatch_earthscope(self.toolkit, "earthscope_plan_waveform", args)
        self.assertFalse(result["ok"])

    def test_search_channels_parses_fdsn_text(self):
        result = self.toolkit.search_channels("OO", station="HYS14", channel="MHZ")
        self.assertTrue(result["ok"])
        self.assertEqual(result["records"][0]["Station"], "HYS14")
        self.assertEqual(result["records"][0]["SampleRate"], "8.0")

    def test_waveform_download_writes_manifest_and_hash(self):
        result = self.toolkit.download_waveform(**self.selection())
        self.assertTrue(result["ok"])
        self.assertEqual(result["byte_size"], 10)
        self.assertEqual(len(result["sha256"]), 64)
        self.assertTrue(Path(result["file"]).is_file())
        manifest = Path(result["file"]).with_name("manifest.json")
        self.assertEqual(json.loads(manifest.read_text())["sha256"], result["sha256"])

    def test_stationxml_download(self):
        result = self.toolkit.download_stationxml("OO", "HYS14", channel="MHZ")
        self.assertTrue(result["ok"])
        self.assertTrue(result["file"].endswith("OO.HYS14.station.xml"))
        self.assertIn(b"FDSNStationXML", Path(result["file"]).read_bytes())

    def test_availability_410_is_explicit(self):
        result = self.toolkit.query_availability(**self.selection())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "service_unavailable")
        self.assertEqual(result["error"]["http_status"], 410)

    def test_url_guard(self):
        with self.assertRaises(ValueError):
            self.toolkit._approved_url("http://localhost/private")


if __name__ == "__main__":
    unittest.main()
