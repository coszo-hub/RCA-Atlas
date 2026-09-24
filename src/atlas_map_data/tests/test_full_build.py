"""Builds the real bundle from the restored corpus. Skipped when data/ or the terrain cache is absent."""
import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import build_atlas_bundle, paths

READY = (paths.DATA / "Instruments" / "instruments.jsonl").exists() and all(
    (paths.RUNTIME / "terrain" / f"{n}.asc").exists() for n in ("overview", "axial", "hydrate"))


@unittest.skipUnless(READY, "needs restored data/ and `build_atlas_bundle.py --refresh-terrain`")
class FullBuildTest(unittest.TestCase):
    def test_real_corpus_builds_and_reconciles(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            summary = build_atlas_bundle.build(out, paths.RUNTIME, paths.DATA)
            self.assertEqual(summary["errors"], [])
            self.assertEqual(summary["total"], 168)
            self.assertEqual(summary["located"], 155)
            self.assertTrue(summary["corpusSnapshot"])          # data/Instruments/manifest.json created_at
            bundle = json.loads((out / "sensors.json").read_text())
            by_id = {s["id"]: s for s in bundle["sensors"]}
            profiler = [s for s in bundle["sensors"] if s["siteCode"] == "RS03AXPS"][0]
            self.assertEqual((profiler["lat"], profiler["lon"]), (45.8168, -129.754))
            self.assertEqual(by_id["EARTHSCOPE-OO-AXCC1"]["family"], "seismic")
            sites = json.loads((out / "sites.json").read_text())["sites"]
            base = [t for t in sites if t["label"] == "Axial Base"]
            self.assertTrue(any(len(t["sensorIds"]) >= 30 for t in base))
            for name in ("overview", "axial", "hydrate"):
                self.assertTrue((out / "terrain" / f"{name}.bin").exists())
            cable = json.loads((out / "cable.json").read_text())
            self.assertEqual(len(cable["nodes"]), 7)


if __name__ == "__main__":
    unittest.main()
