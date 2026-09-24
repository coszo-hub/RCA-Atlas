import dataclasses
import unittest

from fastapi.testclient import TestClient

from atlas_map_gateway.app import create_app
from atlas_map_gateway.tests.fakes import SETTINGS, FakePI, FakeQAQC, deps

REF = "RS03AXPS-PC03A-4A-CTDPFA303"
PLOTS = {"ok": True, "plots": [
    {"reference_designator": REF, "variable": "temperature", "time_span": "week", "overlay": "none",
     "data_range": "full", "depth_or_profile": "", "url": "https://ec2.qaqc.ooi-rca.net/QAQC_plots/a.png"},
    {"reference_designator": REF + "0", "variable": "temperature", "time_span": "week", "overlay": "none",
     "data_range": "full", "depth_or_profile": "", "url": "https://ec2.qaqc.ooi-rca.net/QAQC_plots/b.png"}]}
LISTING = {"ok": True, "instrument_id": "PI-COVIS", "endpoint_label": "COVIS raw", "relative_path": "2026/",
           "source_url": "http://piweb.ooirsn.uw.edu/covis/data/COVIS/2026/", "truncated": False,
           "entries": [{"name": "09/", "kind": "directory"}]}
COVIS_RAW = "PI-PORTAL-ENDPOINT-f13948dc081a8b044c"
CTD_ONLY = "PI-PORTAL-ENDPOINT-2c2cf0f8c135aeb3b5"


class PlotsFilesTest(unittest.TestCase):
    def test_plots_exact_refdes_only(self):
        q = FakeQAQC(PLOTS)
        r = TestClient(create_app(SETTINGS, deps(qaqc=q))).get(f"/plots/{REF}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"refdes": REF, "plots": [
            {"variable": "temperature", "timeSpan": "week", "overlay": "none", "dataRange": "full", "depth": "",
             "url": "https://ec2.qaqc.ooi-rca.net/QAQC_plots/a.png"}]})

    def test_plots_unknown_sensor_404(self):
        r = TestClient(create_app(SETTINGS, deps(qaqc=FakeQAQC(PLOTS)))).get("/plots/RS99XXXX-XX000-00-NOPE00000")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["source"], "atlas")

    def test_files_listing(self):
        pi = FakePI(LISTING)
        r = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-COVIS", params={"path": "2026/", "endpoint": COVIS_RAW})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entries"], [{"name": "09/", "kind": "directory"}])
        # The bundle's corpus endpoint id is translated to the toolkit's own endpoint id (matched by URL).
        self.assertEqual(pi.calls, [("PI-COVIS", "covis-raw", "2026/")])
        self.assertEqual(pi.limits, [5000])

    def test_files_unknown_endpoint_404(self):
        for endpoint in ("PI-PORTAL-ENDPOINT-nope", CTD_ONLY):   # unknown, and another instrument's endpoint
            with self.subTest(endpoint=endpoint):
                pi = FakePI(LISTING)
                r = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-COVIS", params={"endpoint": endpoint})
                self.assertEqual(r.status_code, 404)
                self.assertEqual(r.json()["error"]["source"], "atlas")
                self.assertEqual(pi.calls, [])

    def test_files_single_endpoint_without_endpoint_param(self):
        pi = FakePI({**LISTING, "instrument_id": "PI-CTDPFA110", "endpoint_label": "CTDPFA110 daily data"})
        r = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-CTDPFA110")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["endpointLabel"], "CTDPFA110 daily data")
        self.assertEqual(pi.calls, [("PI-CTDPFA110", None, "")])

    def test_files_newest_first_and_truncated(self):
        days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 10) for d in range(1, 29)]   # 252 days, oldest first
        entries = [{"name": f"{day}.dat", "kind": "file", "observation_date": day} for day in days]
        pi = FakePI({**LISTING, "entries": entries, "truncated": False})
        body = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-CTDPFA110").json()
        self.assertEqual(len(body["entries"]), 200)
        self.assertTrue(body["truncated"])
        self.assertEqual(body["entries"][0]["name"], "2026-09-28.dat")
        self.assertEqual([e["name"] for e in body["entries"]], sorted((e["name"] for e in body["entries"]), reverse=True))
        self.assertNotIn("2026-01-01.dat", [e["name"] for e in body["entries"]])

    def test_files_unknown_instrument_404(self):
        r = TestClient(create_app(SETTINGS, deps(pi=FakePI(LISTING)))).get("/files/PI-NOPE")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["source"], "atlas")

    def test_traversal_rejected_by_toolkit_is_422(self):
        pi = FakePI(exc=ValueError("Relative path escapes the endpoint"))
        r = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-COVIS", params={"path": "../../etc"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["source"], "PI portal")

    def test_busy_limiter_is_503_with_display_source(self):
        busy = dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01)
        for source, path in (("QA/QC", f"/plots/{REF}"), ("PI portal", "/files/PI-COVIS")):
            with self.subTest(source=source):
                app = create_app(busy, deps(qaqc=FakeQAQC(PLOTS), pi=FakePI(LISTING)))
                with app.state.limiter.slot(source):
                    r = TestClient(app).get(path)
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.json()["error"]["source"], source)


if __name__ == "__main__":
    unittest.main()
