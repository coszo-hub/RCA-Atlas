import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import faults


def line(fid, name, slip, coords, linetype="Well Constrained"):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"fault_name": name, "fault_id": fid, "section_name": "", "age": "latest Quaternary",
                           "slip_sense": slip, "slip_rate": "Greater than 5.0 mm/yr", "linetype": linetype,
                           "dip_direction": "", "mapped_scale": "1:250,000", "fault_url": f"https://earthquake.usgs.gov/{fid}"}}


# The terrain covers lon -126..-124; east of -124.5 is land.
covered = lambda x, y: -126 <= x <= -124
elev = lambda x, y: 100.0 if x > -124.5 else -2000.0


class FaultsTest(unittest.TestCase):
    def build(self, features):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "q.geojson"
            p.write_text(json.dumps({"features": features}))
            return faults.load_faults(p, covered, elev)

    def test_offshore_faults_kept_folds_belt_and_onshore_dropped(self):
        out = self.build([
            line("798", "Daisy Bank fault", "Left lateral", [[-125.5, 44.6], [-125.0, 44.8]], "Moderately Constrained"),
            line("786", "Stonewall anticline", "Anticline", [[-125.0, 44.6], [-125.0, 45.0]]),
            line("784", "Cascadia fold and fault belt", "Thrust", [[-125.2, 44.6], [-125.1, 44.7]]),
            line("881", "Tillamook Bay fault zone", "Reverse", [[-124.4, 45.5], [-124.3, 45.6]]),
            line("781", "Cascadia megathrust", "Thrust", [[-127.0, 44.0], [-125.3, 44.5], [-125.2, 44.9]]),
        ])
        self.assertEqual([f["name"] for f in out["faults"]], ["Cascadia megathrust", "Daisy Bank fault"])
        mega, daisy = out["faults"]
        self.assertTrue(mega["megathrust"])
        self.assertIn("deformation front", mega["note"])
        self.assertEqual(mega["lines"][0]["coords"], [[-125.3, 44.5], [-125.2, 44.9]])   # cut to the terrain
        self.assertFalse(daisy["lines"][0]["constrained"])
        self.assertEqual(out["dropped"], ["Cascadia fold and fault belt"])

    def test_unnamed_faults_sort_last_and_are_capitalised(self):
        out = self.build([line("785", "unnamed offshore faults", "Left lateral", [[-125.5, 44.0], [-125.4, 44.1]]),
                          line("797", "Alvin Canyon fault", "Left lateral", [[-125.4, 44.4], [-125.0, 44.6]])])
        self.assertEqual([f["name"] for f in out["faults"]], ["Alvin Canyon fault", "Unnamed offshore faults"])

    def test_committed_source_has_the_named_offshore_faults(self):
        names = {f["properties"]["fault_name"] for f in json.loads(faults.SOURCE.read_text())["features"]}
        self.assertTrue({"Daisy Bank fault", "Alvin Canyon fault", "Cascadia megathrust", "Nehalem Bank fault"} <= names)
