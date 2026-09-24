from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

def decode(path: Path) -> dict:
    # MiniSEED decoding is an optional live-panel capability. Import it at use
    # time so a missing platform wheel cannot keep status, ERDDAP, QA/QC, and
    # PI-portal routes from starting.
    try:
        from pymseed import MS3TraceList
    except ModuleNotFoundError as exc:
        raise RuntimeError("MiniSEED waveform decoding is unavailable on this gateway") from exc
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


def discard_request_dir(file: Path, root: Path | None) -> bool:
    """Delete the EarthScope request dir holding `file` (<root>/requests/<request id>/), and nothing else.

    Only acts when the gateway owns `root`; a file anywhere else is left alone."""
    if root is None:
        return False
    request_dir = Path(file).resolve().parent
    if request_dir.parent != (Path(root).resolve() / "requests"):
        return False
    shutil.rmtree(request_dir, ignore_errors=True)
    return True
