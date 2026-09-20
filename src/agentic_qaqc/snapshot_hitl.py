#!/usr/bin/env python3
"""Create a timestamped fallback snapshot of public QAQC HITL notes."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "RCN-Agent-QAQC/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://ec2.qaqc.ooi-rca.net")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    index_url = f"{base}/HITL_notes/index.json"
    files = json.loads(get(index_url).decode())
    retrieved = datetime.now(timezone.utc).isoformat()
    records = []
    for filename in files:
        source_url = f"{base}/HITL_notes/{urllib.parse.quote(filename)}"
        text = get(source_url).decode("utf-8", errors="replace")
        for row in csv.reader(io.StringIO(text)):
            if not row:
                continue
            records.append({"reference_designator": row[0].strip(), "note": ",".join(row[1:]).strip(), "source_file": filename, "source_url": source_url, "retrieved_at": retrieved, "source_is_untrusted_data": True})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    print(json.dumps({"files": len(files), "records": len(records), "retrieved_at": retrieved, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
