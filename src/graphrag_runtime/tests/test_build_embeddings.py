import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from build_embeddings import BuildError, MODEL_DIMENSION, build_embeddings, load_records


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeEmbedder:
    def __init__(self, fail_on_call=None):
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.seen = []

    def passage_embed(self, texts, **kwargs):
        self.calls += 1
        values = list(texts)
        self.seen.extend(values)
        if self.calls == self.fail_on_call:
            raise RuntimeError("simulated interruption")
        for text in values:
            vector = np.zeros(MODEL_DIMENSION, dtype=np.float32)
            vector[sum(text.encode()) % MODEL_DIMENSION] = 1.0
            yield vector


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        data = self.root / "data" / "one"
        data.mkdir(parents=True)
        rows = [
            {"chunk_id": "a", "text": "alpha"},
            {"chunk_id": "b", "text": "bravo"},
            {"chunk_id": "c", "text": "charlie"},
            {"chunk_id": "d", "text": "delta"},
            {"chunk_id": "e", "text": "echo"},
        ]
        self.input_path = data / "chunks.jsonl"
        self.input_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        catalog = {
            "catalog_schema_version": "1.0",
            "build_fingerprint_sha256": "f" * 64,
            "project_root": str(self.root),
            "collections": [{
                "collection_id": "one",
                "embedding_inputs": [{
                    "path": "data/one/chunks.jsonl",
                    "sha256": file_hash(self.input_path),
                    "records": len(rows),
                }],
            }],
            "totals": {"embedding_records": len(rows)},
        }
        self.catalog_path = self.root / "corpus_catalog.json"
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        self.output = self.root / "output"

    def tearDown(self):
        self.temp.cleanup()

    def test_builds_matrix_mapping_and_metadata(self):
        fake = FakeEmbedder()
        metadata = build_embeddings(
            self.catalog_path, self.output, self.root / "cache", batch_size=2,
            embedder_factory=lambda _cache, _threads: fake,
        )
        matrix = np.load(self.output / "embeddings.npy")
        mappings = [json.loads(line) for line in (self.output / "embedding_rows.jsonl").read_text().splitlines()]
        self.assertEqual(matrix.shape, (5, MODEL_DIMENSION))
        self.assertTrue(np.allclose(np.linalg.norm(matrix, axis=1), 1.0))
        self.assertEqual([row["record_id"] for row in mappings], list("abcde"))
        self.assertEqual([row["chunk_id"] for row in mappings], list("abcde"))
        self.assertTrue(all(len(row["text_sha256"]) == 64 for row in mappings))
        self.assertEqual(metadata["pgvector_type"], "vector(384)")
        self.assertEqual(metadata["model_id"], "BAAI/bge-small-en-v1.5")
        self.assertEqual(metadata["model_artifact_sha256"], metadata["model_sha256"])
        self.assertEqual(metadata["status"], "complete")
        self.assertEqual(fake.calls, 3)

    def test_resumes_only_uncommitted_batches(self):
        interrupted = FakeEmbedder(fail_on_call=2)
        with self.assertRaisesRegex(RuntimeError, "simulated"):
            build_embeddings(
                self.catalog_path, self.output, self.root / "cache", batch_size=2,
                embedder_factory=lambda _cache, _threads: interrupted,
            )
        progress = json.loads((self.output / "embedding_progress.json").read_text())
        self.assertEqual(progress["next_row"], 2)
        resumed = FakeEmbedder()
        build_embeddings(
            self.catalog_path, self.output, self.root / "cache", batch_size=2,
            embedder_factory=lambda _cache, _threads: resumed,
        )
        self.assertEqual(resumed.seen, ["charlie", "delta", "echo"])

    def test_rejects_changed_source(self):
        self.input_path.write_text('{"chunk_id":"a","text":"changed"}\n', encoding="utf-8")
        with self.assertRaisesRegex(BuildError, "hash mismatch"):
            load_records(self.catalog_path)

    def test_rejects_duplicate_collection_record_id(self):
        self.input_path.write_text(
            '{"chunk_id":"same","text":"one"}\n{"chunk_id":"same","text":"two"}\n',
            encoding="utf-8",
        )
        catalog = json.loads(self.catalog_path.read_text())
        catalog["collections"][0]["embedding_inputs"][0]["sha256"] = file_hash(self.input_path)
        catalog["collections"][0]["embedding_inputs"][0]["records"] = 2
        catalog["totals"]["embedding_records"] = 2
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        with self.assertRaisesRegex(BuildError, "Duplicate record key"):
            load_records(self.catalog_path)

    def test_reuses_unchanged_vectors_after_corpus_growth(self):
        original = FakeEmbedder()
        reuse = self.root / "reuse"
        build_embeddings(
            self.catalog_path, reuse, self.root / "cache", batch_size=2,
            embedder_factory=lambda _cache, _threads: original,
        )
        rows = [json.loads(line) for line in self.input_path.read_text(encoding="utf-8").splitlines()]
        rows.append({"chunk_id": "f", "text": "foxtrot"})
        self.input_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        catalog["build_fingerprint_sha256"] = "e" * 64
        catalog["collections"][0]["embedding_inputs"][0]["sha256"] = file_hash(self.input_path)
        catalog["collections"][0]["embedding_inputs"][0]["records"] = len(rows)
        catalog["totals"]["embedding_records"] = len(rows)
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        incremental = FakeEmbedder()
        metadata = build_embeddings(
            self.catalog_path, self.output, self.root / "cache", batch_size=2,
            embedder_factory=lambda _cache, _threads: incremental, reuse_dir=reuse,
        )
        self.assertEqual(incremental.seen, ["foxtrot"])
        self.assertEqual(metadata["reused_record_count"], 5)
        self.assertEqual(np.load(self.output / "embeddings.npy").shape, (6, MODEL_DIMENSION))


if __name__ == "__main__":
    unittest.main()
