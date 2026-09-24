import gzip
import json
import tempfile
import unittest
from pathlib import Path

try:
    import h5py
    import numpy as np
    from atlas_map_data import auv_tiles
    HAVE = True
except ImportError:
    HAVE = False


def synthetic_grid(path: Path, nx=40, ny=30, cell=0.001):
    lon = -130.0 + cell / 2 + np.arange(nx) * cell
    lat = 45.9 + cell / 2 + np.arange(ny) * cell            # ascending, like the MBARI file
    z = (-1500.0 - 10 * np.arange(nx)[None, :] + 3 * np.arange(ny)[:, None]).astype(np.float32)
    with h5py.File(path, "w") as f:
        f["lon"], f["lat"], f["z"] = lon, lat, z
    return lon, lat, z


@unittest.skipUnless(HAVE, "needs h5py + numpy (requirements-auv.txt)")
class AuvTilesTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.src = Path(self.d.name) / "g.grd"
        self.lon, self.lat, self.z = synthetic_grid(self.src)

    def tearDown(self):
        self.d.cleanup()

    def build(self, sites):
        return auv_tiles.build(self.src, Path(self.d.name) / "out", sites, cells=8, levels=((0, 4), (1, 1)), l2_radius_km=0.3)

    def test_index_and_whole_extent_levels(self):
        ix = self.build([])
        self.assertEqual((ix["nx"], ix["ny"], ix["tileCells"]), (40, 30, 8))
        L0, L1 = ix["levels"]
        self.assertEqual((L0["tilesX"], L0["tilesY"]), (2, 1))        # 40/4=10 cols -> 2 tiles; 30/4=8 rows -> 1 tile
        self.assertEqual(len(L0["tiles"]), 2)
        self.assertEqual(L1["tiles"], [])                              # finest level only near sites
        self.assertAlmostEqual(ix["north"], 45.93)
        saved = json.loads((Path(self.d.name) / "out" / "index.json").read_text())
        self.assertEqual(saved["levels"][0]["stride"], 4)
        self.assertEqual(saved["credit"], auv_tiles.CREDIT)
        self.assertIn("ship-based multibeam", saved["credit"])      # the tiles include the ship-survey background

    def test_finest_level_only_near_sites(self):
        ix = self.build([(45.905, -129.995)])                          # south-west corner area
        L1 = ix["levels"][1]
        self.assertTrue(L1["tiles"])
        self.assertTrue(all(ty >= 2 and tx <= 1 for ty, tx in L1["tiles"]))   # rows are north-first

    def test_round_trip_north_first_and_pooled(self):
        ix = self.build([])
        data = (Path(self.d.name) / "out" / "L0" / "0_0.bin.gz").read_bytes()
        rows = auv_tiles.decode(data, 8, ix["zOffset"], ix["zScale"])
        self.assertEqual((len(rows), len(rows[0])), (9, 9))
        north_block = self.z[::-1][:4, :4].mean()                       # first pooled cell = mean of the NW 4x4 block
        self.assertAlmostEqual(rows[0][0], float(north_block), delta=0.05)
        self.assertLess(rows[1][0], rows[0][0])                        # moving south, z decreases in this grid

    def test_gzip_and_little_endian(self):
        self.build([])
        raw = gzip.decompress((Path(self.d.name) / "out" / "L0" / "0_0.bin.gz").read_bytes())
        self.assertEqual(len(raw), 9 * 9 * 2)


if __name__ == "__main__":
    unittest.main()
