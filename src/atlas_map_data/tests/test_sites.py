import unittest

from atlas_map_data import sites


def s(id, lat, lon, loc="Axial Seamount Base", node="MJ03A", depth=2607, rng=None, code="RS03AXBS"):
    return {"id": id, "lat": lat, "lon": lon, "location": loc, "node": node, "depth": depth,
            "depthRange": rng, "siteCode": code, "family": "chemistry", "status": "OPERATIONAL"}


FLAT = lambda lon, lat: -2614.0


class SitesTest(unittest.TestCase):
    def test_colocated_platforms_merge_into_one_site_named_for_the_seafloor(self):
        located = [
            s("base-ctd", 45.8168, -129.754),
            s("sp-ctd", 45.8168, -129.754, loc="Axial Seamount Profiler", node="SF03A", depth=5, rng=[5, 200], code="RS03AXPS"),
            s("dp-ctd", 45.81685, -129.75405, loc="Axial Seamount Deep Profiler", node="DP03A", depth=250, rng=[250, 2457], code="RS03AXPD"),
        ]
        result, unplaced = sites.build_sites(located, [], FLAT)
        self.assertEqual(len(result), 1)
        site = result[0]
        self.assertEqual(site["name"], "Axial Seamount Base")
        self.assertEqual(site["label"], "Axial Base")
        self.assertEqual(site["region"], "axial")
        self.assertEqual(site["seafloor"], 2614)
        self.assertEqual(set(site["sensorIds"]), {"base-ctd", "sp-ctd", "dp-ctd"})
        self.assertEqual(site["parts"], ["Axial Seamount Base", "Axial Seamount Profiler", "Axial Seamount Deep Profiler"])
        self.assertEqual(site["column"], [{"kind": "Shallow profiler", "a": 5, "b": 200},
                                          {"kind": "Deep profiler", "a": 250, "b": 2457}])
        self.assertTrue(all(x["site"] == site["id"] for x in located))

    def test_sensors_150m_apart_are_separate_sites(self):
        a, b = s("a", 45.9, -130.0), s("b", 45.9, -130.0 + 0.0025)   # ~195 m east
        result, _ = sites.build_sites([a, b], [], FLAT)
        self.assertEqual(len(result), 2)

    def test_grouping_is_transitive_through_a_bridging_sensor(self):
        # A and C are 250 m apart; B is 125 m east of A and 50 m north (~135 m from each).
        # B sorts last (highest lat), so a single greedy pass would leave A and C split.
        dlon = 0.125 / sites.KX
        a, c = s("a", 45.9, -130.0), s("c", 45.9, -130.0 + 2 * dlon)
        b = s("b", 45.9 + 0.05 / sites.KZ, -130.0 + dlon)
        result, _ = sites.build_sites([a, b, c], [], FLAT)
        self.assertEqual(len(result), 1)
        self.assertEqual(sorted(result[0]["sensorIds"]), ["a", "b", "c"])

    def test_repeated_labels_get_a_distinguishing_token(self):
        dlat = 1.0 / sites.KZ                      # 1 km apart: four separate sites, all "Summit"
        located = [
            s("EARTHSCOPE-OO-HYS13", 44.56, -125.15, loc="Summit", node=None, code=None),
            s("ctd", 44.56 + dlat, -125.15, loc="Summit", node="MJ01B", code="RS01SUM2"),
            s("pi-cam", 44.56 + dlat, -125.15, loc="Summit", node=None, code=None),
            s("strain-ew", 44.56 + 2 * dlat, -125.15, loc="Summit", node=None, code=None),
            s("strain-ns", 44.56 + 3 * dlat, -125.15, loc="Summit", node=None, code=None),
            s("lonely", 45.9, -130.0, loc="Elsewhere"),
        ]
        result, _ = sites.build_sites(located, [], FLAT)
        labels = sorted(t["label"] for t in result)
        self.assertEqual(labels, ["Elsewhere", "Summit · 3", "Summit · 4", "Summit · HYS13", "Summit · MJ01B"])
        self.assertTrue(all(t["name"] in ("Summit", "Elsewhere") for t in result))
        self.assertEqual(sorted(t["id"] for t in result),
                         ["elsewhere", "summit", "summit-2", "summit-3", "summit-4"])

    def test_labels_distinguish_by_site_code_and_colliding_tokens_by_ordinal(self):
        dlat = 1.0 / sites.KZ
        located = [s("a", 45.9, -130.0, loc="Vent", node=None, code="RS03INT1"),
                   s("b", 45.9 + dlat, -130.0, loc="Vent", node="MJ03D", code="RS03INT2"),
                   s("c", 45.9 + 2 * dlat, -130.0, loc="Vent", node="MJ03D", code="RS03INT2")]
        result, _ = sites.build_sites(located, [], FLAT)
        self.assertEqual([t["label"] for t in result], ["Vent · RS03INT1", "Vent · MJ03D 2", "Vent · MJ03D 3"])

    def test_regions_by_longitude(self):
        self.assertEqual(sites.region_for(-130.0), "axial")
        self.assertEqual(sites.region_for(-125.39), "slope")
        self.assertEqual(sites.region_for(-125.15), "hydrate")
        self.assertEqual(sites.region_for(-124.3), "shelf")

    def test_sensor_without_depth_still_gets_a_site(self):
        result, _ = sites.build_sites([s("nodepth", 44.6, -124.3, loc="Oregon Shelf", depth=None, code=None)], [], FLAT)
        self.assertEqual(result[0]["seafloor"], 2614)
        self.assertEqual(result[0]["column"], [])

    def test_unlocated_sensors_attach_by_site_code_or_location(self):
        located = [s("a", 45.9, -130.0, loc="Axial Seamount Base", code="RS03AXBS")]
        by_code = s("u1", None, None, loc="somewhere", code="RS03AXBS")
        by_loc = s("u2", None, None, loc="Axial Seamount Base", code=None)
        orphan = s("u3", None, None, loc="Nowhere Ridge", code="RS09XXXX")
        result, unplaced = sites.build_sites(located, [by_code, by_loc, orphan], FLAT)
        self.assertEqual(result[0]["unlocatedIds"], ["u1", "u2"])
        self.assertEqual([u["id"] for u in unplaced], ["u3"])

    def test_unlocated_site_code_match_beats_earlier_location_match(self):
        site_a = s("a", 45.80, -130.0, loc="Alpha", code="RS01AAAA")
        site_b = s("b", 45.95, -130.0, loc="Beta", code="RS02BBBB")
        u = s("u", None, None, loc="Alpha", code="RS02BBBB")
        result, unplaced = sites.build_sites([site_a, site_b], [u], FLAT)
        by_name = {t["name"]: t for t in result}
        self.assertEqual(by_name["Alpha"]["unlocatedIds"], [])
        self.assertEqual(by_name["Beta"]["unlocatedIds"], ["u"])
        self.assertEqual(u["site"], by_name["Beta"]["id"])


if __name__ == "__main__":
    unittest.main()
