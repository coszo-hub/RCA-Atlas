import json
import tempfile
import unittest
from pathlib import Path

from build_asset_metadata import calibration_for, changes, coefficients, cruise_label, recovery_cruise, short_codes, source_serials

CRUISES = {
    "AT50-41": {"CUID": "AT50-41", "ShipName": "Atlantis", "cruiseStartDateTime": "2025-08-04T00:00:00",
                "cruiseStopDateTime": "2025-08-30T00:00:00", "notes": "Cabled (rvdata) Visions 25"},
    "TN313": {"CUID": "TN313", "ShipName": "Thomas G. Thompson", "cruiseStartDateTime": "2014-07-13T00:00:00",
              "cruiseStopDateTime": "2014-10-06T00:00:00", "notes": "Cabled (rvdata)"},
}


class AssetMetadataTests(unittest.TestCase):
    def test_a_recovery_cruise_is_recorded_or_inferred_from_the_end_date(self):
        self.assertEqual(recovery_cruise({"CUID_Recover": "TN313", "stopDateTime": "2025-08-15T00:20:00"}, CRUISES), ("TN313", False))
        self.assertEqual(recovery_cruise({"CUID_Recover": "", "stopDateTime": "2025-08-15T00:20:00"}, CRUISES), ("AT50-41", True))
        self.assertEqual(recovery_cruise({"CUID_Recover": "", "stopDateTime": "2021-03-01T00:00:00"}, CRUISES), ("", False))

    def test_a_cruise_is_named_with_its_ship_dates_and_ooi_name(self):
        self.assertEqual(cruise_label("AT50-41", CRUISES), "AT50-41 (Atlantis, 2025-08-04 to 2025-08-30, Visions 25)")
        self.assertEqual(cruise_label("TN313", CRUISES), "TN313 (Thomas G. Thompson, 2014-07-13 to 2014-10-06)")

    def test_a_deployment_uses_the_latest_calibration_on_or_before_its_start(self):
        files = {"U": [("2014-05-07", Path("a")), ("2015-05-10", Path("b")), ("2016-02-27", Path("c"))]}
        self.assertEqual(calibration_for("U", "2015-07-13T00:00:00", files)[0], "2015-05-10")
        self.assertEqual(calibration_for("U", "2015-05-10T00:00:00", files)[0], "2015-05-10")
        self.assertEqual(calibration_for("U", "2013-01-01T00:00:00", files)[0], "2014-05-07")   # none before: the first
        self.assertIsNone(calibration_for("V", "2015-01-01T00:00:00", files))

    def test_short_codes_are_the_class_as_written(self):
        self.assertEqual(short_codes("RS03CCAL-MJ03F-09-SCPRAA301"), ["SCPRA", "SCPR"])
        self.assertEqual(short_codes("RS03CCAL-MJ03F-05-BOTPTA301"), ["BOTPT", "BOTP"])

    def test_long_calibration_arrays_are_summarized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cal.csv"
            values = ", ".join(str(i / 10) for i in range(83))
            path.write_text(f'serial,name,value,notes\n1,CC_a0,1.2e-03,\n1,CC_taarray,"[{values}]",\n', encoding="utf-8")
            self.assertEqual(coefficients(path), ["CC_a0 = 1.2e-03", "CC_taarray = array of 83 values (0.0, 0.1, 0.2, ...)"])

    def test_the_timeline_names_what_changed_between_deployments(self):
        assets = {"A": {"Manufacturer's Serial No./Other Identifier": "16-50031", "Model": "SBE 16plus V2"},
                  "B": {"Manufacturer's Serial No./Other Identifier": "16-50128", "Model": "SBE 16plus V2"},
                  "N7": {"Manufacturer's Serial No./Other Identifier": "SN0007"}, "N11": {"Manufacturer's Serial No./Other Identifier": "SN0011"}}
        prev = {"sensor.uid": "A", "node.uid": "N7", "lat": "45.816847", "lon": "-129.754157", "deployment_depth": "2606"}
        same = dict(prev)
        self.assertEqual(changes(prev, same, assets, ("2014-05-07", "a"), ("2014-05-07", "a")), [])
        moved = {"sensor.uid": "B", "node.uid": "N11", "lat": "45.817847", "lon": "-129.754157", "deployment_depth": "2598"}
        self.assertEqual(changes(prev, moved, assets, ("2014-05-07", "a"), ("2015-05-10", "b")),
                         ["sensor 16-50031 replaced by 16-50128 (B)", "node box SN0007 to SN0011", "calibration 2015-05-10 (was 2014-05-07)",
                          "position moved 111 m", "deployment depth 2606 m to 2598 m"])

    def test_a_sourced_serial_whose_quote_is_not_in_its_chunk_stops_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, path = Path(tmp) / "data", Path(tmp) / "serials.json"
            (data / "Websites").mkdir(parents=True)
            (data / "Websites" / "chunks.jsonl").write_text(json.dumps({"chunk_id": "P", "text": "two transducers (SN136580 is designated P1)"}) + "\n")
            entry = {"id": "x", "quotes": [{"collection": "Websites", "chunk_id": "P", "text": "SN136580 is designated P1"}]}
            path.write_text(json.dumps({"entries": [entry]}))
            self.assertEqual(len(source_serials(path, data)), 1)
            entry["quotes"][0]["text"] = "SN136581 is designated P1"
            path.write_text(json.dumps({"entries": [entry]}))
            with self.assertRaises(ValueError):
                source_serials(path, data)


if __name__ == "__main__":
    unittest.main()
