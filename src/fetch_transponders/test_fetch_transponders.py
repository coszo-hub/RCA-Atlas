#!/usr/bin/env python3
"""Contract checks for the source-backed Axial FETCH collection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_fetch_corpus import DEFAULT_SOURCE, build


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class FetchCorpusTest(unittest.TestCase):
    def test_builds_three_transponders_and_six_directed_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "FETCH"
            build(DEFAULT_SOURCE, output)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            instruments = jsonl(output / "instruments.jsonl")
            relationships = jsonl(output / "relationships.jsonl")
            self.assertEqual(manifest["validation_status"], "pass")
            self.assertEqual({row["station_identifier"] for row in instruments}, {"2502", "2503", "2504"})
            self.assertEqual(sum(row["predicate"] == "RANGES_TO" for row in relationships), 6)
            self.assertTrue(all("depth_m" not in row and row.get("manufacturer") is None for row in instruments))

    def test_evidence_prevents_generic_acoustic_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "FETCH"
            build(DEFAULT_SOURCE, output)
            evidence = " ".join(row["text"] for row in jsonl(output / "chunks.jsonl"))
            self.assertIn("not a generic hydrophone, DAS, or ambient-noise interferometry dataset", evidence)
            self.assertIn("calibrated inter-station baseline distances", evidence)


if __name__ == "__main__":
    unittest.main()
