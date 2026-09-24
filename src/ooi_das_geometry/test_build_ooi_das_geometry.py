import json
import tempfile
import unittest
from pathlib import Path

from build_ooi_das_geometry import build, parse_locations


class OoiDasGeometryTests(unittest.TestCase):
    def test_rejects_invalid_coordinates(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "north_DAS_latlondepth.txt"
            source.write_text("942 91 -124 10\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_locations(source, "north", "checksum")

    def test_builds_structured_channel_geometry_without_silixa_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "source", Path(temp) / "output"
            source.mkdir()
            (source / "north_DAS_latlondepth.txt").write_text("942 45.2 -123.9 -10\n944 45.3 -124.0 -11\n", encoding="utf-8")
            (source / "south_DAS_latlondepth.txt").write_text("942 45.1 -124.1 -12\n944 45.0 -124.2 -13\n", encoding="utf-8")
            (source / "readme.pdf").write_bytes(b"test documentation")
            manifest = build(source, output)
            self.assertEqual(manifest["counts"]["channel_locations"], 4)
            rows = [json.loads(line) for line in (output / "channel_locations.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["channel_id"], "OOI-RCA-OPTASENSE-NORTH-CHANNEL-00942")
            self.assertIn("not an asserted Silixa", rows[0]["applicability"])
            self.assertEqual(rows[-1]["depth_m"], -13.0)


if __name__ == "__main__":
    unittest.main()
