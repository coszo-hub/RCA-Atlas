import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NORMALIZED = ROOT.parents[1] / "runtime_data/GraphRAG/normalized"
NORMALIZED = PROJECT_NORMALIZED if PROJECT_NORMALIZED.exists() else ROOT / "normalized"


class RuntimeContractTests(unittest.TestCase):
    def test_real_normalized_build_has_audited_counts(self):
        manifest = json.loads((NORMALIZED / "build_manifest.json").read_text())
        self.assertTrue(manifest["passed"])
        self.assertEqual(manifest["counts"]["collections"], 13)
        self.assertEqual(manifest["counts"]["source_files"], 93)
        self.assertEqual(manifest["counts"]["node_records"], 23_404)
        self.assertEqual(manifest["counts"]["nodes"], 21_938)
        self.assertEqual(manifest["counts"]["chunks"], 6_565)
        self.assertEqual(manifest["counts"]["edge_records"], 30_242)
        self.assertEqual(manifest["counts"]["edge_facts"], 29_538)
        self.assertEqual(manifest["counts"]["structured_records"], 76_984)

    def test_each_embedding_file_retains_both_roles(self):
        rows = [json.loads(line) for line in (NORMALIZED / "source_files.jsonl").read_text().splitlines()]
        chunks = [row for row in rows if "embedding" in row["roles"]]
        self.assertEqual(len(chunks), 13)
        for row in chunks:
            self.assertIn("embedding", row["roles"])
            self.assertIn("graph_node", row["roles"])
        auxiliary = [row for row in rows if "auxiliary" in row["roles"]]
        self.assertEqual(len(auxiliary), 2)

    def test_api_database_role_has_no_base_table_grants(self):
        schema = (ROOT / "migrations/001_initial.sql").read_text()
        role = (ROOT / "migrations/002_local_api_role.sql").read_text()
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA graphrag FROM PUBLIC", schema)
        self.assertIn("SECURITY DEFINER", schema)
        self.assertNotIn("GRANT SELECT ON", role)
        self.assertIn("GRANT EXECUTE ON FUNCTION graphrag_api.hybrid_search", role)
        self.assertIn("default_transaction_read_only = on", role)

    def test_api_repository_uses_only_bounded_functions(self):
        source = (ROOT / "app/repository.py").read_text()
        for name in ("runtime_health", "hybrid_search", "graph_neighbors", "route_tools"):
            self.assertIn(f"graphrag_api.{name}", source)
        for table in ("graphrag.chunks", "graphrag.nodes", "graphrag.edge_facts", "graphrag.tools"):
            self.assertNotIn(table, source)


if __name__ == "__main__":
    unittest.main()
