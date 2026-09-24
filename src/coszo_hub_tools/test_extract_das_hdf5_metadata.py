import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import extract_das_hdf5_metadata as extractor


class DasHdf5MetadataTests(unittest.TestCase):
    def test_extracts_along_fiber_extent_without_inventing_locations(self):
        values = {
            "/cableSpec/sensorDistances": [0.0, 10.0, 20.0],
            "/cableSpec/cableLengths": [100.0],
            "/cableSpec/cables": [7.0],
            "/cableSpec/positions/eastings": [1022.0],
            "/cableSpec/positions/northings": [6321.0],
            "/cableSpec/positions/depths": [0.0],
        }
        with tempfile.NamedTemporaryFile(suffix=".hdf5") as stream, \
             patch.object(extractor, "_numbers", side_effect=lambda _path, key: values.get(key)), \
             patch.object(extractor, "_text", return_value="WGS84"):
            record = extractor.extract_file(Path(stream.name), "https://example.org/rca.hdf5")
        self.assertEqual(record["sensor_count"], 3)
        self.assertEqual(record["sensor_distance_end_m"], 20.0)
        self.assertEqual(record["sensor_spacing_median_m"], 10.0)
        self.assertEqual(record["cable_ids"], [7])
        self.assertFalse(record["georeferenced_channel_positions"])
        self.assertEqual(record["channel_locations"], [])

    def test_retains_per_channel_wgs84_locations_only_when_complete(self):
        values = {
            "/cableSpec/sensorDistances": [0.0, 10.0],
            "/cableSpec/cableLengths": [10.0],
            "/cableSpec/cables": [2.0],
            "/cableSpec/positions/eastings": [-130.0, -130.1],
            "/cableSpec/positions/northings": [45.0, 45.1],
            "/cableSpec/positions/depths": [100.0, 101.0],
        }
        with tempfile.NamedTemporaryFile(suffix=".hdf5") as stream, \
             patch.object(extractor, "_numbers", side_effect=lambda _path, key: values.get(key)), \
             patch.object(extractor, "_text", return_value="WGS84"):
            record = extractor.extract_file(Path(stream.name))
        self.assertTrue(record["georeferenced_channel_positions"])
        self.assertEqual(record["channel_locations"][1]["longitude"], -130.1)
        self.assertEqual(record["channel_locations"][1]["depth_m"], 101.0)


if __name__ == "__main__":
    unittest.main()
