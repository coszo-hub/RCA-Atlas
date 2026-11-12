import unittest

from atlas_map_data import axial_unrest

CATALOG = """yyyymmdd HHMMSSS.SS Lat(D M)  Lon(D M)  Depth    MW NWR GAP DMIN  RMS  ERH  ERZ            ID         PMom    SMom
20150122 0000 27.54 45 56.81 129 59.92   0.55  -0.31  7 206  1.2 0.03  0.8  0.4         20830      3.8e+17 3.9e+17
20150123 0130 00.00 45 57.00 130  0.60   1.20   0.50  9 150  0.9 0.02  0.5  0.6         20831      1.9e+18 7.8e+17
not a row
"""

DAYDEPTH = """Dataset {
} x;
---------------------------------------------
time[3]
3630700800.0, 3630787200.0, 3630873600.0

botsflu_daydepth[3]
-1509.8, -9999999.0, -1512.2
"""


class AxialUnrestTest(unittest.TestCase):
    def test_reads_catalog_rows_west_longitudes_negative(self):
        c = axial_unrest.parse_catalog(CATALOG)
        self.assertEqual(c.shape, (2, 8))
        self.assertAlmostEqual(c[0, 0], 27.54 / 86400, 6)        # days after 22 January 2015
        self.assertAlmostEqual(c[0, 1], 45 + 56.81 / 60, 6)
        self.assertAlmostEqual(c[0, 2], -(129 + 59.92 / 60), 6)
        self.assertAlmostEqual(c[1, 2], -(130 + 0.60 / 60), 6)
        self.assertEqual(list(c[1, 3:]), [1.2, 0.5, 0.5, 0.6, 20831])   # depth, Mw, ERH, ERZ, catalog ID

    def test_reads_daily_depths_dropping_fill_values(self):
        d = axial_unrest.parse_daydepth(DAYDEPTH)
        self.assertEqual(d, {"2015-01-20": -1509.8, "2015-01-22": -1512.2})

    def test_months_span_the_catalog(self):
        from datetime import datetime
        self.assertEqual(axial_unrest.months_between(datetime(2015, 11, 3), datetime(2016, 2, 1)),
                         ["2015-11", "2015-12", "2016-01", "2016-02"])


class FocalMatchTest(unittest.TestCase):
    def test_matches_mechanisms_by_time_and_place(self):
        import numpy as np
        timed = np.array([[10.0, 45.95, -130.0, 1], [20.0, 45.95, -130.0, 3]])
        events = np.array([[10.0 + 0.5 / 86400, 45.951, -130.0],    # half a second, 110 m: normal
                           [20.0 + 5 / 86400, 45.95, -130.0],       # five seconds off: none
                           [10.0, 46.10, -130.0],                   # 17 km off: none
                           [30.0, 45.95, -130.0]])                  # after them all: none
        self.assertEqual(list(axial_unrest.match_by_time(events, timed)), [1, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
