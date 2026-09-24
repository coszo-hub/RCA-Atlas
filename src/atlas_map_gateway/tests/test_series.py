import dataclasses
import unittest
from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from atlas_map_gateway import thinning
from atlas_map_gateway.app import create_app
from atlas_map_gateway.erddap import ErddapClient
from atlas_map_gateway.tests.fakes import SETTINGS, deps

REF = "RS03AXPS-PC03A-4A-CTDPFA303"
DS = "ooi-rs03axps-pc03a-4a-ctdpfa303"
INFO = {"table": {"columnNames": ["Row Type", "Variable Name", "Attribute Name", "Data Type", "Value"], "rows": [
    ["attribute", "NC_GLOBAL", "time_coverage_start", "String", "2014-10-02T20:42:00Z"],
    ["attribute", "NC_GLOBAL", "time_coverage_end", "String", "2026-09-23T10:48:00Z"],
    ["variable", "time", "", "double", ""], ["attribute", "time", "units", "String", "seconds since 1970-01-01T00:00:00Z"],
    ["variable", "z", "", "double", ""],
    ["variable", "sea_water_temperature", "", "double", ""],
    ["attribute", "sea_water_temperature", "units", "String", "degree_Celsius"],
    ["attribute", "sea_water_temperature", "long_name", "String", "Water Temperature"],
    ["variable", "sea_water_temperature_qc_agg", "", "int", ""],
]}}
CSV = "time,sea_water_temperature\nUTC,degree_Celsius\n2026-09-20T00:00:00Z,7.32\n2026-09-20T00:01:00Z,NaN\n2026-09-20T00:02:00Z,7.33\n"


def transport(handler_log, csv=CSV, csv_status=200, info=INFO):
    def handler(request: httpx.Request):
        handler_log.append(str(request.url))
        if "/info/" in request.url.path:
            return httpx.Response(200, json=info)
        return httpx.Response(csv_status, text=csv)
    return httpx.MockTransport(handler)


def client(log, **kw):
    erd = ErddapClient(httpx.Client(transport=transport(log, **kw)))
    return TestClient(create_app(SETTINGS, deps(erddap=erd)))


class ThinningTest(unittest.TestCase):
    def test_small_series_unchanged(self):
        self.assertEqual(thinning.minmax([1, 2, 3], [5, 6, 7], 10), ([1, 2, 3], [5, 6, 7]))

    def test_keeps_extremes_and_order(self):
        t = list(range(10_000))
        v = [0.0] * 10_000
        v[4321], v[8000] = 99.0, -99.0
        tt, vv = thinning.minmax(t, v, 2000)
        self.assertLessEqual(len(tt), 2000)
        self.assertIn(99.0, vv)
        self.assertIn(-99.0, vv)
        self.assertEqual(tt, sorted(tt))


class SeriesRouteTest(unittest.TestCase):
    def test_variables_exclude_coordinates_and_qc(self):
        r = client([]).get(f"/series/{REF}/variables")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"variables": [{"name": "sea_water_temperature", "units": "degree_Celsius", "longName": "Water Temperature"}],
                                    "coverage": {"start": "2014-10-02T20:42:00Z", "end": "2026-09-23T10:48:00Z"}})

    def test_series_skips_nan_and_builds_download_url(self):
        log = []
        r = client(log).get(f"/series/{REF}", params={"var": "sea_water_temperature",
                                                      "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["units"], "degree_Celsius")
        self.assertEqual(body["rawCount"], 2)
        self.assertEqual(body["points"][0], [1789862400000, 7.32])
        self.assertIn(f"/tabledap/{DS}.csv?time,sea_water_temperature", body["downloadUrl"])
        self.assertIn("time%3E=2026-09-20T00:00:00Z", log[0])

    def test_no_feed_is_404(self):
        r = client([]).get("/series/RS01SBPD-DP01A-01-CTDPFL104", params={"var": "x", "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["source"], "atlas")

    def test_missing_query_param_is_422_with_error_body(self):
        r = client([]).get(f"/series/{REF}", params={"start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(set(r.json()), {"error"})
        self.assertEqual(r.json()["error"]["source"], "atlas")
        self.assertIn("var", r.json()["error"]["message"])

    def test_millisecond_times_parse(self):
        csv = "time,sea_water_temperature\nUTC,degree_Celsius\n2026-09-20T00:00:00.000Z,7.32\n2026-09-20T00:00:00.500Z,7.33\n"
        r = client([], csv=csv).get(f"/series/{REF}", params={"var": "sea_water_temperature",
                                                              "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["points"], [[1789862400000, 7.32], [1789862400500, 7.33]])

    def test_malformed_info_is_502(self):
        bad_rows = ([["attribute", "NC_GLOBAL"]], [None], ["x"], "rows")
        for rows in bad_rows:
            with self.subTest(rows=rows):
                r = client([], info={"table": {"rows": rows}}).get(f"/series/{REF}/variables")
                self.assertEqual(r.status_code, 502)
                self.assertEqual(r.json()["error"]["source"], "ERDDAP")

    def test_csv_missing_units_cell_is_502(self):
        r = client([], csv="time,sea_water_temperature\nUTC\n").get(
            f"/series/{REF}", params={"var": "sea_water_temperature", "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["source"], "ERDDAP")

    def test_range_over_31_days_is_422(self):
        r = client([]).get(f"/series/{REF}", params={"var": "sea_water_temperature", "start": "2026-08-01T00:00:00Z", "end": "2026-09-02T00:00:01Z"})
        self.assertEqual(r.status_code, 422)

    def test_bad_variable_name_is_422(self):
        r = client([]).get(f"/series/{REF}", params={"var": "time,lat", "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 422)

    def test_long_erddap_variable_names_pass(self):
        var = "concentration_of_colored_dissolved_organic_matter_in_sea_water_expressed_as_equivalent_mass_fraction_of_quinine_sulfate_dihydrate_profiler_depth_enabled"
        csv = f"time,{var}\nUTC,1e-9\n2026-09-20T00:00:00Z,1.5\n"
        r = client([], csv=csv).get(f"/series/{REF}", params={"var": var, "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["points"]), 1)

    def test_end_before_start_is_422(self):
        r = client([]).get(f"/series/{REF}", params={"var": "sea_water_temperature", "start": "2026-09-21T00:00:00Z", "end": "2026-09-20T00:00:00Z"})
        self.assertEqual(r.status_code, 422)

    def test_erddap_no_results_is_empty_not_error(self):
        r = client([], csv="Error {\n    code=404;\n    message=\"Not Found: Your query produced no matching results.\";\n}\n", csv_status=404).get(
            f"/series/{REF}", params={"var": "sea_water_temperature", "start": "2030-01-01T00:00:00Z", "end": "2030-01-02T00:00:00Z"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["points"], [])
        self.assertEqual(r.json()["message"], "No readings in this range.")

    def test_html_instead_of_csv_is_502(self):
        r = client([], csv="<html>maintenance</html>").get(
            f"/series/{REF}", params={"var": "sea_water_temperature", "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["error"]["source"], "ERDDAP")

    def test_series_is_cached(self):
        log = []
        c = client(log)
        params = {"var": "sea_water_temperature", "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"}
        c.get(f"/series/{REF}", params=params)
        c.get(f"/series/{REF}", params=params)
        self.assertEqual(len(log), 1)

    def test_busy_limiter_is_503_with_display_source(self):
        erd = ErddapClient(httpx.Client(transport=transport([])))
        app = create_app(dataclasses.replace(SETTINGS, per_host_limit=1, upstream_timeout=0.01), deps(erddap=erd))
        with app.state.limiter.slot("ERDDAP"):
            r = TestClient(app).get(f"/series/{REF}", params={"var": "sea_water_temperature",
                                                             "start": "2026-09-20T00:00:00Z", "end": "2026-09-21T00:00:00Z"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["source"], "ERDDAP")


if __name__ == "__main__":
    unittest.main()
