import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import sensors

ROW = {
    "instrument_id": "INSTRUMENT-a", "canonical_id": "RS03AXPS-SF03A-2A-CTDPFA302",
    "name": "Axial Base Shallow Profiler CTD", "instrument_type": "ctd",
    "location": "Axial Seamount Base", "projects": ["Regional Cabled Array"], "coszo_role": None,
    "site": "RS03AXPS", "node": "SF03A", "instrument_code": "2A-CTDPFA302",
    "latitude": 45.9316, "longitude": -129.9808, "depth_m": 2607,
    "manufacturer": "Sea-Bird", "model": "SBE 16plus", "source_urls": ["https://example.org/a"],
    "arcada_document_id": "ARCADA-INSTRUMENT-x",
}


class SensorRecordTest(unittest.TestCase):
    def test_profiler_depths_come_from_node_not_water_depth(self):
        self.assertEqual(sensors.depth_range("SF03A", 2607), [5, 200])
        self.assertEqual(sensors.depth_range("PC03A", 2607), [200, 200])
        self.assertEqual(sensors.depth_range("DP03A", 2607), [250, 2457])
        self.assertIsNone(sensors.depth_range("MJ03B", 1542))
        self.assertIsNone(sensors.depth_range(None, 1542))

    def test_deep_profiler_without_water_depth_has_no_range(self):
        self.assertIsNone(sensors.depth_range("DP03A", None))

    def test_sensor_from_row(self):
        s = sensors.sensor_from_row(ROW)
        self.assertEqual(s["id"], "RS03AXPS-SF03A-2A-CTDPFA302")
        self.assertEqual(s["family"], "chemistry")
        self.assertEqual(s["refdes"], "RS03AXPS-SF03A-2A-CTDPFA302")
        self.assertEqual(s["depthRange"], [5, 200])
        self.assertEqual(s["depth"], 5)
        self.assertEqual(s["waterDepth"], 2607)
        self.assertEqual(s["sources"], ["https://example.org/a"])
        self.assertEqual(s["corrections"], [])

    def test_row_without_refdes_parts(self):
        row = dict(ROW, canonical_id="COSZO-BPR-O2B", site=None, node=None, instrument_code=None,
                   instrument_type="bottom_pressure_recorder", depth_m=None)
        s = sensors.sensor_from_row(row)
        self.assertIsNone(s["refdes"])
        self.assertIsNone(s["depth"])
        self.assertIsNone(s["depthRange"])

    def test_apply_position_correction(self):
        recs = [sensors.sensor_from_row(ROW)]
        unlocated = sensors.sensor_from_row(dict(ROW, canonical_id="RS03AXPS-PC03A-4B-CTDPFK301", latitude=None, longitude=None))
        recs.append(unlocated)
        fixes = [{"match": {"siteCode": ["RS03AXPS", "RS03AXPD"], "lat": [45.9316]}, "set": {"lat": 45.8168, "lon": -129.754},
                  "reason": "Inventory places the Axial Base profilers in the caldera."}]
        sensors.apply_corrections(recs, fixes)
        self.assertEqual((recs[0]["lat"], recs[0]["lon"]), (45.8168, -129.754))
        self.assertEqual(recs[0]["corrections"], ["Inventory places the Axial Base profilers in the caldera."])
        # a sensor with no recorded position is not given one by a position fix
        self.assertIsNone(unlocated["lat"])
        self.assertEqual(unlocated["corrections"], [])

    def test_correction_matching_nothing_is_reported(self):
        recs = [sensors.sensor_from_row(ROW)]
        with self.assertRaises(ValueError):
            sensors.apply_corrections(recs, [{"match": {"id": ["NOPE"]}, "set": {"lat": 1}, "reason": "x"}])

    def test_shipped_corrections_file_loads(self):
        fixes = sensors.load_corrections(Path(sensors.__file__).with_name("corrections.json"))
        self.assertTrue(any("RS03AXPS" in f["match"].get("siteCode", []) for f in fixes))


if __name__ == "__main__":
    unittest.main()
