#!/usr/bin/env python3
"""Resumable, lawful full-text acquisition for the literature catalog.

Only publicly accessible copies discovered from a record's explicit URLs or
open-access resolvers are stored.  Paywalls and authentication are never
bypassed.  Output is runtime state, deliberately excluded from Git.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from literature_fulltext_tools import REQUIRED_REASON, LiteratureFullTextToolkit


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/Literature/literature.jsonl"
CACHE = ROOT / "runtime_data/Literature/full_text_cache"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cached_work_ids(cache_dir: Path) -> set[str]:
    return {
        item.parent.name.casefold()
        for item in cache_dir.glob("*/metadata.json")
        if item.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Maximum uncached works to attempt; 0 means all.")
    parser.add_argument("--delay", type=float, default=0.75, help="Seconds between works (default: 0.75).")
    parser.add_argument("--report", type=Path, default=CACHE / "acquisition_report.jsonl")
    parser.add_argument("--confirm-open-access", action="store_true", help="Required before making network requests.")
    args = parser.parse_args()
    if not args.confirm_open_access:
        parser.error("--confirm-open-access is required; this job performs public network requests")

    CACHE.mkdir(parents=True, exist_ok=True)
    toolkit = LiteratureFullTextToolkit(CATALOG, CACHE)
    already_cached = cached_work_ids(CACHE)
    records = [row for row in toolkit.rows if str(row["id"]).casefold() not in already_cached]
    # Existing direct full-text candidates first; all remaining DOI-resolvable
    # records follow.  Stable ordering makes interrupted jobs reproducible.
    records.sort(key=lambda row: (not bool(row.get("full_text_url")), not bool(row.get("resolved_doi")), row["id"]))
    if args.limit > 0:
        records = records[:args.limit]

    summary = {"attempted": 0, "downloaded": 0, "unavailable": 0, "failed": 0}
    with args.report.open("a", encoding="utf-8") as stream:
        for ordinal, row in enumerate(records, 1):
            work_id = row["id"]
            try:
                result = toolkit.evidence(
                    work_id=work_id,
                    question="Retrieve and preserve publicly accessible full-text evidence for this literature record.",
                    retrieval_reason=REQUIRED_REASON,
                    max_passages=1,
                    fetch_if_missing=True,
                )
                access_status = result.get("access_status", "error")
                if access_status == "downloaded":
                    summary["downloaded"] += 1
                elif result.get("ok"):
                    summary["unavailable"] += 1
                else:
                    summary["failed"] += 1
                event = {
                    "timestamp": utc_now(), "work_id": work_id,
                    "title": row.get("resolved_title") or row.get("citation"),
                    "access_status": access_status,
                    "source_url": result.get("source_url"),
                    "sha256": result.get("document_sha256"),
                    "page_count": result.get("page_count"),
                    "attempts": result.get("attempts", []),
                }
            except Exception as exc:  # Preserve failure details and continue.
                summary["failed"] += 1
                event = {"timestamp": utc_now(), "work_id": work_id, "access_status": "error", "error": f"{type(exc).__name__}: {exc}"}
            summary["attempted"] += 1
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"[{ordinal}/{len(records)}] {work_id}: {event['access_status']}", flush=True)
            if args.delay > 0 and ordinal < len(records):
                time.sleep(args.delay)
    print(json.dumps({"completed_at": utc_now(), **summary, "report": str(args.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
