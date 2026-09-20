#!/usr/bin/env python3
"""Load a validated normalized build, then atomically activate it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def batches(values: Iterable[Any], size: int = 1000) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_build(dsn: str, normalized: Path, *, activate: bool, embeddings: Path | None = None) -> dict[str, int]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
        from pgvector.psycopg import register_vector
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("Install requirements.txt before loading PostgreSQL") from exc

    manifest = json.loads((normalized / "build_manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("passed"):
        raise ValueError("Normalized build did not pass validation")
    build_id = manifest["build_id"]
    if build_id != manifest.get("catalog_fingerprint_sha256"):
        raise ValueError("Build ID must equal the full catalog SHA-256 fingerprint")
    counts: dict[str, int] = {}

    with psycopg.connect(dsn) as connection:
        register_vector(connection)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '10min'")
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('graphrag_build_loader'))")
            cursor.execute(
                "INSERT INTO graphrag.corpus_builds(build_id,catalog_fingerprint_sha256,schema_version,created_at_utc,manifest,validation_passed) "
                "VALUES (%s,%s,%s,%s,%s,false) ON CONFLICT (build_id) DO NOTHING",
                (build_id, manifest["catalog_fingerprint_sha256"], manifest["schema_version"],
                 manifest["created_at_utc"], Jsonb(manifest)),
            )
            cursor.execute(
                "SELECT validation_passed,catalog_fingerprint_sha256 FROM graphrag.corpus_builds WHERE build_id=%s",
                (build_id,),
            )
            existing = cursor.fetchone()
            if existing and existing[1] != manifest["catalog_fingerprint_sha256"]:
                raise ValueError(f"Build ID collision for {build_id}")

            for batch in batches(read_jsonl(normalized / "collections.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.collections(build_id,collection_id,name,root_path,scope,manifest) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"], r["collection_id"], r["name"], r["root_path"], r.get("scope"), Jsonb(r["manifest"])) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "source_files.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.source_files(build_id,file_id,collection_id,relative_path,sha256,byte_size,record_count) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"],r["file_id"],r["collection_id"],r["relative_path"],r["sha256"],r["byte_size"],r.get("record_count")) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "nodes.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.nodes(build_id,collection_id,local_id,display_name,summary,source_url,record_kinds,representative_payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"],r["collection_id"],r["local_id"],r["display_name"],r.get("summary"),r.get("source_url"),r["record_kinds"],Jsonb(r["representative_payload"])) for r in batch],
                )

            cursor.execute("SELECT file_id,source_file_pk FROM graphrag.source_files WHERE build_id=%s", (build_id,))
            file_pks = dict(cursor.fetchall())
            for batch in batches(read_jsonl(normalized / "source_files.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.source_file_roles(source_file_pk,role) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                    [(file_pks[r["file_id"]], role) for r in batch for role in r["roles"]],
                )
            cursor.execute("SELECT collection_id,local_id,node_pk FROM graphrag.nodes WHERE build_id=%s", (build_id,))
            node_pks = {(c, i): pk for c, i, pk in cursor.fetchall()}

            for batch in batches(read_jsonl(normalized / "node_records.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.node_records(source_file_pk,line_no,node_pk,record_kind,payload_sha256,source_is_untrusted_data,payload) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(file_pks[r["file_id"]],r["line_no"],node_pks[(r["collection_id"],r["local_id"])],r["record_kind"],r["payload_sha256"],r["source_is_untrusted_data"],Jsonb(r["payload"])) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "node_identifiers.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.node_identifiers(node_pk,identifier,identifier_type) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(node_pks[(r["collection_id"],r["local_id"])],r["identifier"],r["identifier_type"]) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "chunks.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.chunks(build_id,collection_id,chunk_id,node_pk,title,section_heading,body,source_url,locator,text_sha256,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"],r["collection_id"],r["chunk_id"],node_pks[(r["collection_id"],r["node_local_id"])],r["title"],r.get("section_heading"),r["body"],r.get("source_url"),r.get("locator"),r["text_sha256"],Jsonb(r["metadata"])) for r in batch],
                )
            cursor.execute("SELECT collection_id,chunk_id,chunk_pk FROM graphrag.chunks WHERE build_id=%s", (build_id,))
            chunk_pks = {(c, i): pk for c, i, pk in cursor.fetchall()}

            for batch in batches(read_jsonl(normalized / "chunk_links.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.chunk_links(chunk_pk,link_type,target_node_pk) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(chunk_pks[(r["collection_id"],r["chunk_id"])],r["link_type"],node_pks[(r["collection_id"],r["target_local_id"])]) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "edge_records.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.edge_records(source_file_pk,line_no,raw_edge_id,source_node_pk,predicate,target_node_pk,payload_sha256,payload) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(file_pks[r["file_id"]],r["line_no"],r.get("raw_edge_id"),node_pks[(r["collection_id"],r["source_local_id"])],r["predicate"],node_pks[(r["collection_id"],r["target_local_id"])],r["payload_sha256"],Jsonb(r["payload"])) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "edge_facts.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.edge_facts(build_id,collection_id,source_node_pk,predicate,target_node_pk) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"],r["collection_id"],node_pks[(r["collection_id"],r["source_local_id"])],r["predicate"],node_pks[(r["collection_id"],r["target_local_id"])]) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "structured_records.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.structured_records(source_file_pk,line_no,collection_id,record_id,subject_id,observed_at,payload) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(file_pks[r["file_id"]],r["line_no"],r["collection_id"],r["record_id"],r.get("subject_id"),r.get("observed_at"),Jsonb(r["payload"])) for r in batch],
                )
            for batch in batches(read_jsonl(normalized / "tools.jsonl")):
                cursor.executemany(
                    "INSERT INTO graphrag.tools(build_id,collection_id,name,description,input_schema,runtime,manifest_path,metadata) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(r["build_id"],r["collection_id"],r["name"],r["description"],Jsonb(r["input_schema"]),r.get("runtime"),r["manifest_path"],Jsonb(r["metadata"])) for r in batch],
                )

            if embeddings:
                import numpy as np
                meta = json.loads((embeddings / "embedding_manifest.json").read_text(encoding="utf-8"))
                matrix = np.load(embeddings / meta["matrix_file"], mmap_mode="r")
                mappings = list(read_jsonl(embeddings / meta["mapping_file"]))
                if matrix.shape != (len(mappings), 384):
                    raise ValueError(f"Embedding shape mismatch: {matrix.shape}")
                expected_mapping_keys = {(r["collection_id"], r["chunk_id"]) for r in mappings}
                if len(expected_mapping_keys) != len(mappings):
                    raise ValueError("Embedding mapping contains duplicate collection/chunk keys")
                if len(mappings) != manifest["counts"]["chunks"]:
                    raise ValueError(
                        f"Embedding mapping has {len(mappings)} rows; expected {manifest['counts']['chunks']}"
                    )
                for start in range(0, len(mappings), 500):
                    part = mappings[start:start + 500]
                    cursor.executemany(
                        "INSERT INTO graphrag.embeddings(chunk_pk,model_id,model_revision,model_artifact_sha256,dimensions,normalized,text_sha256,embedding) VALUES(%s,%s,%s,%s,384,%s,%s,%s) ON CONFLICT DO NOTHING",
                        [(chunk_pks[(r["collection_id"],r["chunk_id"])],meta["model_id"],meta["model_revision"],meta.get("model_artifact_sha256"),meta["normalized"],r["text_sha256"],matrix[start+i]) for i,r in enumerate(part)],
                    )

            expected = manifest["counts"]
            table_checks = {
                "collections": "collections", "source_files": "source_files", "node_records": "node_records",
                "nodes": "nodes", "chunks": "chunks", "edge_records": "edge_records",
                "edge_facts": "edge_facts", "structured_records": "structured_records", "tools": "tools",
            }
            for key, table in table_checks.items():
                if table in {"node_records", "edge_records", "structured_records"}:
                    cursor.execute(f"SELECT count(*) FROM graphrag.{table} r JOIN graphrag.source_files f USING(source_file_pk) WHERE f.build_id=%s", (build_id,))
                else:
                    cursor.execute(f"SELECT count(*) FROM graphrag.{table} WHERE build_id=%s", (build_id,))
                actual = cursor.fetchone()[0]
                counts[key] = actual
                if actual != expected[key]:
                    raise ValueError(f"{table}: expected {expected[key]}, got {actual}")
            if embeddings:
                cursor.execute(
                    "SELECT count(*), "
                    "count(*) FILTER (WHERE e.text_sha256 <> c.text_sha256), "
                    "count(*) FILTER (WHERE e.model_revision <> %s OR e.model_id <> %s) "
                    "FROM graphrag.embeddings e JOIN graphrag.chunks c USING(chunk_pk) "
                    "WHERE c.build_id=%s AND e.model_id=%s",
                    (meta["model_revision"], meta["model_id"], build_id, meta["model_id"]),
                )
                embedding_count, stale_hashes, wrong_model_metadata = cursor.fetchone()
                if embedding_count != expected["chunks"]:
                    raise ValueError(
                        f"Embedding count {embedding_count} does not match chunks {expected['chunks']}"
                    )
                if stale_hashes or wrong_model_metadata:
                    raise ValueError(
                        f"Embedding provenance mismatch: stale_hashes={stale_hashes}, "
                        f"wrong_model_metadata={wrong_model_metadata}"
                    )
            cursor.execute("UPDATE graphrag.corpus_builds SET validation_passed=true WHERE build_id=%s", (build_id,))
            if activate:
                cursor.execute("SELECT graphrag.activate_build(%s)", (build_id,))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    print(json.dumps(load_build(args.dsn, args.normalized, activate=args.activate, embeddings=args.embeddings), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
