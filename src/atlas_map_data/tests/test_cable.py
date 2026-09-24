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

    def test_lines_split_kind_and_route(self):
        north = [l for l in self.c["lines"] if l["route"].startswith("Pacific City landfall") and l["kind"] == "North backbone"]
        self.assertEqual(len(north), 1)
        self.assertEqual(north[0]["accuracy"], "charted")
        self.assertIn("→", north[0]["route"])

    def test_approximate_segments_reach_axial(self):
        approx = [l for l in self.c["lines"] if l["accuracy"] == "approximate"]
        self.assertEqual(len(approx), 2)
        self.assertTrue(all(l["kind"] == "North backbone" for l in approx))

    def test_primary_nodes(self):
        codes = sorted(n["code"] for n in self.c["nodes"])
        self.assertEqual(codes, ["PN1A", "PN1B", "PN1C", "PN1D", "PN3A", "PN3B", "PN5A"])
        pn5a = [n for n in self.c["nodes"] if n["code"] == "PN5A"][0]
        self.assertIn("placeholder", pn5a["description"].lower())
        pn3a = [n for n in self.c["nodes"] if n["code"] == "PN3A"][0]
        self.assertEqual(pn3a["name"], "PN3A (Axial Base)")


if __name__ == "__main__":
    unittest.main()
