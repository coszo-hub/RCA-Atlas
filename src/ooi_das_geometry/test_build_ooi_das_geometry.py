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
            (source / "multi_span_fiber_sensing_2026-03-31.html").write_text(
                '<div class="fl-post-content clearfix" itemprop="text"><p>Official <a href="https://doi.org/example">article</a>.</p><div class="wp-caption"><p>Map caption.</p></div></div><!-- .fl-post-content -->',
                encoding="utf-8",
            )
            manifest = build(source, output)
            self.assertEqual(manifest["counts"]["channel_locations"], 4)
            self.assertEqual(manifest["counts"]["figures"], 1)
            rows = [json.loads(line) for line in (output / "channel_locations.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["channel_id"], "OOI-RCA-OPTASENSE-NORTH-CHANNEL-00942")
            self.assertIn("not an asserted Silixa", rows[0]["applicability"])
            self.assertEqual(rows[-1]["depth_m"], -13.0)
            article = [json.loads(line) for line in (output / "chunks.jsonl").read_text().splitlines() if "Official OOI DAS25" in line]
            self.assertEqual(len(article), 1)
            self.assertIn("Official article (https://doi.org/example).", article[0]["text"])
            self.assertIn("https://doi.org/example", article[0]["text"])


if __name__ == "__main__":
    unittest.main()
