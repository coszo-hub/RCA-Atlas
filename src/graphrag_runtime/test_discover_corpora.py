#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discover_corpora import COLLECTION_NAMES, build_catalog, write_catalog


class CorpusCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[2]
        cls.catalog = build_catalog(cls.project_root, generated_at="2026-09-19T00:00:00Z")

    def test_discovers_every_collection_manifest(self) -> None:
        ids = {row["collection_id"] for row in self.catalog["collections"]}
        expected = {value[0] for value in COLLECTION_NAMES.values()}
        self.assertEqual(ids, expected)
        self.assertEqual(self.catalog["totals"]["collections"], 13)

    def test_rca_information_has_a_friendly_display_name(self) -> None:
        collection = next(row for row in self.catalog["collections"] if row["collection_id"] == "arcada")
        self.assertEqual(collection["name"], "RCA Information")

    def test_every_collection_has_valid_embedding_input(self) -> None:
        for collection in self.catalog["collections"]:
            self.assertEqual(len(collection["embedding_inputs"]), 1, collection["collection_id"])
            item = collection["embedding_inputs"][0]
            self.assertGreater(item["records"], 0)
            self.assertEqual(item["records"], item["text_records"])
            self.assertEqual(len(item["sha256"]), 64)
            self.assertTrue(item["path"].endswith("chunks.jsonl"))
            self.assertNotIn("visual_chunks.jsonl", item["path"])

    def test_graph_and_structured_inputs_are_separate(self) -> None:
        for collection in self.catalog["collections"]:
            nodes = {row["path"] for row in collection["graph_node_inputs"]}
            edges = {row["path"] for row in collection["graph_edge_inputs"]}
            structured = {row["path"] for row in collection["structured_inputs"]}
            auxiliary = {row["path"] for row in collection["auxiliary_inputs"]}
            self.assertFalse(edges & structured)
            self.assertFalse(nodes & structured)
            self.assertFalse(auxiliary & {row["path"] for row in collection["embedding_inputs"]})
            self.assertTrue(any(path.endswith("chunks.jsonl") for path in nodes))

    def test_fingerprint_is_independent_of_catalog_timestamp(self) -> None:
        second = build_catalog(self.project_root, generated_at="2030-01-01T00:00:00Z")
        self.assertEqual(self.catalog["build_fingerprint_sha256"], second["build_fingerprint_sha256"])

    def test_catalog_writes_as_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "corpus_catalog.json"
            written = write_catalog(self.project_root, output)
            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(loaded["build_fingerprint_sha256"], written["build_fingerprint_sha256"])
            self.assertTrue(loaded["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
