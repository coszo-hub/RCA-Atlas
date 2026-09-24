#!/usr/bin/env python3
"""Extract Nokia MultiDAS saved/unmasked spatial intervals from a file header.

The OOI DAS25 MultiDAS format embeds ``chunk_meta.masked`` in its MessagePack
header.  Despite its historic field name, that list identifies the along-cable
intervals *saved* in a spatially masked file; all intervals outside it are not
present in the data stream.  This utility reads only the small header, never
the strain-rate array, and records the exact file URL as provenance.
"""

from __future__ import annotations

import argparse
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.request import Request, urlopen


MAGIC = b"OFDR1MAGIC"


def _unpacker(payload: bytes):
    try:
        import msgpack
    except ImportError as exc:  # pragma: no cover - environment configuration
        raise RuntimeError("msgpack is required to inspect Nokia MultiDAS headers") from exc
    return msgpack.Unpacker(raw=False), msgpack


def parse_header(stream: BinaryIO) -> dict[str, Any]:
    if stream.read(len(MAGIC)) != MAGIC:
        raise ValueError("Not a complete Nokia MultiDAS (OFDR1MAGIC) file")
    fixed = stream.read(struct.calcsize("<BII"))
    if len(fixed) != struct.calcsize("<BII"):
        raise ValueError("Truncated MultiDAS header")
    version, header_bytes, array_start = struct.unpack("<BII", fixed)
    payload = stream.read(header_bytes)
    if len(payload) != header_bytes:
        raise ValueError("Truncated MessagePack header")
    unpacker, _ = _unpacker(payload)
    unpacker.feed(payload)
    array_info = unpacker.unpack()
    unpacker.unpack()  # historical unused header record
    chunk_meta = unpacker.unpack()
    return {"version": version, "header_bytes": header_bytes, "array_start": array_start,
            "array_info": array_info, "chunk_meta": chunk_meta}


def parse_url(url: str, read_limit: int = 1024 * 1024) -> dict[str, Any]:
    # Deliberately omit Range: the PIWeb SimpleHTTP server may ignore it.  Read
    # the header then close the response before array data is downloaded.
    request = Request(url, headers={"User-Agent": "RCA-Atlas/1.0"})
    with urlopen(request, timeout=60) as response:
        class LimitedReader:
            def __init__(self, raw): self.raw, self.remaining = raw, read_limit
            def read(self, count=-1):
                if count < 0 or count > self.remaining: count = self.remaining
                data = self.raw.read(count); self.remaining -= len(data); return data
        return parse_header(LimitedReader(response))


def mask_record(url: str, parsed: dict[str, Any], retrieved_at_utc: str | None = None) -> dict[str, Any]:
    meta = parsed["chunk_meta"]
    raw_intervals = meta.get("masked")
    if not isinstance(raw_intervals, list) or not raw_intervals:
        raise ValueError("MultiDAS header contains no spatial-mask intervals")
    intervals = []
    for interval in raw_intervals:
        if not isinstance(interval, (list, tuple)) or len(interval) != 2:
            raise ValueError("Invalid spatial-mask interval")
        start, end = map(float, interval)
        if not (0 <= start < end):
            raise ValueError("Spatial-mask intervals must be increasing positive distances")
        intervals.append({"start_m": start, "end_m": end, "length_m": end - start})
    dx = float(meta["dx"])
    saved_length_m = sum(item["length_m"] for item in intervals)
    return {
        "record_type": "multidas_spatial_mask_coverage",
        "source_url": url,
        "retrieved_at_utc": retrieved_at_utc or datetime.now(timezone.utc).isoformat(),
        "format_magic": "OFDR1MAGIC", "format_version": parsed["version"],
        "cable": "north" if "_north_" in url else "south" if "_south_" in url else None,
        "sampling_rate_hz": float(meta["fs2"]), "channel_spacing_m": dx,
        "gauge_length_setting": meta.get("gauge"), "stream_start_epoch_utc": meta.get("stream.proc_start"),
        "saved_unmasked_intervals_m": intervals,
        "saved_unmasked_length_m": saved_length_m,
        "maximum_saved_distance_m": max(item["end_m"] for item in intervals),
        "source_field_name": "chunk_meta.masked",
        "interpretation": "Intervals are present/saved data; distance outside the intervals was spatially masked out.",
        "caveat": "Mask metadata was present but not necessarily applied from 2025-11-26 through 2025-12-02; validate each file's array shape before treating it as masked.",
        "source_is_untrusted_data": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", required=True, help="Public MultiDAS file URL; repeat for multiple files")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = [mask_record(url, parse_url(url)) for url in args.url]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    print(json.dumps({"records": len(records), "saved_unmasked_length_m": [row["saved_unmasked_length_m"] for row in records]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
