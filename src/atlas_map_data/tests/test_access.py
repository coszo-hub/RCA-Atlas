import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import access

EXT = {"erddap": {"ooi-rs03axps-pc03a-4a-ctdpfa303"}, "qaqc": {"RS03AXPS-PC03A-4A-CTDPFA303"}, "warnings": []}
PI = {"INSTRUMENT-pi": [{"instrument_key": "PI-COVIS", "label": "COVIS raw", "url": "http://piweb.ooirsn.uw.edu/covis/data/COVIS/raw/"}]}


def rec(**kw):
    base = {"id": "X", "instrumentId": "INSTRUMENT-x", "refdes": None, "sources": []}
    base.update(kw)
    return base


class AccessTest(unittest.TestCase):
    def test_erddap_id_pattern(self):
        self.assertEqual(access.erddap_dataset_id("RS03AXPS-PC03A-4A-CTDPFA303"), "ooi-rs03axps-pc03a-4a-ctdpfa303")

    def test_ooi_sensor_with_feed_and_plots(self):
        routes = access.build_access(rec(refdes="RS03AXPS-PC03A-4A-CTDPFA303"), EXT, PI, {})
        kinds = [r["kind"] for r in routes]
        self.assertEqual(kinds[:3], ["erddap", "qaqc", "ooi_explorer"])
        erd = routes[0]
        self.assertEqual(erd["datasetId"], "ooi-rs03axps-pc03a-4a-ctdpfa303")
        self.assertTrue(erd["url"].startswith("https://erddap.dataexplorer.oceanobservatories.org/erddap/tabledap/"))

    def test_ooi_sensor_without_public_feed_has_no_erddap(self):
        routes = access.build_access(rec(refdes="RS01SBPD-DP01A-01-CTDPFL104"), EXT, PI, {})
        self.assertNotIn("erddap", [r["kind"] for r in routes])
        self.assertIn("ooi_explorer", [r["kind"] for r in routes])

    def test_earthscope_station(self):
        r = rec(id="EARTHSCOPE-OO-AXCC1")
        self.assertEqual(access.earthscope_station(r), ("OO", "AXCC1"))
        routes = access.build_access(r, EXT, PI, {"OO.AXCC1": "HHZ"})
        es = [x for x in routes if x["kind"] == "earthscope"][0]
        self.assertEqual((es["network"], es["station"], es["channel"]), ("OO", "AXCC1", "HHZ"))

    def test_pi_portal_endpoints(self):
        routes = access.build_access(rec(instrumentId="INSTRUMENT-pi"), EXT, PI, {})
        pi = [x for x in routes if x["kind"] == "pi_portal"]
        self.assertEqual(pi[0]["instrumentKey"], "PI-COVIS")
        self.assertEqual(pi[0]["url"], "http://piweb.ooirsn.uw.edu/covis/data/COVIS/raw/")

    def test_documentation_only_sensor(self):
        routes = access.build_access(rec(sources=["https://coszo.org/x"]), EXT, PI, {})
        self.assertEqual([r["kind"] for r in routes], ["documentation"])

    def test_disallowed_hosts_are_dropped(self):
        routes = access.build_access(rec(sources=["https://evil.example.com/x", "http://10.0.0.5/x"]), EXT, PI, {})
        self.assertEqual(routes, [])

    def test_missing_caches_warn_but_do_not_fail(self):
        with tempfile.TemporaryDirectory() as d:
            ext = access.load_external(Path(d))
        self.assertEqual(ext["erddap"], set())
        self.assertEqual(ext["qaqc"], set())
        self.assertEqual(len(ext["warnings"]), 2)

    def test_refresh_qaqc_parses_refdes_from_plot_paths(self):
        paths = ["RS03AXPS/RS03AXPS-PC03A-4A-CTDPFA303_temperature_week_none_full.png",
                 "CE04OSPS/CE04OSPS-SF01B-2A-CTDPFA107_salinity_day_none_full.png"]
        with tempfile.TemporaryDirectory() as d:
            n = access.refresh_qaqc(Path(d), paths)
            saved = json.loads((Path(d) / "qaqc_refdes.json").read_text())
        self.assertEqual(n, 1)
        self.assertEqual(saved["refdes"], ["RS03AXPS-PC03A-4A-CTDPFA303"])


if __name__ == "__main__":
    unittest.main()
