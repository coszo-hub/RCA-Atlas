from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pymseed import MS3TraceList


def decode(path: Path) -> dict:
    traces = MS3TraceList.from_file(str(path), unpack_data=True)
    segments = [seg for tid in traces for seg in tid]
    if not segments:
        return {"start": None, "startMs": None, "rate": None, "samples": []}
    seg = max(segments, key=lambda s: s.samplecnt)
    start = seg.starttime_str()
    if start.endswith("Z") and "." in start:
        start = start.split(".")[0] + "Z"
    start_ms = int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp() * 1000)
    return {"start": start, "startMs": start_ms, "rate": float(seg.samprate), "samples": list(seg.datasamples)}
