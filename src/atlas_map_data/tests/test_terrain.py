import tempfile
import unittest
from pathlib import Path

from atlas_map_data import terrain

FIX = Path(__file__).parent / "fixtures" / "tiny.asc"


class TerrainTest(unittest.TestCase):
    def setUp(self):
        self.g = terrain.read_esri_ascii(FIX, "tiny")

    def test_header_and_nodata(self):
        self.assertEqual((self.g.ncols, self.g.nrows), (3, 2))
        self.assertEqual(list(self.g.values), [-1000, -1100, -1200, -2000, -2100, -3000])

    def test_sample_at_cell_centers(self):
        # row 0 (north) cell centers are at lat 45.15; row 1 at 45.05
        self.assertAlmostEqual(self.g.sample(-129.95, 45.15), -1000)
        self.assertAlmostEqual(self.g.sample(-129.85, 45.05), -2100)

    def test_bilinear_between_centers(self):
        self.assertAlmostEqual(self.g.sample(-129.90, 45.15), -1050)

    def test_outside_is_none(self):
        self.assertIsNone(self.g.sample(-131.0, 45.1))

    def test_bin_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiny.bin"
            terrain.write_bin(self.g, p)
            self.assertEqual(p.stat().st_size, 12)
            back = terrain.read_bin(p, self.g.meta(), "tiny")
            self.assertEqual(list(back.values), list(self.g.values))

    def test_stack_prefers_first_grid_and_falls_back(self):
        s = terrain.Stack([self.g])
        self.assertAlmostEqual(s.elev(-129.95, 45.15), -1000)
        self.assertFalse(s.covered(-140.0, 45.0))
        self.assertEqual(s.elev(-140.0, 45.0), terrain.Stack.FALLBACK)

    def test_fetch_builds_gmrt_url_and_writes_file(self):
        seen = {}

        class Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(url, timeout):
            seen["url"] = url
            return Resp(FIX.read_bytes())

        with tempfile.TemporaryDirectory() as d:
            out = terrain.fetch_gmrt("axial", Path(d), urlopen=fake_urlopen)
            self.assertTrue(out.exists())
        self.assertIn("gmrt.org/services/GridServer", seen["url"])
        self.assertIn("format=esriascii", seen["url"])
        self.assertIn("resolution=high", seen["url"])
        self.assertIn("north=46.08", seen["url"])


if __name__ == "__main__":
    unittest.main()
