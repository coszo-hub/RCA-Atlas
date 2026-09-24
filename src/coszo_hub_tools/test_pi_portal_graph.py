#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from build_pi_portal_graph import (
    EXPECTED_DATASET_KEYS,
    GRAPH_FILES,
    PI_INSTRUMENTS,
    PI_PORTAL_TOOL_SCHEMAS,
    PORTAL_HOST,
    PREFERRED_SHARED_INSTRUMENT_IDS,
    ROUTING_POLICY_ID,
    build,
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class PIPortalGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "corpus"
        self.manifest = build(self.output)
        self.instruments = read_jsonl(self.output / "instruments.jsonl")
        self.endpoints = read_jsonl(self.output / "endpoints.jsonl")
        self.sites = read_jsonl(self.output / "sites.jsonl")
        self.sources = read_jsonl(self.output / "sources.jsonl")
        self.tools = read_jsonl(self.output / "tools.jsonl")
        self.entities = read_jsonl(self.output / "entities.jsonl")
        self.relationships = read_jsonl(self.output / "relationships.jsonl")
        self.chunks = read_jsonl(self.output / "chunks.jsonl")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_required_outputs_and_exact_scope(self) -> None:
        for filename in (*GRAPH_FILES, "manifest.json", "README.md"):
            self.assertTrue((self.output / filename).is_file(), filename)
        self.assertEqual(set(PI_INSTRUMENTS), EXPECTED_DATASET_KEYS)
        self.assertEqual(len(self.instruments), 10)
        self.assertEqual({row["portal_instrument_key"] for row in self.instruments}, EXPECTED_DATASET_KEYS)
        self.assertEqual(len(self.endpoints), sum(len(value["endpoints"]) for value in PI_INSTRUMENTS.values()))
        self.assertEqual(self.manifest["instrument_count"], 10)
        self.assertEqual(self.manifest["endpoint_count"], len(self.endpoints))

    def test_known_shared_instrument_and_site_ids_are_reused(self) -> None:
        by_key = {row["portal_instrument_key"]: row for row in self.instruments}
        for key, shared_id in PREFERRED_SHARED_INSTRUMENT_IDS.items():
            self.assertEqual(by_key[key]["instrument_id"], shared_id)
            self.assertTrue(by_key[key]["shared_instrument_id_reused"])
        self.assertEqual(len(PREFERRED_SHARED_INSTRUMENT_IDS), 10)
        self.assertTrue(all(row["site_id"].startswith("ENTITY-") for row in self.sites))

        # Stable audited crosswalk IDs survive an older local corpus snapshot.
        old_corpus = Path(self.temp.name) / "old-instruments.jsonl"
        old_corpus.write_text("", encoding="utf-8")
        older_output = Path(self.temp.name) / "older-corpus-build"
        build(older_output, old_corpus)
        older = {row["portal_instrument_key"]: row for row in read_jsonl(older_output / "instruments.jsonl")}
        for key, shared_id in PREFERRED_SHARED_INSTRUMENT_IDS.items():
            self.assertEqual(older[key]["instrument_id"], shared_id)

    def test_instrument_download_and_site_edges_are_first_class(self) -> None:
        triples = {(row["source_id"], row["predicate"], row["target_id"]) for row in self.relationships}
        endpoint_by_id = {row["endpoint_id"]: row for row in self.endpoints}
        for instrument in self.instruments:
            for endpoint_id in instrument["endpoint_ids"]:
                self.assertIn((instrument["instrument_id"], "DOWNLOADABLE_FROM", endpoint_id), triples)
                self.assertEqual(endpoint_by_id[endpoint_id]["instrument_id"], instrument["instrument_id"])
            self.assertIn((instrument["instrument_id"], "LOCATED_AT", instrument["site_id"]), triples)

    def test_instrument_chunks_open_with_complete_routing(self) -> None:
        chunk_by_parent = {
            row["parent_id"]: row
            for row in self.chunks
            if row["content_kind"] == "instrument_download_routing"
        }
        endpoint_by_id = {row["endpoint_id"]: row for row in self.endpoints}
        for instrument in self.instruments:
            text = chunk_by_parent[instrument["instrument_id"]]["text"]
            self.assertTrue(text.startswith("Data for "))
            self.assertIn("available to download from", text)
            self.assertIn("Physical site:", text)
            self.assertIn(instrument["physical_site"], text)
            self.assertIn("Available formats:", text)
            self.assertIn(instrument["observed_layout"], text)
            self.assertIn("Aliases:", text)
            self.assertIn("Caveats:", text)
            for endpoint_id in instrument["endpoint_ids"]:
                endpoint = endpoint_by_id[endpoint_id]
                self.assertIn(endpoint["label"], text)
                self.assertIn(endpoint["url"], text)

    def test_das_interrogator_hardware_is_inherited_from_shared_inventory(self) -> None:
        by_key = {row["portal_instrument_key"]: row for row in self.instruments}
        self.assertEqual(by_key["PI-DAS24"]["manufacturer"], "Alcatel Subsea Networks")
        self.assertEqual(by_key["PI-DAS24"]["model"], "OptoDAS")
        self.assertIn("Nokia multi-span DAS", by_key["PI-DAS25"]["model"])
        self.assertIn("Silixa iDASv3", by_key["PI-DAS-OPTASENSE-SILIXA"]["model"])
        chunks = {row["parent_id"]: row["text"] for row in self.chunks}
        for key in ("PI-DAS-OPTASENSE-SILIXA", "PI-DAS24", "PI-DAS25"):
            self.assertIn("Interrogator hardware:", chunks[by_key[key]["instrument_id"]])

    def test_exact_urls_hosts_and_official_pages(self) -> None:
        endpoint_by_key = {(row["instrument_key"], row["endpoint_key"]): row for row in self.endpoints}
        for instrument_key, dataset in PI_INSTRUMENTS.items():
            for endpoint in dataset["endpoints"]:
                record = endpoint_by_key[(instrument_key, endpoint["endpoint_id"])]
                self.assertEqual(record["url"], endpoint["url"])
                self.assertEqual(urlparse(record["url"]).hostname, PORTAL_HOST)
            self.assertTrue(any(source.get("source_url") == dataset["official_url"] for source in self.sources))

    def test_tool_schemas_and_agentic_flow_edges(self) -> None:
        expected_schemas = {row["name"]: row for row in PI_PORTAL_TOOL_SCHEMAS}
        tools = {row["name"]: row for row in self.tools}
        self.assertEqual(set(tools), set(expected_schemas))
        for name, record in tools.items():
            self.assertEqual(record["input_schema"], expected_schemas[name]["inputSchema"])

        triples = {(row["source_id"], row["predicate"], row["target_id"]) for row in self.relationships}
        tool_ids = {row["name"]: row["tool_id"] for row in self.tools}
        for endpoint in self.endpoints:
            for name in ["pi_portal_browse", "pi_portal_find_files", "pi_portal_plan_download", "pi_portal_download_files"]:
                self.assertIn((endpoint["endpoint_id"], "ACCESSIBLE_WITH", tool_ids[name]), triples)
            self.assertIn((tool_ids["pi_portal_browse"], "BROWSES", endpoint["endpoint_id"]), triples)
            self.assertIn((tool_ids["pi_portal_find_files"], "BROWSES", endpoint["endpoint_id"]), triples)
            self.assertIn((tool_ids["pi_portal_download_files"], "DOWNLOADS_FROM", endpoint["endpoint_id"]), triples)
        for name in ["pi_portal_browse", "pi_portal_find_files", "pi_portal_plan_download", "pi_portal_download_files"]:
            self.assertIn((ROUTING_POLICY_ID, "USE_CORPUS_FIRST_THEN_INVOKE_TOOL", tool_ids[name]), triples)

    def test_routing_chunk_names_all_sources_and_endpoints(self) -> None:
        policy = next(row for row in self.chunks if row["content_kind"] == "routing_policy")
        lower = policy["text"].casefold()
        self.assertIn("static corpus first", lower)
        self.assertIn("user-invoked", lower)
        self.assertIn("live tools are only", lower)
        for source in self.sources:
            self.assertIn(source["title"], policy["text"])
            self.assertIn(source.get("source_url") or source["source_path"], policy["text"])
        for endpoint in self.endpoints:
            self.assertIn(endpoint["label"], policy["text"])
            self.assertIn(endpoint["url"], policy["text"])

    def test_graph_integrity_and_deterministic_ids(self) -> None:
        node_ids = set()
        for rows, key in [
            (self.instruments, "instrument_id"),
            (self.endpoints, "endpoint_id"),
            (self.sites, "site_id"),
            (self.sources, "source_id"),
            (self.tools, "tool_id"),
            (self.entities, "entity_id"),
            (self.chunks, "chunk_id"),
        ]:
            for row in rows:
                self.assertNotIn(row[key], node_ids)
                node_ids.add(row[key])
        self.assertTrue(all(row["source_id"] in node_ids and row["target_id"] in node_ids for row in self.relationships))
        self.assertEqual(len({row["relationship_id"] for row in self.relationships}), len(self.relationships))

        second = Path(self.temp.name) / "second"
        build(second)
        for filename in GRAPH_FILES:
            first_rows = read_jsonl(self.output / filename)
            second_rows = read_jsonl(second / filename)
            self.assertEqual(first_rows, second_rows, filename)
        self.assertNotIn("undefined", "\n".join((self.output / name).read_text(encoding="utf-8").casefold() for name in GRAPH_FILES))


if __name__ == "__main__":
    unittest.main()
