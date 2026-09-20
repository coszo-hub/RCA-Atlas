#!/usr/bin/env python3
"""Build a deterministic, resumable embedding matrix from corpus_catalog.json."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

import numpy as np


MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_SOURCE_REPOSITORY = "qdrant/bge-small-en-v1.5-onnx-q"
MODEL_REVISION = "52398278842ec682c6f32300af41344b1c0b0bb2"
MODEL_FILE = "model_optimized.onnx"
MODEL_SHA256 = "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431"
MODEL_DIMENSION = 384
MODEL_MAX_TOKENS = 512
FASTEMBED_VERSION = "0.7.3"
OUTPUT_SCHEMA_VERSION = "1.0"
ID_FIELDS = (
    "chunk_id",
    "id",
    "entity_id",
    "instrument_id",
    "document_id",
    "source_id",
)


class BuildError(RuntimeError):
    pass


class Embedder(Protocol):
    def passage_embed(self, texts: Iterable[str], **kwargs: Any) -> Iterable[np.ndarray]: ...


@dataclass(frozen=True)
class InputRecord:
    row_index: int
    collection_id: str
    source_path: str
    source_line: int
    record_id: str
    text: str

    def mapping(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "collection_id": self.collection_id,
            "source_path": self.source_path,
            "source_line": self.source_line,
            "chunk_id": self.record_id,
            "record_id": self.record_id,
            "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def resolve_project_root(catalog: dict[str, Any], catalog_path: Path, override: Path | None) -> Path:
    if override is not None:
        return override.resolve()
    declared = catalog.get("project_root")
    if isinstance(declared, str) and declared:
        return Path(declared).expanduser().resolve()
    # A catalog normally lives at PROJECT/runtime_data/GraphRAG/corpus_catalog.json.
    try:
        return catalog_path.resolve().parents[2]
    except IndexError as exc:
        raise BuildError("Cannot infer project root; pass --project-root") from exc


def load_records(catalog_path: Path, project_root: Path | None = None) -> tuple[dict[str, Any], list[InputRecord]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("collections"), list):
        raise BuildError("Catalog must be an object with a collections array")
    root = resolve_project_root(catalog, catalog_path, project_root)
    records: list[InputRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    for collection in catalog["collections"]:
        collection_id = collection.get("collection_id")
        if not isinstance(collection_id, str) or not collection_id:
            raise BuildError("Every collection requires collection_id")
        for descriptor in collection.get("embedding_inputs", []):
            relative = descriptor.get("path")
            if not isinstance(relative, str) or not relative:
                raise BuildError(f"Invalid embedding input path in {collection_id}")
            path = root / relative
            if not path.is_file():
                raise BuildError(f"Embedding input does not exist: {path}")
            expected_hash = descriptor.get("sha256")
            actual_hash = sha256_file(path)
            if expected_hash and actual_hash != expected_hash:
                raise BuildError(f"Input hash mismatch for {path}: {actual_hash} != {expected_hash}")
            input_count = 0
            with path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise BuildError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
                    if not isinstance(row, dict):
                        raise BuildError(f"Expected object at {path}:{line_number}")
                    text = row.get("text")
                    if not isinstance(text, str) or not text.strip():
                        raise BuildError(f"Missing nonempty text at {path}:{line_number}")
                    value = next((row.get(field) for field in ID_FIELDS if row.get(field) is not None), None)
                    if value is None:
                        raise BuildError(f"No supported record ID at {path}:{line_number}")
                    record_id = str(value)
                    key = (collection_id, record_id)
                    if key in seen_keys:
                        raise BuildError(f"Duplicate record key {collection_id}:{record_id}")
                    seen_keys.add(key)
                    records.append(InputRecord(len(records), collection_id, relative, line_number, record_id, text.strip()))
                    input_count += 1
            expected_count = descriptor.get("records")
            if expected_count is not None and input_count != expected_count:
                raise BuildError(f"Record count mismatch for {path}: {input_count} != {expected_count}")
    totals = catalog.get("totals", {})
    expected_total = totals.get("embedding_records", totals.get("embedding_chunks"))
    if expected_total is not None and len(records) != expected_total:
        raise BuildError(f"Catalog total mismatch: {len(records)} != {expected_total}")
    return catalog, records


def write_mapping(path: Path, records: list[InputRecord]) -> str:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record.mapping(), sort_keys=True, separators=(",", ":")) + "\n")
    os.replace(temporary, path)
    return sha256_file(path)


def default_embedder(cache_dir: Path, threads: int) -> Embedder:
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise BuildError(f"fastembed=={FASTEMBED_VERSION} is required") from exc
    installed_version = importlib.metadata.version("fastembed")
    if installed_version != FASTEMBED_VERSION:
        raise BuildError(f"fastembed version {installed_version} != pinned {FASTEMBED_VERSION}")
    verify_cached_model(cache_dir)
    return TextEmbedding(
        model_name=MODEL_NAME,
        cache_dir=str(cache_dir),
        threads=threads,
        local_files_only=True,
    )


def find_model_file(cache_dir: Path) -> Path:
    preferred = cache_dir / f"models--{MODEL_SOURCE_REPOSITORY.replace('/', '--')}" / "snapshots" / MODEL_REVISION / MODEL_FILE
    if preferred.is_file():
        return preferred
    matches = list(cache_dir.rglob(MODEL_FILE))
    verified = [path for path in matches if sha256_file(path) == MODEL_SHA256]
    if len(verified) == 1:
        return verified[0]
    raise BuildError(f"Pinned model not found in {cache_dir}; run prefetch_model.py first")


def verify_cached_model(cache_dir: Path) -> Path:
    model_path = find_model_file(cache_dir)
    actual = sha256_file(model_path)
    if actual != MODEL_SHA256:
        raise BuildError(f"Model hash mismatch: {actual} != {MODEL_SHA256}")
    return model_path


def build_embeddings(
    catalog_path: Path,
    output_dir: Path,
    cache_dir: Path,
    *,
    project_root: Path | None = None,
    batch_size: int = 128,
    threads: int = 4,
    embedder_factory: Callable[[Path, int], Embedder] = default_embedder,
) -> dict[str, Any]:
    if batch_size < 1:
        raise BuildError("batch_size must be positive")
    catalog, records = load_records(catalog_path, project_root)
    if not records:
        raise BuildError("Catalog contains no embedding records")
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = output_dir / "embeddings.npy"
    mapping_path = output_dir / "embedding_rows.jsonl"
    progress_path = output_dir / "embedding_progress.json"
    metadata_path = output_dir / "embedding_manifest.json"
    catalog_fingerprint = catalog.get("build_fingerprint_sha256") or sha256_file(catalog_path)

    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        required = {
            "catalog_fingerprint_sha256": catalog_fingerprint,
            "model_revision": MODEL_REVISION,
            "model_sha256": MODEL_SHA256,
            "dimension": MODEL_DIMENSION,
            "record_count": len(records),
        }
        for key, expected in required.items():
            if progress.get(key) != expected:
                raise BuildError(f"Cannot resume: {key} changed")
        if not matrix_path.is_file() or not mapping_path.is_file():
            raise BuildError("Cannot resume: matrix or row mapping is missing")
        if progress.get("mapping_sha256") != sha256_file(mapping_path):
            raise BuildError("Cannot resume: row mapping changed")
        next_row = int(progress.get("next_row", 0))
        matrix = np.lib.format.open_memmap(matrix_path, mode="r+", dtype=np.float32, shape=(len(records), MODEL_DIMENSION))
    else:
        mapping_hash = write_mapping(mapping_path, records)
        matrix = np.lib.format.open_memmap(matrix_path, mode="w+", dtype=np.float32, shape=(len(records), MODEL_DIMENSION))
        next_row = 0
        progress = {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "status": "building",
            "catalog_fingerprint_sha256": catalog_fingerprint,
            "model_name": MODEL_NAME,
            "model_source_repository": MODEL_SOURCE_REPOSITORY,
            "model_revision": MODEL_REVISION,
            "model_sha256": MODEL_SHA256,
            "dimension": MODEL_DIMENSION,
            "normalized": True,
            "record_count": len(records),
            "mapping_sha256": mapping_hash,
            "next_row": 0,
        }
        atomic_json(progress_path, progress)

    if next_row < 0 or next_row > len(records):
        raise BuildError(f"Invalid resume row: {next_row}")
    embedder = embedder_factory(cache_dir, threads)
    for start in range(next_row, len(records), batch_size):
        end = min(start + batch_size, len(records))
        vectors = np.asarray(list(embedder.passage_embed([item.text for item in records[start:end]])), dtype=np.float32)
        if vectors.shape != (end - start, MODEL_DIMENSION):
            raise BuildError(f"Embedding shape {vectors.shape} != {(end - start, MODEL_DIMENSION)}")
        if not np.isfinite(vectors).all():
            raise BuildError(f"Non-finite embedding in rows {start}:{end}")
        norms = np.linalg.norm(vectors, axis=1)
        if not np.allclose(norms, 1.0, rtol=1e-3, atol=1e-3):
            raise BuildError(f"Embeddings are not normalized in rows {start}:{end}")
        matrix[start:end] = vectors
        matrix.flush()
        progress["next_row"] = end
        progress["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(progress_path, progress)

    del matrix
    # Rewrite from the canonical records when finalizing. This lets an older
    # checkpoint gain newly added loader fields without re-embedding rows.
    progress["mapping_sha256"] = write_mapping(mapping_path, records)
    progress["status"] = "complete"
    progress["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(progress_path, progress)
    metadata = {
        **progress,
        "model_id": MODEL_NAME,
        "model_artifact_sha256": MODEL_SHA256,
        "matrix_file": matrix_path.name,
        "matrix_sha256": sha256_file(matrix_path),
        "mapping_file": mapping_path.name,
        "dtype": "float32",
        "distance_metric": "cosine",
        "pgvector_type": f"vector({MODEL_DIMENSION})",
        "model_max_tokens": MODEL_MAX_TOKENS,
        "fastembed_version": FASTEMBED_VERSION,
    }
    atomic_json(metadata_path, metadata)
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--threads", type=int, default=4)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metadata = build_embeddings(
            args.catalog,
            args.output_dir,
            args.cache_dir,
            project_root=args.project_root,
            batch_size=args.batch_size,
            threads=args.threads,
        )
    except (BuildError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
