import unittest

from atlas_map_data import das


class DasTest(unittest.TestCase):
    def test_slice_keeps_interval_endpoints(self):
        coords = [[-124.0, 45.0], [-125.0, 45.0], [-126.0, 45.0]]
        result = das._slice_by_distance(coords, 25_000, 75_000)
        self.assertGreaterEqual(len(result), 2)
        km_per_degree = das._km(coords[0], coords[1])
        self.assertAlmostEqual(result[0][0], -124.0 - 25 / km_per_degree, places=3)
        self.assertAlmostEqual(result[-1][0], -124.0 - 75 / km_per_degree, places=3)
