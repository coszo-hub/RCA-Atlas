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


class FirstSpanTest(unittest.TestCase):
    south = [[-124.0 - i * 0.1, 45.0] for i in range(40)]   # ~315 km due west, a vertex every ~7.9 km

    def test_first_span_ends_where_the_2021_south_channels_end(self):
        conventional = [{"cable": "north", "coords": [[-124.0, 45.0], [-124.5, 45.1]]},
                        {"cable": "south", "coords": [[-124.0, 45.0], [-125.2, 45.01]]}]
        span = das.first_south_span(self.south, conventional)
        self.assertAlmostEqual(span[-1][0], -125.2, places=3)
        self.assertLess(das._km(span[0], span[-1]), 100)

    def test_without_the_2021_geometry_it_stops_at_95_km(self):
        span = das.first_south_span(self.south, [])
        self.assertAlmostEqual(sum(das._km(a, b) for a, b in zip(span, span[1:])), 95, delta=0.5)
