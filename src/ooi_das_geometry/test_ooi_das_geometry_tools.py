import json
import tempfile
import unittest
from pathlib import Path

from ooi_das_geometry_tools import OoiDasGeometryToolkit, dispatch


class OoiDasGeometryToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        rows = [
            {"cable": "north", "channel_number": 10, "latitude": 45.0, "longitude": -125.0, "source_url": "https://example/n", "source_file_sha256": "n"},
            {"cable": "north", "channel_number": 12, "latitude": 45.1, "longitude": -125.1, "source_url": "https://example/n", "source_file_sha256": "n"},
        ]
        (root / "channel_locations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        coverage = {"cable": "north", "saved_unmasked_intervals_m": [{"start_m": 0, "end_m": 10}], "source_url": "https://example/file"}
        (root / "multidas_unmasked_coverage.jsonl").write_text(json.dumps(coverage) + "\n")
        self.toolkit = OoiDasGeometryToolkit(root)

    def tearDown(self): self.temp.cleanup()

    def test_channel_and_nearest_lookup(self):
        result = dispatch(self.toolkit, "ooi_das_channel_location", {"cable": "north", "channel_number": 10})
        self.assertTrue(result["ok"])
        self.assertEqual(result["location"]["latitude"], 45.0)
        nearest = self.toolkit.nearest_channel("north", 45.09, -125.09)
        self.assertEqual(nearest["location"]["channel_number"], 12)

    def test_mask_lookup_is_explicitly_file_specific(self):
        result = self.toolkit.multidas_unmasked_spans("north")
        self.assertTrue(result["ok"])
        self.assertIn("file-specific", result["warning"])


if __name__ == "__main__": unittest.main()
