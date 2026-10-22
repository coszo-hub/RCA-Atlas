#!/usr/bin/env python3
"""Re-extract the cached PDFs' text with the current extractor, in place.

Each cache entry keeps its PDF and metadata; its chunks.jsonl is rewritten from the PDF, and the metadata records the
new extraction version, chunk count and chunks hash. Entries already at the current version are skipped. The previous
chunks.jsonl and metadata.json are kept as *.prev, so a rerun of build_fulltext_corpus.py on them restores the old text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from literature_fulltext_tools import DEFAULT_MAX_OCR_PAGES, DEFAULT_MAX_PAGES, EXTRACTION_VERSION, LiteratureFullTextToolkit

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/Literature/literature.jsonl"
CACHE = ROOT / "runtime_data/Literature/full_text_cache"


def reextract(toolkit: LiteratureFullTextToolkit, entry: Path) -> str:
    metadata = json.loads((entry / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("content_type") != "application/pdf":
        return "not a PDF"
    if metadata.get("extraction_version") == EXTRACTION_VERSION:
        return "current"
    extraction = toolkit._extract_pdf(entry / metadata["payload_file"], max_pages=DEFAULT_MAX_PAGES, max_ocr_pages=DEFAULT_MAX_OCR_PAGES)
    chunks = toolkit._chunk_units(metadata["work_id"], extraction["units"])
    if not chunks:
        raise ValueError("re-extraction produced no chunks")
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in chunks)
    metadata.update(extraction_version=EXTRACTION_VERSION, chunk_count=len(chunks), ocr_pages=extraction.get("ocr_pages", []),
                    chunks_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest())
    for name in ("chunks.jsonl", "metadata.json"):
        shutil.copy2(entry / name, entry / f"{name}.prev")
    for name, data in (("chunks.jsonl", payload), ("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")):
        temporary = entry / f".{name}.tmp"
        temporary.write_text(data, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, entry / name)
    return "re-extracted"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    toolkit = LiteratureFullTextToolkit(CATALOG, args.cache)
    entries = sorted(p for p in args.cache.iterdir() if (p / "metadata.json").is_file())

    def run(entry: Path) -> tuple[str, str]:
        try:
            return entry.name, reextract(toolkit, entry)
        except Exception as exc:  # one bad PDF leaves its old text in place and is reported
            return entry.name, f"failed: {exc}"

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(run, entries))
    counts: dict[str, int] = {}
    for name, status in results:
        key = "failed" if status.startswith("failed") else status
        counts[key] = counts.get(key, 0) + 1
        if key == "failed":
            print(name, status)
    print(json.dumps(counts))
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
