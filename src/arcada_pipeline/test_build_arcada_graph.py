import unittest

from build_arcada_graph import correct_earthscope_rows, station_summary

SHORT_PERIOD = "CMG-6TF, 1s-100Hz, 2400 V/m/s-DM-24 Mk3 Variable Gain"
BROADBAND = "CMG-1T, 360 s, 3000 V/m/s-DM-24 Mk3 Fixed Gain"


def chan(code, rate, sensor, end=None):
    return {"location": "", "channel": code, "sensor": sensor, "sample_rate_hz": rate, "start": "2014-08-01", "end": end}


def snapshot(**stations):
    return {"retrieved_at": "2026-10-21T19:28:15+00:00",
            "stations": {f"OO.{k}": {"source_url": f"https://fdsn/?sta={k}", "channels": v} for k, v in stations.items()}}


ARCADA_TEMPLATE = ("Name: Seismic Station AXAS1\nType: seismometer\nDescription: Broadband seismometer at ASHES recording volcanic "
                   "seismicity\nChannels: BHZ, BHN, BHE\nEarthScope network: OO / station: AXAS1")


class StationSummaryTest(unittest.TestCase):
    def test_short_period_station_lists_its_channel_groups_vertical_first(self):
        s = station_summary({"channels": [chan(c, 200.0, SHORT_PERIOD) for c in ("EHE", "EHN", "EHZ")] + [chan("LHZ", 1.0, SHORT_PERIOD)]})
        self.assertEqual(s["model"], "CMG-6TF")
        self.assertTrue(s["class"].startswith("Short-period seismometer"))
        self.assertEqual(s["seismic_channels"], "EHZ, EHN, EHE at 200 Hz; LHZ at 1 Hz")
        self.assertIsNone(s["closed"])

    def test_sensor_names_keep_commas_inside_parentheses(self):
        s = station_summary({"channels": [chan("HHZ", 200.0, BROADBAND),
                                          chan("LDO", 1.0, "Tidal Seafloor Pressure (Tsunameter 2,000 psia): PREST Series B")]})
        self.assertEqual(s["other_channels"], "LDO (Tidal Seafloor Pressure (Tsunameter 2,000 psia): PREST Series B, 1 Hz)")

    def test_closed_station_reports_its_last_channel_end(self):
        s = station_summary({"channels": [chan("BNZ", 40.0, "SCTA", "2021-08-27"), chan("MNZ", 8.0, "SCTA", "2021-08-20")]})
        self.assertEqual(s["closed"], "2021-08-27")


class CorrectRowsTest(unittest.TestCase):
    def test_template_station_gets_its_real_class_and_channels_with_an_audit_trail(self):
        rows = [{"id": "EARTHSCOPE-OO-AXAS1", "type": "seismometer", "text": ARCADA_TEMPLATE, "_source_row_index": 7},
                {"id": "EARTHSCOPE-OO-AXAS1::desc", "type": "seismometer", "_source_row_index": 8,
                 "text": "Broadband seismometer at ASHES recording volcanic seismicity"}]
        fixes = correct_earthscope_rows(rows, snapshot(AXAS1=[chan("EHZ", 200.0, SHORT_PERIOD)]))
        self.assertEqual(len(fixes), 2)
        self.assertIn("Description: Short-period seismometer (Güralp CMG-6TF, 1 s to 100 Hz) at ASHES", rows[0]["text"])
        self.assertIn("Channels: EHZ at 200 Hz", rows[0]["text"])
        self.assertNotIn("BHZ", rows[0]["text"])
        self.assertTrue(rows[1]["text"].startswith("Short-period seismometer"))
        self.assertEqual(rows[0]["_repair"]["reason"], "earthscope_station_metadata_corrected")
        self.assertEqual(len(rows[0]["_repair"]["original_text_sha256"]), 64)

    def test_non_seismometer_keeps_its_channel_list_and_gains_the_closing_date(self):
        text = "Type: tiltmeter\nDescription: Tiltmeter station (retired 2021).\nChannels: BNE, BNZ, BKA"
        rows = [{"id": "EARTHSCOPE-OO-AXCC2", "type": "tiltmeter", "text": text, "_source_row_index": 3}]
        correct_earthscope_rows(rows, snapshot(AXCC2=[chan("BNZ", 40.0, "SCTA", "2021-08-27")]))
        self.assertIn("Channels: BNE, BNZ, BKA", rows[0]["text"])
        self.assertIn("(retired 2021). Station closed: every channel ended 2021-08-27 (EarthScope).", rows[0]["text"])

    def test_rows_without_a_snapshot_station_are_untouched(self):
        rows = [{"id": "RS03AXBS-LJ03A-12-CTDPFB301", "type": "ctd", "text": "Description: CTD", "_source_row_index": 1}]
        self.assertEqual(correct_earthscope_rows(rows, snapshot()), [])
        self.assertNotIn("_repair", rows[0])


if __name__ == "__main__":
    unittest.main()


class CorrectionTests(unittest.TestCase):
    def test_corrections_fix_titles_abstracts_links_and_positions(self):
        from build_arcada_graph import apply_corrections
        rows = [
            {"id": "paper::10.1234/x", "type": "paper", "title": "Cut titl", "_source_row_index": 0, "keywords": ["sonar"],
             "text": "Cut titl (2020) — J\n\nAnother paper's abstract.\nRelevant instruments: A, B",
             "linked_instruments": ["A", "B"]},
            {"id": "RS03AXPS-PC03A-4A-CTDPFA303", "type": "ctd", "_source_row_index": 1,
             "text": "Name: CTD\nLatitude: 45.9316\nLongitude: -129.9808\nDepth: 2607 m"},
        ]
        catalog = {"RS03AXPS-PC03A-4A-CTDPFA303": {"latitude": "45.9316", "longitude": "-129.9808", "depth_m": "2607"}}
        corrections = {
            "papers": [{"doi": "10.1234/x", "title": "Cut title in full", "abstract": "The paper's own abstract.", "keywords": [],
                        "reason": "r", "authority": "https://doi.org/10.1234/x"}],
            "links": [{"doi": "10.1234/x", "linked_instruments": ["B"], "removed": ["A"], "evidence": {"B": "named by code"}, "reason": "l"}],
            "instruments": [{"id": "RS03AXPS-PC03A-4A-CTDPFA303", "latitude": 45.8305, "longitude": -129.7535, "depth_m": 2607,
                             "depth_text": "200 m (shallow-profiler platform; water depth 2607 m)", "reason": "p", "authority": "https://o"}],
        }
        done = apply_corrections(rows, catalog, corrections)
        self.assertEqual(rows[0]["title"], "Cut title in full")
        self.assertEqual(rows[0]["text"], "Cut title in full (2020) — J\n\nThe paper's own abstract.\nRelevant instruments: B")
        self.assertEqual(rows[0]["linked_instruments"], ["B"])
        self.assertEqual(rows[0]["keywords"], [])
        self.assertIn("Latitude: 45.8305\nLongitude: -129.7535\nDepth: 200 m (shallow-profiler platform", rows[1]["text"])
        self.assertEqual(catalog["RS03AXPS-PC03A-4A-CTDPFA303"]["latitude"], 45.8305)
        self.assertEqual(done[0]["removed_links"], ["A"])
        self.assertTrue(all("original_text_sha256" in r["_repair"] for r in rows))
