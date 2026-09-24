import unittest
from pathlib import Path

from atlas_map_data import cable

GEOJSON = Path(cable.__file__).with_name("cable") / "rca_cable.geojson"


class CableTest(unittest.TestCase):
    def setUp(self):
        self.c = cable.load_cable(GEOJSON)

    def test_undocumented_segments_are_left_off(self):
        names = [l["name"] for l in self.c["lines"]]
        self.assertFalse(any(n.startswith("Unidentified") for n in names))
        self.assertFalse(any("path B" in n for n in names))
        self.assertEqual(self.c["hidden"], 5)

    def test_line_kinds_are_the_four_legend_groups(self):
        kinds = {l["kind"] for l in self.c["lines"]}
        self.assertEqual(kinds, {"North backbone", "South backbone", "Extension", "Spur", "Secondary cable"})
        pn5a = [l for l in self.c["lines"] if "path A" in l["route"]]
        self.assertEqual([(l["kind"], l["route"]) for l in pn5a], [("North backbone", "near PN5A (path A)")])

    def test_lines_split_kind_and_route(self):
        north = [l for l in self.c["lines"] if l["route"].startswith("Pacific City landfall") and l["kind"] == "North backbone"]
        self.assertEqual(len(north), 1)
        self.assertEqual(north[0]["accuracy"], "charted")
        self.assertIn("→", north[0]["route"])

    def test_mapped_route_reaches_axial_and_nothing_is_straight_lined(self):
        self.assertEqual([l for l in self.c["lines"] if l["accuracy"] == "approximate"], [])
        north = [l for l in self.c["lines"] if l["accuracy"] == "mapped" and l["kind"] == "North backbone"]
        self.assertEqual([l["route"] for l in north], ["US EEZ limit → PN3A (Axial Base)", "PN3A (Axial Base) → PN3B (Axial Caldera)"])
        self.assertGreater(len(north[0]["coords"]), 20)   # the mapped route, not a two-point straight line
        pn3b = [n for n in self.c["nodes"] if n["code"] == "PN3B"][0]
        self.assertLess(abs(north[1]["coords"][-1][0] - pn3b["lon"]) + abs(north[1]["coords"][-1][1] - pn3b["lat"]), 1e-4)
        secondary = [l for l in self.c["lines"] if l["kind"] == "Secondary cable"]
        self.assertTrue(secondary and all(l["accuracy"] == "mapped" for l in secondary))

    def test_primary_nodes(self):
        codes = sorted(n["code"] for n in self.c["nodes"])
        self.assertEqual(codes, ["PN1A", "PN1B", "PN1C", "PN1D", "PN3A", "PN3B", "PN5A"])
        pn5a = [n for n in self.c["nodes"] if n["code"] == "PN5A"][0]
        self.assertIn("placeholder", pn5a["description"].lower())
        pn3a = [n for n in self.c["nodes"] if n["code"] == "PN3A"][0]
        self.assertEqual(pn3a["name"], "PN3A (Axial Base)")


if __name__ == "__main__":
    unittest.main()
