import json
import tempfile
import unittest
from pathlib import Path

from ooi_m2m_agent_tools import OOIM2MToolkit, dispatch_ooi_m2m


REFDES = "RS03AXBS-MJ03A-06-PRESTA301"


class FakeHTTP:
    def __init__(self):
        self.calls = []

    def __call__(self, *, url, params, authenticated, max_bytes):
        self.calls.append({"url": url, "params": params, "authenticated": authenticated, "max_bytes": max_bytes})
        if url.endswith("/RS03AXBS/MJ03A/06-PRESTA301"):
            return 200, {"Content-Type": "application/json"}, json.dumps(["telemetered", "recovered_inst"]).encode(), url
        if url.endswith("/telemetered"):
            return 200, {"Content-Type": "application/json"}, json.dumps(["prest_real_time"]).encode(), url
        if url.endswith("/recovered_inst"):
            return 200, {"Content-Type": "application/json"}, json.dumps(["prest_recovered"]).encode(), url
        if "/prest_real_time" in url:
            body = {
                "requestUUID": "ooi-remote-123",
                "allURLs": [
                    "https://opendap.oceanobservatories.org/thredds/catalog/ooi/test/catalog.html",
                    "https://opendap.oceanobservatories.org/async_results/test/request",
                ],
                "sizeCalculation": 1234,
                "timeCalculation": 4,
            }
            return 200, {"Content-Type": "application/json"}, json.dumps(body).encode(), url
        if url.endswith("status.txt"):
            return 404, {"Content-Type": "text/plain"}, b"", url
        if url.endswith("status.json"):
            return 200, {"Content-Type": "application/json"}, b'{"status":"complete"}', url
        if url.endswith("/request"):
            html = '<a href="data-one.nc">data-one.nc</a><a href="provenance.json">provenance.json</a>'
            return 200, {"Content-Type": "text/html"}, html.encode(), url
        if url.endswith("catalog.xml"):
            xml = '<catalog><dataset><dataset name="two" urlPath="ooi/test/data-two.nc"/></dataset></catalog>'
            return 200, {"Content-Type": "application/xml"}, xml.encode(), url
        if url.endswith("data-one.nc"):
            return 200, {"Content-Type": "application/x-netcdf"}, b"NETCDF-ONE", url
        if url.endswith("data-two.nc"):
            return 200, {"Content-Type": "application/x-netcdf"}, b"NETCDF-TWO", url
        if url.endswith("provenance.json"):
            return 200, {"Content-Type": "application/json"}, b"{}", url
        raise AssertionError(f"unexpected URL {url}")


class OOIM2MToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inventory = self.root / "instruments.jsonl"
        self.inventory.write_text(json.dumps({
            "canonical_id": REFDES,
            "name": "Axial Base pressure",
            "instrument_type": "pressure",
            "projects": ["Regional Cabled Array"],
            "site": "RS03AXBS",
            "node": "MJ03A",
            "instrument_code": "06-PRESTA301",
        }) + "\n")
        self.http = FakeHTTP()
        self.toolkit = OOIM2MToolkit(
            runtime_root=self.root / "runtime",
            instrument_inventory=self.inventory,
            username="test-user",
            token="test-token",
            http_get=self.http,
        )

    def tearDown(self):
        self.temp.cleanup()

    def request_arguments(self, estimate_only=False):
        return {
            "reference_designator": REFDES,
            "method": "telemetered",
            "stream": "prest_real_time",
            "begin": "2026-09-01T00:00:00Z",
            "end": "2026-09-02T00:00:00Z",
            "estimate_only": estimate_only,
        }

    def test_status_never_exposes_secret_values(self):
        result = self.toolkit.status()
        self.assertTrue(result["ready_for_live_api"])
        self.assertNotIn("test-user", json.dumps(result))
        self.assertNotIn("test-token", json.dumps(result))

    def test_local_search_and_request_plan_need_no_network(self):
        result = self.toolkit.search_instruments(query="pressure")
        self.assertEqual(result["instruments"][0]["canonical_id"], REFDES)
        plan = self.toolkit.plan_request(**self.request_arguments())
        self.assertFalse(plan["live_request_executed"])
        self.assertEqual(plan["duration_days"], 1)
        self.assertEqual(self.http.calls, [])

    def test_request_window_is_bounded(self):
        args = self.request_arguments()
        args["end"] = "2027-09-02T00:00:00Z"
        result = dispatch_ooi_m2m(self.toolkit, "ooi_m2m_plan_request", args)
        self.assertFalse(result["ok"])
        self.assertIn("maximum", result["error"]["message"])

    def test_stream_discovery(self):
        result = self.toolkit.list_streams(REFDES)
        self.assertEqual(result["count"], 2)
        self.assertEqual({r["method"] for r in result["streams"]}, {"telemetered", "recovered_inst"})

    def test_no_credentials_blocks_live_request(self):
        toolkit = OOIM2MToolkit(runtime_root=self.root / "other", instrument_inventory=self.inventory,
                                username="", token="", http_get=self.http)
        result = dispatch_ooi_m2m(toolkit, "ooi_m2m_request_data", self.request_arguments())
        self.assertFalse(result["ok"])
        self.assertIn("OOI_USERNAME", result["error"]["message"])

    def test_request_status_catalog_and_download_lifecycle(self):
        submitted = self.toolkit.request_data(**self.request_arguments())
        self.assertTrue(submitted["ok"])
        state_text = Path(submitted["state_file"]).read_text()
        self.assertNotIn("test-user", state_text)
        self.assertNotIn("test-token", state_text)

        status = self.toolkit.request_status(submitted["local_request_id"])
        self.assertTrue(status["complete"])
        self.assertEqual(len(status["checks"]), 2)

        listed = self.toolkit.list_result_files(submitted["local_request_id"], suffixes=[".nc"])
        self.assertEqual({x["name"] for x in listed["files"]}, {"data-one.nc", "data-two.nc"})

        result = self.toolkit.download_results(submitted["local_request_id"], suffixes=[".nc"], max_total_bytes=100)
        self.assertEqual(result["downloaded_count"], 2)
        self.assertEqual(result["total_bytes"], 20)
        for item in result["files"]:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertTrue(Path(item["path"]).is_file())

    def test_refdes_and_url_validation(self):
        with self.assertRaises(ValueError):
            self.toolkit.split_refdes("../../etc/passwd")
        with self.assertRaises(ValueError):
            self.toolkit._approved_url("http://127.0.0.1/secret")


if __name__ == "__main__":
    unittest.main()
