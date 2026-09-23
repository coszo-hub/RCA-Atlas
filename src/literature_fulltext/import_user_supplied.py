#!/usr/bin/env python3
"""Validate and import PDFs deliberately supplied by a licensed user."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from literature_fulltext_tools import LiteratureFullTextToolkit, utc_now


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/Literature/literature.jsonl"
CACHE = ROOT / "runtime_data/Literature/full_text_cache"
DEFAULT_INPUT = ROOT / "source_material/literature_user_supplied"
WORK_ID = re.compile(r"^((?:COSZO-REF|OOI-ZOT)-\d{3})(?:[-_.].*)?\.pdf$", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=CACHE / "user_supplied_import_report.jsonl")
    parser.add_argument("--replace", action="store_true", help="Replace an existing cached copy for the same work ID.")
    parser.add_argument("--max-new", type=int, default=0, help="Maximum new PDFs to import; 0 means all.")
    args = parser.parse_args()
    toolkit = LiteratureFullTextToolkit(CATALOG, CACHE)
    files = sorted(path for path in args.input.iterdir() if path.is_file())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report, new_count = [], 0
    with args.report.open("a", encoding="utf-8") as stream:
      for path in files:
        match = WORK_ID.match(path.name)
        if not match:
            event = {"timestamp": utc_now(), "file": path.name, "status": "unmapped_filename"}
        else:
            work_id = match.group(1).upper()
            row = toolkit.by_id.get(work_id.casefold())
            if not row:
                event = {"timestamp": utc_now(), "file": path.name, "work_id": work_id, "status": "unknown_work_id"}
            else:
                cache_root = CACHE / work_id
                if (cache_root / "metadata.json").is_file() and not args.replace:
                    event = {"timestamp": utc_now(), "file": path.name, "work_id": work_id, "status": "already_cached"}
                elif args.max_new > 0 and new_count >= args.max_new:
                    break
                else:
                    try:
                        result = toolkit.ingest_user_pdf(row, path)
                        metadata = result["cache"]["metadata"]
                        event = {"timestamp": utc_now(), "file": path.name, "work_id": work_id,
                                 "status": "imported", "input_sha256": sha256(path),
                                 "cached_sha256": metadata["sha256"], "page_count": metadata["page_count"],
                                 "chunk_count": metadata["chunk_count"]}
                        new_count += 1
                    except Exception as exc:
                        event = {"timestamp": utc_now(), "file": path.name, "work_id": work_id,
                                 "status": "error", "error": f"{type(exc).__name__}: {exc}"}
                        new_count += 1
        report.append(event)
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
    print(json.dumps({"processed": len(report), "status_counts": {
        status: sum(item["status"] == status for item in report) for status in sorted({item["status"] for item in report})
    }, "report": str(args.report)}))
    return 0 if not any(item["status"] == "error" for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
