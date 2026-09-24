import math
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from atlas_map_data import subsurface
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "needs numpy + scipy (requirements-subsurface.txt)")
class SubsurfaceTest(unittest.TestCase):
    def test_local_frame_round_trips(self):
        lon, lat = subsurface.to_ll(*subsurface.to_xy(45.97, -129.99))
        self.assertAlmostEqual(float(lon), -129.99, places=9)
        self.assertAlmostEqual(float(lat), 45.97, places=9)
        self.assertEqual(tuple(map(float, subsurface.to_xy(subsurface.LAT0, subsurface.LON0))), (0.0, 0.0))

    def test_utm_central_meridian(self):
        lat, lon = subsurface.utm_to_ll(np.array([500000.0]), np.array([5087000.0]), zone=9)
        self.assertAlmostEqual(float(lon[0]), -129.0, places=9)
        self.assertTrue(45.9 < float(lat[0]) < 46.0)

    def test_surface_masks_and_undoes_the_datum(self):
        X = np.array([[0.0, 1.0], [0.0, 1.0]])
        Y = np.array([[0.0, 0.0], [1.0, 1.0]])
        Z = np.array([[-1.0, np.nan], [0.0, -0.5]])
        s = subsurface._surface("t", "Test", X, Y, Z)
        self.assertEqual((s["rows"], s["cols"]), (2, 2))
        self.assertIsNone(s["points"][1])
        self.assertEqual(s["points"][0], [subsurface.LON0, subsurface.LAT0, -2500.0])   # 1 km below the 1,500 m datum
        self.assertEqual(s["points"][2][2], -1500.0)
        self.assertTrue(math.isclose(s["points"][3][1], subsurface.LAT0 + 1 / subsurface.XLT, abs_tol=1e-6))

    def test_rim_parses_the_matlab_block(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "axial_calderaRim.m").write_text("% rim\ncalderaRim = [-130.0047,45.9207\n-130.0104,45.9238];\n")
            self.assertEqual(subsurface.rim(Path(d)), [[-130.0047, 45.9207], [-130.0104, 45.9238]])


if __name__ == "__main__":
    unittest.main()
