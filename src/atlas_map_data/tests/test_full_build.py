"""Builds the real bundle from the restored corpus. Skipped when data/ or the terrain cache is absent."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from atlas_map_data import build_atlas_bundle, paths, status

READY = (paths.DATA / "Instruments" / "instruments.jsonl").exists() and all(
    (paths.RUNTIME / "terrain" / f"{n}.asc").exists() for n in ("overview", "axial", "hydrate"))


@unittest.skipUnless(READY, "needs restored data/ and `build_atlas_bundle.py --refresh-terrain`")
class FullBuildTest(unittest.TestCase):
    def test_real_corpus_builds_and_reconciles(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            summary = build_atlas_bundle.build(out, paths.RUNTIME, paths.DATA)
            self.assertEqual(summary["errors"], [])
            self.assertEqual(summary["total"], 171)
            self.assertEqual(summary["located"], 155)
            self.assertEqual(summary["unlocated"], 16)
            self.assertEqual(summary["unplaced"], 5)
            self.assertEqual(summary["sites"], 31)
            self.assertTrue(summary["corpusSnapshot"])          # data/Instruments/manifest.json created_at
            bundle = json.loads((out / "sensors.json").read_text())
            by_id = {s["id"]: s for s in bundle["sensors"]}
            profiler = [s for s in bundle["sensors"] if s["siteCode"] == "RS03AXPS"][0]
            self.assertEqual((profiler["lat"], profiler["lon"]), (45.8168, -129.754))
            self.assertEqual(by_id["EARTHSCOPE-OO-AXCC1"]["family"], "seismic")
            self.assertEqual(by_id["FETCH-2504"]["family"], "acoustic")
            self.assertEqual(len(by_id["FETCH-2504"]["access"]), 2)
            for das in ("PI-DAS24", "PI-DAS25", "PI-DAS-OPTASENSE"):   # placeholder 45.0, -128.0 cleared
                self.assertIsNone(by_id[das]["lat"])
                self.assertIsNone(by_id[das]["lon"])
                self.assertIn(das, bundle["unplaced"])
            self.assertFalse(any(s["lat"] == 45.0 and s["lon"] == -128.0 for s in bundle["sensors"]))
            pi = [r for s in bundle["sensors"] for r in s["access"] if r["kind"] == "pi_portal"]
            self.assertTrue(pi and all(r["endpointId"].startswith("PI-PORTAL-ENDPOINT-") for r in pi))
            sites = json.loads((out / "sites.json").read_text())["sites"]
            labels = [t["label"] for t in sites]
            self.assertEqual(len(labels), len(set(labels)))
            base = [t for t in sites if t["name"] == "Axial Seamount Base"]
            self.assertTrue(any(len(t["sensorIds"]) >= 30 for t in base))
            self.assertIn("Southern Hydrate Ridge Summit · HYS13", labels)
            for name in ("overview", "axial", "hydrate"):
                self.assertTrue((out / "terrain" / f"{name}.bin").exists())
            cable = json.loads((out / "cable.json").read_text())
            self.assertEqual(len(cable["nodes"]), 7)

    def test_unrecognised_nereus_status_is_a_validation_error(self):
        real = status.resolve

        def resolve(record, index):
            hit = real(record, index)
            return dict(hit, status="HIBERNATING") if record["id"] == "EARTHSCOPE-OO-AXCC1" else hit

        with tempfile.TemporaryDirectory() as d, mock.patch.object(status, "resolve", resolve):
            summary = build_atlas_bundle.build(Path(d), paths.RUNTIME, paths.DATA)
            self.assertFalse((Path(d) / "sensors.json").exists())
        self.assertEqual(summary["errors"],
                         ["EARTHSCOPE-OO-AXCC1: unrecognised Nereus status 'HIBERNATING'; add it to status.STATUS_GROUP"])


if __name__ == "__main__":
    unittest.main()
