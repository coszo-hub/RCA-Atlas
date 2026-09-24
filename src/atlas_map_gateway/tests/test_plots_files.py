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

    def test_files_listing(self):
        pi = FakePI(LISTING)
        r = TestClient(create_app(SETTINGS, deps(pi=pi))).get("/files/PI-COVIS", params={"path": "2026/"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entries"], [{"name": "09/", "kind": "directory"}])
        self.assertEqual(pi.calls, [("PI-COVIS", None, "2026/")])

    def test_files_unknown_instrument_404(self):
        r = TestClient(create_app(SETTINGS, deps(pi=FakePI(LISTING)))).get("/files/PI-NOPE")
        self.assertEqual(r.status_code, 404)

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
