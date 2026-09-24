import unittest

from atlas_map_data import validate


class FlatStack:
    FALLBACK = -2500.0
    def elev(self, lon, lat): return -1500.0
    def covered(self, lon, lat): return lon > -131


def sensor(id, depth=1500, rng=None, water=None, corrections=(), lat=45.9, lon=-130.0, site="s1"):
    return {"id": id, "lat": lat, "lon": lon, "depth": depth, "depthRange": rng, "waterDepth": water if water is not None else depth,
            "family": "chemistry", "site": site, "region": "axial", "corrections": list(corrections),
            "status": "OPERATIONAL", "access": []}


SITE = {"id": "s1", "sensorIds": ["a"], "unlocatedIds": []}


class ValidateTest(unittest.TestCase):
    def test_clean_bundle(self):
        self.assertEqual(validate.validate([sensor("a")], [SITE], [], 1, FlatStack()), [])

    def test_depth_mismatch_fails_without_correction(self):
        errs = validate.validate([sensor("a", depth=2607)], [SITE], [], 1, FlatStack())
        self.assertTrue(any("a" in e and "1,107 m" in e for e in errs), errs)

    def test_depth_mismatch_allowed_with_correction(self):
        self.assertEqual(validate.validate([sensor("a", depth=2607, corrections=["moved"])], [SITE], [], 1, FlatStack()), [])

    def test_profilers_are_checked_by_water_depth(self):
        s = sensor("a", depth=5, rng=[5, 200], water=2607)
        errs = validate.validate([s], [SITE], [], 1, FlatStack())
        self.assertEqual(len(errs), 1)

    def test_sensor_without_depth_is_not_depth_checked(self):
        self.assertEqual(validate.validate([sensor("a", depth=None, water=None)], [SITE], [], 1, FlatStack()), [])

    def test_counts_must_reconcile(self):
        errs = validate.validate([sensor("a")], [SITE], [], 2, FlatStack())
        self.assertTrue(any("reconcile" in e for e in errs))

    def test_sensor_outside_terrain_is_flagged(self):
        errs = validate.validate([sensor("a", lon=-140.0)], [SITE], [], 1, FlatStack())
        self.assertTrue(any("outside" in e for e in errs))

    def test_site_references_must_agree(self):
        errs = validate.validate([sensor("a", site="s2")], [SITE], [], 1, FlatStack())
        self.assertTrue(any("site" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
