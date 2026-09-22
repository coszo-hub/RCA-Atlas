"""Export Atlas chunks as provenance-preserving Microsoft GraphRAG text input.

This never modifies the authoritative Atlas graph.  Each exported document
contains its stable Atlas chunk ID and source URL so every extracted candidate
can be traced back before human review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collections", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    allowed = set(args.collections)
    docs = args.output / "input"
    docs.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "atlas_source_manifest.jsonl"
    written = 0
    with args.chunks.open(encoding="utf-8") as source, manifest_path.open("w", encoding="utf-8") as manifest:
        for line in source:
            row = json.loads(line)
            if allowed and row.get("collection_id") not in allowed:
                continue
            chunk_id = row["chunk_id"]
            text = row.get("body") or row.get("text") or ""
            if not text.strip():
                continue
            metadata = row.get("metadata") or {}
            source_url = row.get("source_url") or metadata.get("source_url") or ""
            path = docs / f"{chunk_id}.txt"
            path.write_text(
                f"Atlas chunk ID: {chunk_id}\nCollection: {row.get('collection_id', '')}\n"
                f"Title: {row.get('title', '')}\nSource URL: {source_url}\n\n{text}\n",
                encoding="utf-8",
            )
            manifest.write(json.dumps({"graphrag_document": path.name, "chunk_id": chunk_id,
                                       "collection_id": row.get("collection_id"), "source_url": source_url,
                                       "text_sha256": row.get("text_sha256")}, sort_keys=True) + "\n")
            written += 1
            if args.limit and written >= args.limit:
                break
    print(json.dumps({"documents": written, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
