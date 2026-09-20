#!/usr/bin/env python3
"""Live, incrementally indexed tools for COSZO Hub repository outputs.

The stable Graph-RAG corpus describes the repositories, schemas, and tool
capabilities.  This module reads the current output trees at query time so
new files written by an online pipeline are visible without rebuilding the
corpus.  A small SQLite index under runtime_data is refreshed incrementally.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import json
import math
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from gap_detection import detect_gaps as run_gap_detector
from earthscope_fdsn_agent_tools import (
    EARTHSCOPE_TOOL_SCHEMAS,
    EarthScopeFDSNToolkit,
    dispatch_earthscope,
)
from ooi_m2m_agent_tools import (
    OOIM2MToolkit,
    OOI_M2M_TOOL_SCHEMAS,
    dispatch_ooi_m2m,
)
from pi_portal_agent_tools import (
    PIPortalToolkit,
    PI_PORTAL_TOOL_SCHEMAS,
    dispatch_pi_portal,
)


UTC = timezone.utc
SUPPORTED_REPOSITORIES = {
    "absolute-seafloor-pressure": {
        "output_subdir": "PREST-data-collection/output",
        "env": "COSZO_PRESSURE_OUTPUT_ROOT",
        "commit": "43a420c7bf143007b5fa45963fc2c0dc1681cf75",
        "license": "permission-provided; upstream has no LICENSE file",
    },
    "chronfix": {
        "output_subdir": "examples/HYS14",
        "env": "COSZO_CHRONFIX_OUTPUT_ROOT",
        "commit": "486f05bcdaad26a1855ee90c987c41b7d36b835a",
        "license": "MIT",
    },
    "dive-index-hindcast": {
        "output_subdir": ".",
        "env": "COSZO_DIVE_OUTPUT_ROOT",
        "commit": "85e5318548fd2f3c0447f7d254e166c869a6b60d",
        "license": "permission-provided; upstream has no LICENSE file",
    },
    "sea-water-velocity": {
        "output_subdir": "VEL3D-data-collection/output",
        "env": "COSZO_VELOCITY_OUTPUT_ROOT",
        "commit": "5be90a0d2c92c4f7e4fdf06ceae98f66d22a6b25",
        "license": "permission-provided; upstream has no LICENSE file",
    },
}

PRESSURE_STATIONS = [
    {"station": "OO.HYSB1", "reference_designator": "RS01SLBS-MJ01A-06-PRESTA101", "site": "Slope Base, Hydrate Ridge", "location": "10", "pressure_channels": ["UDO", "LDO"], "temperature_channels": ["UK1", "LK1"]},
    {"station": "OO.HYS14", "reference_designator": "RS01SUM1-LJ01B-09-PRESTB102", "site": "Southern Hydrate Summit 1", "location": "10", "pressure_channels": ["UDO", "LDO"], "temperature_channels": ["UK1", "LK1"]},
    {"station": "OO.AXBA1", "reference_designator": "RS03AXBS-MJ03A-06-PRESTA301", "site": "Axial Base", "location": "10", "pressure_channels": ["UDO"], "temperature_channels": ["UK1"]},
]

VELOCITY_STATIONS = [
    {"station": "OO.HYSB1", "reference_designator": "RS01SLBS-MJ01A-12-VEL3DB101", "site": "Hydrate Slope Base", "location": "20", "channels": ["LOE", "LON", "LOZ", "LKO"], "sample_rate_hz": 1},
    {"station": "OO.HYS14", "reference_designator": "RS01SUM1-LJ01B-12-VEL3DB104", "site": "Hydrate Summit 1-4", "location": "20", "channels": ["LOE", "LON", "LOZ", "LKO"], "sample_rate_hz": 1},
    {"station": "OO.AXBA1", "reference_designator": "RS03AXBS-MJ03A-12-VEL3DB301", "site": "Axial Base", "location": "20", "channels": ["LOE", "LON", "LOZ", "LKO"], "sample_rate_hz": 1},
]

DIVE_CONFIG = {
    "formula": "Dive Index = significant wave height (m) * 10-m wind speed (knots)",
    "wind_conversion": "wind_knots = hypot(U10_mps, V10_mps) * 1.943844492",
    "analysis_period": ["2006-01-01T00:00:00", "2025-12-31T23:59:59"],
    "thresholds": [40, 70],
    "look_ahead_hours": [12, 72],
    "seasonal_gaussian_sigma_days": 3,
    "sites": [
        {"name": "Slope Base", "latitude": 44.50960, "longitude": -125.39830, "scope": "RCA"},
        {"name": "Axial Base", "latitude": 45.82030, "longitude": -129.73640, "scope": "RCA"},
        {"name": "Oregon Offshore", "latitude": 44.36937, "longitude": -124.95386, "scope": "published COSZO output"},
        {"name": "Oregon Shelf", "latitude": 44.63718, "longitude": -124.30565, "scope": "published COSZO output"},
    ],
}

HYS14_CHRONFIX_TARGET = {
    "network": "OO",
    "station": "HYS14",
    "instrument": "OOI Hydrate Ridge ocean-bottom seismometer (OBS)",
    "instrument_id": "OO.HYS14.OBS",
    "derivation_and_validation_stream": "OO.HYS14..MHZ",
    "derivation_and_validation_channel": "MHZ",
    "channel_description": "The model was derived and validated with the 8 Hz vertical MHZ stream.",
    "applicable_channels": "All channels recorded by the same HYS14 OBS instrument clock, including other seismic channels such as BHZ or HHZ.",
    "scope": "One instrument clock model. PREST, VEL3D, and other HYS14 instruments are independent and must not be shifted with this model.",
}

REFDES_RE = re.compile(r"(RS\d{2}[A-Z0-9]{4}-[A-Z0-9]+-\d{2}-[A-Z0-9]+)", re.I)
SITE_RE = re.compile(r"(?<![A-Z0-9])(RS\d{2}[A-Z0-9]{4})(?![A-Z0-9])", re.I)
DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)(?!\d)")
ISO_TIME_RE = re.compile(r"20\d{2}-[01]\d-[0-3]\d[T ][0-2]\d:[0-5]\d(?::[0-6]\d(?:\.\d+)?)?(?:Z|[+-][0-2]\d:[0-5]\d)?")
HYS14_ALIASES = ("hys14", "rs01sum1", "hydrate summit", "southern hydrate summit")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    token = value.strip().replace(" ", "T")
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    parsed = datetime.fromisoformat(token)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _coerce_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [_coerce_scalar(item) for item in value]
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return None
    low = s.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        x = float(s)
        return x if math.isfinite(x) else None
    except ValueError:
        return s


def _station_from_path(path: str) -> str | None:
    match = REFDES_RE.search(path)
    if match:
        return match.group(1).upper()
    match = SITE_RE.search(path)
    return match.group(1).upper() if match else None


def _date_from_path(path: str) -> str | None:
    match = DATE_RE.search(path)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def _kind(path: Path) -> str:
    token = path.as_posix().lower()
    if "variability" in token and path.suffix.lower() == ".csv": return "temporal_variability_table"
    if "variability_stats" in token: return "temporal_variability_stats"
    if "variability_4panel" in token: return "temporal_variability_figure"
    if "diagnostic" in token and path.suffix.lower() in {".png", ".jpg", ".jpeg"}: return "timing_diagnostic_figure"
    if path.suffix.lower() == ".xml": return "stationxml"
    if path.suffix.lower() in {".mseed", ".ms"}: return "miniseed"
    if path.suffix.lower() == ".nc": return "netcdf"
    if path.name == "delta_t_hourly_clean.npy": return "clock_correction_array"
    if path.name == "hour_times.npy": return "clock_hour_array"
    if path.name == "trigger_periods.csv": return "clock_trigger_table"
    if "chronfix" in token and path.suffix.lower() == ".csv": return "clock_correction_table"
    if path.suffix.lower() == ".pdf" and "dive" in token: return "dive_index_report"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}: return "figure"
    if path.suffix.lower() == ".csv": return "metrics_table"
    if path.suffix.lower() in {".txt", ".log"}: return "diagnostic_text"
    return "output_artifact"


class CoszoHubToolkit:
    """Queries growing output directories and exposes bounded calculations."""

    def __init__(
        self,
        repository_root: str | Path | None = None,
        index_path: str | Path | None = None,
        cache_dir: str | Path | None = None,
        roots: dict[str, str | Path] | None = None,
        ooi_m2m_toolkit: OOIM2MToolkit | None = None,
        earthscope_toolkit: EarthScopeFDSNToolkit | None = None,
        pi_portal_toolkit: PIPortalToolkit | None = None,
    ) -> None:
        project = Path(__file__).resolve().parents[2]
        self.repository_root = Path(repository_root or os.getenv("COSZO_HUB_REPOSITORY_ROOT", project / "source_material" / "repositories" / "coszo-hub")).resolve()
        self.index_path = Path(index_path or os.getenv("COSZO_HUB_INDEX_PATH", project / "runtime_data" / "COSZOHub" / "output_index.sqlite")).resolve()
        self.cache_dir = Path(cache_dir or os.getenv("COSZO_HUB_CACHE_DIR", project / "runtime_data" / "COSZOHub" / "cache")).resolve()
        self.chronfix_refresh_ttl_seconds = max(0, int(os.getenv("COSZO_CHRONFIX_REFRESH_TTL_SECONDS", "300")))
        self._last_chronfix_refresh_monotonic: float | None = None
        self._last_chronfix_refresh_result: dict | None = None
        self.ooi_m2m = ooi_m2m_toolkit or OOIM2MToolkit()
        self.earthscope = earthscope_toolkit or EarthScopeFDSNToolkit()
        self.pi_portal = pi_portal_toolkit or PIPortalToolkit()
        supplied = roots or {}
        self.roots: dict[str, Path] = {}
        for name, meta in SUPPORTED_REPOSITORIES.items():
            configured = supplied.get(name) or os.getenv(str(meta["env"]))
            root = Path(configured) if configured else self.repository_root / name / str(meta["output_subdir"])
            self.roots[name] = root.resolve()
        self._init_db()

    def _init_db(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.index_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS files (
                repository TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                extension TEXT,
                kind TEXT,
                station TEXT,
                observation_date TEXT,
                byte_size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                modified_at_utc TEXT NOT NULL,
                in_scope INTEGER NOT NULL,
                last_scan TEXT NOT NULL,
                PRIMARY KEY(repository, relative_path)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_files_query ON files(repository, kind, station, observation_date)")

    def _iter_files(self, root: Path) -> Iterable[Path]:
        if not root.exists():
            return []
        return (p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and p.name not in {".DS_Store"})

    def scan(self, repository: str | None = None) -> dict:
        names = [repository] if repository else list(SUPPORTED_REPOSITORIES)
        unknown = [x for x in names if x not in SUPPORTED_REPOSITORIES]
        if unknown:
            return error("unknown_repository", unknown[0], allowed=list(SUPPORTED_REPOSITORIES))
        scan_id = _utc_now()
        counts: dict[str, dict] = {}
        with sqlite3.connect(self.index_path) as db:
            for name in names:
                root = self.roots[name]
                seen: set[str] = set()
                if root.exists():
                    for path in self._iter_files(root):
                        rel = path.relative_to(root).as_posix()
                        stat = path.stat()
                        station = _station_from_path(rel)
                        in_scope = not (name == "sea-water-velocity" and station and station.startswith("CE"))
                        modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z")
                        db.execute("""INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(repository,relative_path) DO UPDATE SET
                            absolute_path=excluded.absolute_path, extension=excluded.extension,
                            kind=excluded.kind, station=excluded.station,
                            observation_date=excluded.observation_date, byte_size=excluded.byte_size,
                            mtime_ns=excluded.mtime_ns, modified_at_utc=excluded.modified_at_utc,
                            in_scope=excluded.in_scope, last_scan=excluded.last_scan""",
                            (name, rel, str(path), path.suffix.lower(), _kind(path), station,
                             _date_from_path(rel), stat.st_size, stat.st_mtime_ns, modified,
                             1 if in_scope else 0, scan_id))
                        seen.add(rel)
                db.execute("DELETE FROM files WHERE repository=? AND last_scan<>?", (name, scan_id))
                rows = db.execute("SELECT COUNT(*), COALESCE(SUM(byte_size),0), MAX(modified_at_utc) FROM files WHERE repository=?", (name,)).fetchone()
                counts[name] = {"root": str(root), "exists": root.exists(), "file_count": rows[0], "byte_size": rows[1], "newest_modified_at_utc": rows[2]}
            db.commit()
        return {"ok": True, "scan_time_utc": scan_id, "repositories": counts, "index_path": str(self.index_path)}

    def status(self, rescan: bool = True) -> dict:
        if rescan:
            self.scan()
        with sqlite3.connect(self.index_path) as db:
            db.row_factory = sqlite3.Row
            summary = {}
            for name in SUPPORTED_REPOSITORIES:
                rows = db.execute("SELECT kind, COUNT(*) n, COALESCE(SUM(byte_size),0) bytes, MAX(modified_at_utc) newest FROM files WHERE repository=? AND in_scope=1 GROUP BY kind", (name,)).fetchall()
                summary[name] = {"root": str(self.roots[name]), "exists": self.roots[name].exists(), "kinds": [dict(x) for x in rows], "file_count": sum(x["n"] for x in rows), "byte_size": sum(x["bytes"] for x in rows), "newest_modified_at_utc": max((x["newest"] for x in rows if x["newest"]), default=None)}
        return {"ok": True, "scope": "COSZO and RCA outputs; non-RCA VEL3D files excluded by default", "checked_at_utc": _utc_now(), "repositories": summary}

    def list_outputs(self, repository: str | None = None, station: str | None = None,
                     kind: str | None = None, start: str | None = None, end: str | None = None,
                     include_non_rca: bool = False, limit: int = 200,
                     newest_first: bool = True, rescan: bool = True) -> dict:
        if repository and repository not in SUPPORTED_REPOSITORIES:
            return error("unknown_repository", repository, allowed=list(SUPPORTED_REPOSITORIES))
        if rescan:
            result = self.scan(repository)
            if not result.get("ok"): return result
        where, values = ["1=1"], []
        if repository: where.append("repository=?"); values.append(repository)
        if station: where.append("LOWER(COALESCE(station,'')) LIKE ?"); values.append(f"%{station.lower()}%")
        if kind: where.append("kind=?"); values.append(kind)
        if start: where.append("COALESCE(observation_date,'')>=?"); values.append(start)
        if end: where.append("COALESCE(observation_date,'')<=?"); values.append(end)
        if not include_non_rca: where.append("in_scope=1")
        limit = max(1, min(int(limit), 2000))
        order = "modified_at_utc DESC, relative_path" if newest_first else "modified_at_utc, relative_path"
        with sqlite3.connect(self.index_path) as db:
            db.row_factory = sqlite3.Row
            total = db.execute(f"SELECT COUNT(*) FROM files WHERE {' AND '.join(where)}", values).fetchone()[0]
            rows = db.execute(f"SELECT repository,relative_path,kind,station,observation_date,byte_size,modified_at_utc FROM files WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?", [*values, limit]).fetchall()
        return {"ok": True, "total_matches": total, "returned": len(rows), "outputs": [dict(x) for x in rows], "index_refreshed": rescan, "checked_at_utc": _utc_now()}

    def _resolve(self, repository: str, relative_path: str) -> Path:
        if repository not in self.roots:
            raise ValueError(f"Unknown repository: {repository}")
        root = self.roots[repository]
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Path escapes configured output root")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def read_output(self, repository: str, relative_path: str, limit: int = 200) -> dict:
        try:
            path = self._resolve(repository, relative_path)
        except Exception as exc:
            return error(type(exc).__name__, str(exc))
        limit = max(1, min(int(limit), 1000))
        meta = self._artifact_meta(repository, path, relative_path)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8", errors="replace") as stream:
                reader = csv.DictReader(stream)
                rows = [{k: _coerce_scalar(v) for k, v in row.items()} for _, row in zip(range(limit), reader)]
                fields = reader.fieldnames or []
            meta.update({"ok": True, "format": "csv", "columns": fields, "rows": rows, "returned": len(rows), "truncated": path.stat().st_size > 0 and len(rows) == limit})
            return meta
        if suffix in {".txt", ".log", ".md", ".m"} or not suffix:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {**meta, "ok": True, "format": "text", "text": text[:200_000], "truncated": len(text) > 200_000}
        if suffix in {".json", ".jsonl"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            return {**meta, "ok": True, "format": suffix[1:], "text": text[:200_000], "truncated": len(text) > 200_000}
        return {**meta, "ok": True, "format": "binary", "guidance": "Use coszo_get_figure for image content; binary scientific files remain available at the artifact path."}

    def _artifact_meta(self, repository: str, path: Path, relative_path: str | None = None) -> dict:
        rel = relative_path or path.relative_to(self.roots[repository]).as_posix()
        payload = path.read_bytes() if path.stat().st_size <= 20_000_000 else b""
        return {
            "repository": repository,
            "relative_path": rel,
            "artifact_uri": path.resolve().as_uri(),
            "kind": _kind(path),
            "station": _station_from_path(rel),
            "observation_date": _date_from_path(rel),
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "byte_size": path.stat().st_size,
            "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z"),
            "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
            "commit_sha_at_packaging": SUPPORTED_REPOSITORIES[repository]["commit"],
        }

    def get_figure(self, repository: str, relative_path: str) -> dict:
        try:
            path = self._resolve(repository, relative_path)
        except Exception as exc:
            return error(type(exc).__name__, str(exc))
        suffix = path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"}:
            return error("not_an_image", "Expected PNG or JPEG", relative_path=relative_path)
        payload = path.read_bytes()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        return {"ok": True, **self._artifact_meta(repository, path, relative_path), "_mcp_image": {"mimeType": mime, "data": base64.b64encode(payload).decode("ascii")}}

    def find_diagnostic_figure(self, repository: str, station: str, day: str) -> dict:
        if repository not in {"absolute-seafloor-pressure", "sea-water-velocity"}:
            return error("invalid_repository", "Diagnostic figures are available for pressure and velocity outputs")
        self.scan(repository)
        with sqlite3.connect(self.index_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT relative_path FROM files
                WHERE repository=? AND station LIKE ? AND observation_date=?
                AND kind IN ('temporal_variability_figure','timing_diagnostic_figure','figure')
                ORDER BY relative_path LIMIT 20""", (repository, f"%{station.upper()}%", day)).fetchall()
        if not rows:
            return error("figure_not_found", "No matching figure in the current output tree", repository=repository, station=station, day=day)
        return self.get_figure(repository, rows[0]["relative_path"])

    def metric_rows(self, repository: str, station: str | None = None,
                    start: str | None = None, end: str | None = None,
                    gaps_only: bool = False, has_data_only: bool = False,
                    limit: int = 500, newest_first: bool = False) -> dict:
        if repository not in {"absolute-seafloor-pressure", "sea-water-velocity"}:
            return error("invalid_repository", "Metrics are available for pressure and velocity")
        root = self.roots[repository]
        candidates = sorted(root.rglob("*variability.csv")) if root.exists() else []
        rows: list[dict] = []
        for path in candidates:
            with path.open(newline="", encoding="utf-8", errors="replace") as stream:
                for raw in csv.DictReader(stream):
                    item = {k: _coerce_scalar(v) for k, v in raw.items()}
                    st = str(item.get("station") or "")
                    day = str(item.get("date") or "")
                    if station and station.lower() not in st.lower() and station.lower() not in path.name.lower(): continue
                    if start and day < start: continue
                    if end and day > end: continue
                    if gaps_only and not ((item.get("n_gaps") or 0) > 0): continue
                    if has_data_only and item.get("has_data") is not True: continue
                    item.update({"repository": repository, "source_relative_path": path.relative_to(root).as_posix(), "commit_sha_at_packaging": SUPPORTED_REPOSITORIES[repository]["commit"]})
                    rows.append(item)
        rows.sort(key=lambda x: str(x.get("date") or ""), reverse=newest_first)
        limit = max(1, min(int(limit), 100_000))
        return {"ok": True, "repository": repository, "total_matches": len(rows), "returned": min(limit, len(rows)), "rows": rows[:limit], "output_root": str(root), "checked_at_utc": _utc_now()}

    def metric_summary(self, repository: str, station: str | None = None,
                       start: str | None = None, end: str | None = None) -> dict:
        result = self.metric_rows(repository, station, start, end, limit=100_000)
        if not result.get("ok"): return result
        rows = result["rows"]
        has_data = [r for r in rows if r.get("has_data") is True]
        gap_days = [r for r in has_data if (r.get("n_gaps") or 0) > 0]
        unstable = [r for r in has_data if r.get("jitter_unstable") is True]
        return {
            "ok": True, "repository": repository, "station_query": station,
            "start": start, "end": end, "days_in_table": len(rows),
            "days_with_data": len(has_data), "days_with_corrected_gaps": len(gap_days),
            "days_jitter_unstable": len(unstable),
            "total_missing_samples": int(sum(int(r.get("true_missing") or 0) for r in has_data)),
            "date_coverage": [min((str(r.get("date")) for r in rows), default=None), max((str(r.get("date")) for r in rows), default=None)],
            "latest_row": max(rows, key=lambda r: str(r.get("date") or ""), default=None),
            "output_root": result["output_root"], "checked_at_utc": _utc_now(),
        }

    def list_stations(self) -> dict:
        return {"ok": True, "pressure": PRESSURE_STATIONS, "velocity_rca": VELOCITY_STATIONS, "scope": "RCA instruments present in the COSZO Hub output pipelines"}

    def detect_pressure_gaps(self, timestamps_seconds: list[float], nominal_sample_period_seconds: float,
                             algorithm: str = "anomaly", request_duration_seconds: float | None = None) -> dict:
        if len(timestamps_seconds) < 2:
            return error("insufficient_samples", "At least two timestamps are required")
        if len(timestamps_seconds) > 2_000_000:
            return error("too_many_samples", "Maximum 2,000,000 timestamps per call")
        if nominal_sample_period_seconds <= 0:
            return error("invalid_sample_period", "nominal_sample_period_seconds must be positive")
        if algorithm not in {"legacy", "anomaly"}:
            return error("invalid_algorithm", "algorithm must be legacy or anomaly")
        try:
            value = run_gap_detector(
                timestamps_seconds, float(nominal_sample_period_seconds),
                algorithm=algorithm, request_duration_seconds=request_duration_seconds,
                max_samples=2_000_000,
            )
            result = value.to_dict()
            result.update({"ok": True, "source_algorithm": "pure-Python parity port of upstream PREST gap_algorithms.py", "source_commit": SUPPORTED_REPOSITORIES["absolute-seafloor-pressure"]["commit"]})
            return result
        except Exception as exc:
            return error(type(exc).__name__, str(exc))

    def refresh_hys14_correction(self, force: bool = False) -> dict:
        """Refresh the correction source, or report a directly mounted live tree."""
        root = self.roots["chronfix"]
        configured_live = bool(os.getenv("COSZO_CHRONFIX_OUTPUT_ROOT"))
        if configured_live:
            return {"ok": True, "mode": "mounted_live_directory", "updated": None,
                    "correction_root": str(root), "checked_at_utc": _utc_now(),
                    "guidance": "Files are read directly on every correction call; no repository pull is needed."}
        now = time.monotonic()
        if (not force and self._last_chronfix_refresh_monotonic is not None
                and now - self._last_chronfix_refresh_monotonic < self.chronfix_refresh_ttl_seconds
                and self._last_chronfix_refresh_result is not None):
            return {**self._last_chronfix_refresh_result, "mode": "refresh_ttl_cache",
                    "cache_age_seconds": round(now - self._last_chronfix_refresh_monotonic, 3)}
        repo = self.repository_root / "chronfix"
        if not (repo / ".git").exists():
            result = {"ok": True, "mode": "local_snapshot", "updated": False,
                      "correction_root": str(root), "checked_at_utc": _utc_now(),
                      "refresh_warning": "Chronfix source is not a Git checkout; reading the current local bundle."}
        else:
            try:
                before = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=20).strip()
                run = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"], capture_output=True, text=True, timeout=180)
                after = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=20).strip()
                if run.returncode == 0:
                    result = {"ok": True, "mode": "git_fast_forward", "updated": before != after,
                              "before_commit": before, "after_commit": after,
                              "git_output": run.stdout.strip(), "correction_root": str(root),
                              "checked_at_utc": _utc_now()}
                else:
                    result = {"ok": True, "mode": "snapshot_fallback", "updated": False,
                              "before_commit": before, "after_commit": after,
                              "refresh_warning": run.stderr.strip() or run.stdout.strip(),
                              "correction_root": str(root), "checked_at_utc": _utc_now()}
            except Exception as exc:
                result = {"ok": True, "mode": "snapshot_fallback", "updated": False,
                          "refresh_warning": str(exc), "correction_root": str(root),
                          "checked_at_utc": _utc_now()}
        self._last_chronfix_refresh_monotonic = now
        self._last_chronfix_refresh_result = result
        return result

    @staticmethod
    def _correction_file_metadata(paths: list[Path]) -> list[dict]:
        rows = []
        for path in paths:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({"name": path.name, "path": str(path), "byte_size": stat.st_size,
                         "mtime_ns": stat.st_mtime_ns,
                         "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
                         "sha256": digest})
        return rows

    def chronfix_model(self, query_times: list[str] | None = None,
                       refresh: bool = True, force_refresh: bool = False) -> dict:
        root = self.roots["chronfix"]
        try:
            import numpy as np
            refresh_result = self.refresh_hys14_correction(force=force_refresh) if refresh else {"ok": True, "mode": "refresh_disabled"}
            required_paths = [root / "hour_times.npy", root / "delta_t_hourly_clean.npy", root / "trigger_periods.csv"]
            for path in required_paths:
                if not path.is_file():
                    return error("correction_file_missing", str(path), correction_root=str(root), refresh=refresh_result)
            stable = False
            for _attempt in range(2):
                before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in required_paths]
                hours = np.load(required_paths[0], allow_pickle=False)
                delta = np.load(required_paths[1], allow_pickle=False).astype(float)
                with required_paths[2].open(newline="", encoding="utf-8") as stream:
                    triggers = list(csv.DictReader(stream))
                after = [(p.stat().st_size, p.stat().st_mtime_ns) for p in required_paths]
                if before == after:
                    stable = True
                    break
            if not stable:
                return error("correction_bundle_changing", "Chronfix files changed during both read attempts; retry after the writer completes", correction_root=str(root))
            file_metadata = self._correction_file_metadata(required_paths)
            bundle_fingerprint = hashlib.sha256("".join(x["sha256"] for x in file_metadata).encode()).hexdigest()
            trigger_windows = []
            for row in triggers:
                try:
                    i0, i1 = int(row["start_index"]), int(row["end_index"])
                    trigger_windows.append({
                        **{k: _coerce_scalar(v) for k, v in row.items()},
                        "start_time_utc": str(hours[i0].astype("datetime64[s]")) + "Z",
                        "end_time_utc": str(hours[i1].astype("datetime64[s]")) + "Z",
                    })
                except Exception:
                    trigger_windows.append({k: _coerce_scalar(v) for k, v in row.items()})
            valid = np.isfinite(delta)
            result: dict[str, Any] = {
                "ok": True, "station": "HYS14", "target": HYS14_CHRONFIX_TARGET, "n_hours": int(len(hours)),
                "n_valid": int(valid.sum()), "n_missing": int((~valid).sum()),
                "n_trigger_periods": len(triggers),
                "coverage_start": str(hours[0]) if len(hours) else None,
                "coverage_end": str(hours[-1]) if len(hours) else None,
                "delta_t_seconds_min": float(np.nanmin(delta)) if valid.any() else None,
                "delta_t_seconds_max": float(np.nanmax(delta)) if valid.any() else None,
                "trigger_periods": trigger_windows[:200], "output_root": str(root),
                "source_commit": refresh_result.get("after_commit") or SUPPORTED_REPOSITORIES["chronfix"]["commit"],
                "refresh": refresh_result, "correction_files": file_metadata,
                "bundle_fingerprint_sha256": bundle_fingerprint,
                "model_read_at_utc": _utc_now(),
            }
            if query_times:
                if len(query_times) > 1000: return error("too_many_query_times", "Maximum 1000")
                hsec = hours.astype("datetime64[s]").astype("int64")
                normalized_times = [_parse_utc(t).replace(tzinfo=None).isoformat() for t in query_times]
                q = np.asarray(normalized_times, dtype="datetime64[s]")
                qsec = q.astype("int64")
                vals = np.interp(qsec, hsec[valid], delta[valid], left=np.nan, right=np.nan)
                for trig in triggers:
                    try:
                        i0, i1 = int(trig["start_index"]), int(trig["end_index"])
                        vals[(q >= hours[i0].astype("datetime64[s]")) & (q <= hours[i1].astype("datetime64[s]"))] = np.nan
                    except Exception:
                        continue
                queries = []
                for t, v in zip(query_times, vals):
                    delta = None if not math.isfinite(float(v)) else float(v)
                    corrected = None
                    if delta is not None:
                        try:
                            corrected = _iso_utc(_parse_utc(t) - timedelta(seconds=delta))
                        except Exception:
                            corrected = None
                    queries.append({"apparent_time": t, "delta_t_seconds": delta,
                                    "corrected_true_utc": corrected,
                                    "correction": "true UTC = apparent time - delta_t"})
                result["queries"] = queries
            return result
        except Exception as exc:
            return error(type(exc).__name__, str(exc), output_root=str(root))

    @staticmethod
    def _mentions_hys14(question: str) -> bool:
        token = question.casefold()
        return any(alias in token for alias in HYS14_ALIASES)

    def hys14_correct_times(self, apparent_times: list[str], target_instrument: str,
                            channel: str | None = None) -> dict:
        """Correct apparent timestamps for any channel on the HYS14 OBS clock."""
        if not apparent_times:
            return error("missing_times", "At least one apparent HYS14 timestamp is required")
        if len(apparent_times) > 1000:
            return error("too_many_times", "Maximum 1000 timestamps per call")
        if target_instrument.upper() != HYS14_CHRONFIX_TARGET["instrument_id"]:
            return error(
                "wrong_instrument",
                "The bundled Chronfix model applies only to channels recorded by the OO.HYS14 OBS instrument clock.",
                requested_target_instrument=target_instrument,
                validated_target=HYS14_CHRONFIX_TARGET,
            )
        if channel is not None and not re.fullmatch(r"[A-Z0-9]{3}", channel.upper()):
            return error("invalid_channel", "channel must be a three-character SEED channel code", supplied=channel)
        model = self.chronfix_model(apparent_times)
        if not model.get("ok"):
            return model
        windows = model.get("trigger_periods", [])
        corrected = []
        for row in model.get("queries", []):
            apparent = row["apparent_time"]
            in_trigger = False
            try:
                point = _parse_utc(apparent)
                for window in windows:
                    if window.get("start_time_utc") and _parse_utc(str(window["start_time_utc"])) <= point <= _parse_utc(str(window["end_time_utc"])):
                        in_trigger = True
                        break
            except Exception:
                pass
            if row.get("delta_t_seconds") is not None:
                status = "corrected"
                action = "Use corrected_true_utc for time-dependent analysis."
            elif in_trigger:
                status = "trigger_interval"
                action = "Do not interpolate across this clock discontinuity; split or exclude the trace interval."
            else:
                status = "outside_model_or_missing"
                action = "Do not estimate a shift outside valid model coverage."
            corrected.append({**row, "in_trigger_interval": in_trigger, "status": status, "action": action})
        return {
            "ok": True, "target": {**HYS14_CHRONFIX_TARGET, "requested_channel": channel.upper() if channel else None},
            "input_time_semantics": "Apparent timestamps assigned by the OO.HYS14 OBS instrument clock",
            "formula": "corrected true UTC = apparent HYS14 time - delta_t(apparent time)",
            "coverage_start": model.get("coverage_start"), "coverage_end": model.get("coverage_end"),
            "corrections": corrected, "source_commit": model.get("source_commit"),
            "channel_scope": "MHZ supplied the correction evidence, but the fitted clock error applies to all channels sharing this OBS clock.",
            "warning": "This is one OBS instrument correction. Preserve already-corrected UTC and all independent PREST, VEL3D, and other-instrument timestamps.",
        }

    def hys14_clock_context(self, question: str | None = None, day: str | None = None,
                            apparent_times: list[str] | None = None,
                            target_instrument: str | None = None,
                            channel: str | None = None) -> dict:
        """Return the clock evidence that must accompany any HYS14 answer."""
        exact_times = list(apparent_times or [])
        if question:
            exact_times.extend(match.group(0).replace(" ", "T") for match in ISO_TIME_RE.finditer(question))
            if day is None:
                found = DATE_RE.search(question)
                if found:
                    day = f"{found.group(1)}-{found.group(2)}-{found.group(3)}"
        # Preserve caller order but remove duplicate times extracted from text.
        exact_times = list(dict.fromkeys(exact_times))
        model = self.chronfix_model(exact_times or None)
        if not model.get("ok"):
            return model
        q = (question or "").casefold()
        explicitly_unaffected = any(term in q for term in ("prest", "pressure", "vel3d", "current meter", "water velocity"))
        explicitly_affected = any(term in q for term in ("mhz", "bhz", "bhn", "bhe", "hhz", "hhn", "hhe", "ehz", "obs", "seismic", "seismometer", "earthquake", "waveform"))
        if target_instrument:
            applicability = "affected_instrument" if target_instrument.upper() == HYS14_CHRONFIX_TARGET["instrument_id"] else "different_instrument"
        elif explicitly_unaffected:
            applicability = "different_instrument"
        elif explicitly_affected:
            applicability = "affected_instrument_likely; MHZ-derived correction applies to all channels sharing the HYS14 OBS clock"
        else:
            applicability = "instrument_unspecified"
        result: dict[str, Any] = {
            "ok": True, "target": HYS14_CHRONFIX_TARGET, "aliases": list(HYS14_ALIASES),
            "applicability": applicability,
            "chronfix_required_only_for_this_obs_clock": True,
            "model_coverage": [model.get("coverage_start"), model.get("coverage_end")],
            "trigger_count": model.get("n_trigger_periods"),
            "routing_rule": "For HYS14 OBS seismic evidence, check Chronfix before answering. Correct apparent times on any channel sharing the HYS14 OBS clock when the model is valid; never interpolate through a trigger window.",
            "scope_rule": "For general HYS14 questions, disclose that one OBS instrument has a known clock correction. Never apply it to PREST, VEL3D, another instrument, or already-corrected UTC.",
            "source_commit": model.get("source_commit"),
        }
        should_apply = bool(exact_times) and (
            (target_instrument and target_instrument.upper() == HYS14_CHRONFIX_TARGET["instrument_id"])
            or (not target_instrument and explicitly_affected and not explicitly_unaffected)
        )
        if should_apply:
            corrected = self.hys14_correct_times(exact_times, HYS14_CHRONFIX_TARGET["instrument_id"], channel=channel)
            result["timestamp_corrections"] = corrected.get("corrections", [])
        elif exact_times:
            result["timestamp_corrections"] = []
            result["correction_not_applied_reason"] = "The question does not identify data from the affected HYS14 OBS instrument. The model is disclosed but unrelated instrument timestamps are left unchanged."
        if day:
            try:
                import numpy as np
                root = self.roots["chronfix"]
                hours = np.load(root / "hour_times.npy").astype("datetime64[s]")
                delta = np.load(root / "delta_t_hourly_clean.npy").astype(float)
                start = np.datetime64(day, "s")
                end = start + np.timedelta64(1, "D")
                mask = (hours >= start) & (hours < end) & np.isfinite(delta)
                values = delta[mask]
                windows = [w for w in model.get("trigger_periods", []) if w.get("start_time_utc") and str(w["start_time_utc"])[:10] <= day <= str(w["end_time_utc"])[:10]]
                result["day_context"] = {
                    "day_utc": day, "valid_hourly_corrections": int(len(values)),
                    "delta_t_seconds_min": float(values.min()) if len(values) else None,
                    "delta_t_seconds_median": float(np.median(values)) if len(values) else None,
                    "delta_t_seconds_max": float(values.max()) if len(values) else None,
                    "trigger_windows": windows,
                    "applies_to": HYS14_CHRONFIX_TARGET,
                    "formula": "corrected true UTC = apparent HYS14 OBS time - delta_t",
                }
            except Exception as exc:
                result["day_context_error"] = str(exc)
        return result

    def dive_index_config(self) -> dict:
        return {"ok": True, **DIVE_CONFIG, "repository_root": str(self.roots["dive-index-hindcast"]), "source_commit": SUPPORTED_REPOSITORIES["dive-index-hindcast"]["commit"]}

    def compute_dive_index(self, significant_wave_height_m: float,
                           wind_speed_mps: float | None = None,
                           u10_mps: float | None = None, v10_mps: float | None = None) -> dict:
        if significant_wave_height_m < 0:
            return error("invalid_wave_height", "significant_wave_height_m must be nonnegative")
        if wind_speed_mps is None:
            if u10_mps is None or v10_mps is None:
                return error("missing_wind", "Supply wind_speed_mps or both u10_mps and v10_mps")
            wind_speed_mps = math.hypot(float(u10_mps), float(v10_mps))
        if wind_speed_mps < 0:
            return error("invalid_wind_speed", "wind speed must be nonnegative")
        knots = float(wind_speed_mps) * 1.943844492
        value = float(significant_wave_height_m) * knots
        return {"ok": True, "significant_wave_height_m": float(significant_wave_height_m), "wind_speed_mps": float(wind_speed_mps), "wind_speed_knots": knots, "dive_index": value, "below_threshold_40": value < 40, "below_threshold_70": value < 70, "formula": DIVE_CONFIG["formula"], "source_commit": SUPPORTED_REPOSITORIES["dive-index-hindcast"]["commit"]}

    def dive_index_page(self, page: int = 1) -> dict:
        if page < 1 or page > 200:
            return error("invalid_page", "page must be between 1 and 200")
        root = self.roots["dive-index-hindcast"]
        pdfs = sorted(root.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not pdfs:
            return error("report_not_found", "No Dive Index PDF in the current output root", output_root=str(root))
        pdf = pdfs[0]
        if not shutil.which("pdftoppm"):
            return error("renderer_missing", "pdftoppm is required to render Dive Index report pages")
        cache = self.cache_dir / "dive-index-pages" / f"{pdf.stat().st_mtime_ns}-{page:03d}.png"
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            prefix = cache.with_suffix("")
            run = subprocess.run(["pdftoppm", "-f", str(page), "-singlefile", "-png", "-r", "130", str(pdf), str(prefix)], capture_output=True, text=True, timeout=120)
            if run.returncode != 0 or not cache.exists():
                return error("render_failed", run.stderr.strip() or "pdftoppm did not produce an image", page=page)
        payload = cache.read_bytes()
        return {"ok": True, "page": page, "report": pdf.name, "report_modified_at_utc": datetime.fromtimestamp(pdf.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z"), "source_pdf_uri": pdf.resolve().as_uri(), "byte_size": len(payload), "_mcp_image": {"mimeType": "image/png", "data": base64.b64encode(payload).decode("ascii")}}

    def collection_readiness(self, repository: str) -> dict:
        if repository not in {"absolute-seafloor-pressure", "sea-water-velocity"}:
            return error("invalid_repository", "Collection readiness applies to pressure and velocity pipelines")
        repo = self.repository_root / repository
        subdir = "PREST-data-collection" if repository == "absolute-seafloor-pressure" else "VEL3D-data-collection"
        wrapper = repo / subdir / "bin" / "run_ooi_requests.sh"
        required = ["OOI_USERNAME", "OOI_TOKEN"]
        credentials = {name: bool(os.getenv(name)) for name in required}
        return {"ok": True, "repository": repository, "wrapper": str(wrapper), "wrapper_exists": wrapper.exists(), "credentials_configured": credentials, "ready_for_ooi_collection": wrapper.exists() and all(credentials.values()), "live_outputs_visible_without_credentials": self.roots[repository].exists(), "output_root": str(self.roots[repository]), "guidance": "Queries of existing outputs are credential-free. OOI M2M collection requires OOI_USERNAME and OOI_TOKEN and the upstream runtime dependencies."}

    def sync_repository(self, repository: str) -> dict:
        if repository not in SUPPORTED_REPOSITORIES:
            return error("unknown_repository", repository, allowed=list(SUPPORTED_REPOSITORIES))
        repo = self.repository_root / repository
        if not (repo / ".git").exists():
            return error("not_a_git_checkout", "Configured repository snapshot has no .git directory", path=str(repo))
        try:
            before = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=20).strip()
            run = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"], capture_output=True, text=True, timeout=180)
            if run.returncode != 0:
                return error("git_pull_failed", run.stderr.strip() or run.stdout.strip(), repository=repository)
            after = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=20).strip()
            scan = self.scan(repository)
            return {"ok": True, "repository": repository, "before_commit": before, "after_commit": after, "updated": before != after, "git_output": run.stdout.strip(), "scan": scan, "checked_at_utc": _utc_now()}
        except Exception as exc:
            return error(type(exc).__name__, str(exc), repository=repository)

    def question_context(self, question: str, limit: int = 100) -> dict:
        q = question.casefold()
        hys14 = self._mentions_hys14(question)
        if any(x in q for x in ["velocity", "vel3d", "current meter"]): repo = "sea-water-velocity"
        elif any(x in q for x in ["pressure", "prest", "seafloor"]): repo = "absolute-seafloor-pressure"
        elif any(x in q for x in ["clock", "chronfix", "timing correction"]): repo = "chronfix"
        elif any(x in q for x in ["dive index", "rov", "wave", "weather"]): repo = "dive-index-hindcast"
        else: repo = None
        station_match = REFDES_RE.search(question) or SITE_RE.search(question)
        station = station_match.group(1).upper() if station_match else ("RS01SUM1" if hys14 else None)
        dates = [f"{y}-{m}-{d}" for y, m, d in DATE_RE.findall(question)]
        outputs = self.list_outputs(repo, station=station, start=dates[0] if dates else None, end=dates[-1] if dates else None, limit=limit)
        summary = self.metric_summary(repo, station, dates[0] if dates else None, dates[-1] if dates else None) if repo in {"absolute-seafloor-pressure", "sea-water-velocity"} else None
        hys_context = self.hys14_clock_context(question=question) if hys14 else None
        guidance = ["Use live output tools for time-sensitive results.", "Cite output modified times and observation dates.", "Use the Graph-RAG corpus for stable scientific context and lineage."]
        if hys14:
            guidance.insert(0, "HYS14 detected: one OBS instrument has a Chronfix model derived on MHZ. Apply it to any channel sharing that OBS clock; leave PREST, VEL3D, and other instruments unchanged.")
        return {"ok": True, "question": question, "resolved_repository": repo, "resolved_station": station, "resolved_dates": dates, "hys14_clock_context": hys_context, "outputs": outputs, "metric_summary": summary, "guidance": guidance}


TOOL_SCHEMAS = [
    {"name":"coszo_output_status","description":"Rescan all configured COSZO Hub output directories and report current contents and newest files.","inputSchema":{"type":"object","properties":{"rescan":{"type":"boolean","default":True}}}},
    {"name":"coszo_list_outputs","description":"Incrementally rescan and list current COSZO/RCA output artifacts, including files added after the Graph-RAG corpus was built.","inputSchema":{"type":"object","properties":{"repository":{"type":"string","enum":list(SUPPORTED_REPOSITORIES)},"station":{"type":"string"},"kind":{"type":"string"},"start":{"type":"string","format":"date"},"end":{"type":"string","format":"date"},"include_non_rca":{"type":"boolean","default":False},"limit":{"type":"integer","default":200},"newest_first":{"type":"boolean","default":True},"rescan":{"type":"boolean","default":True}}}},
    {"name":"coszo_read_output","description":"Read a bounded CSV/text output from an allowlisted repository output tree.","inputSchema":{"type":"object","required":["repository","relative_path"],"properties":{"repository":{"type":"string","enum":list(SUPPORTED_REPOSITORIES)},"relative_path":{"type":"string"},"limit":{"type":"integer","default":200}}}},
    {"name":"coszo_get_figure","description":"Return a PNG/JPEG output figure as MCP image content.","inputSchema":{"type":"object","required":["repository","relative_path"],"properties":{"repository":{"type":"string","enum":list(SUPPORTED_REPOSITORIES)},"relative_path":{"type":"string"}}}},
    {"name":"coszo_find_diagnostic_figure","description":"Find and return a pressure or velocity diagnostic figure for a station and UTC day.","inputSchema":{"type":"object","required":["repository","station","day"],"properties":{"repository":{"type":"string","enum":["absolute-seafloor-pressure","sea-water-velocity"]},"station":{"type":"string"},"day":{"type":"string","format":"date"}}}},
    {"name":"coszo_metric_rows","description":"Query current per-day temporal-variability rows from growing pressure or velocity CSV outputs.","inputSchema":{"type":"object","required":["repository"],"properties":{"repository":{"type":"string","enum":["absolute-seafloor-pressure","sea-water-velocity"]},"station":{"type":"string"},"start":{"type":"string","format":"date"},"end":{"type":"string","format":"date"},"gaps_only":{"type":"boolean","default":False},"has_data_only":{"type":"boolean","default":False},"limit":{"type":"integer","default":500},"newest_first":{"type":"boolean","default":False}}}},
    {"name":"coszo_metric_summary","description":"Summarize data coverage, corrected gaps, missing samples, and timing instability from current pressure or velocity outputs.","inputSchema":{"type":"object","required":["repository"],"properties":{"repository":{"type":"string","enum":["absolute-seafloor-pressure","sea-water-velocity"]},"station":{"type":"string"},"start":{"type":"string","format":"date"},"end":{"type":"string","format":"date"}}}},
    {"name":"coszo_list_stations","description":"List RCA pressure and velocity stations, reference designators, channels, and sites represented by the COSZO pipelines.","inputSchema":{"type":"object","properties":{}}},
    {"name":"coszo_pressure_detect_gaps","description":"Run the upstream COSZO PREST legacy or anomaly gap detector on supplied epoch-second timestamps.","inputSchema":{"type":"object","required":["timestamps_seconds","nominal_sample_period_seconds"],"properties":{"timestamps_seconds":{"type":"array","items":{"type":"number"},"minItems":2},"nominal_sample_period_seconds":{"type":"number","exclusiveMinimum":0},"algorithm":{"type":"string","enum":["legacy","anomaly"],"default":"anomaly"},"request_duration_seconds":{"type":"number","exclusiveMinimum":0}}}},
    {"name":"coszo_refresh_hys14_correction","description":"Refresh the public Chronfix checkout with a fast-forward pull, or report that a configured live correction directory is read directly.","inputSchema":{"type":"object","properties":{"force":{"type":"boolean","default":False}}}},
    {"name":"coszo_chronfix_model","description":"Refresh and inspect the current HYS14 Chronfix correction bundle, return its file fingerprint, and interpolate clock corrections at requested times.","inputSchema":{"type":"object","properties":{"query_times":{"type":"array","items":{"type":"string","format":"date-time"},"maxItems":1000},"refresh":{"type":"boolean","default":True},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"coszo_hys14_correct_times","description":"Convert apparent timestamps from any channel sharing the OO.HYS14 OBS instrument clock to true UTC. MHZ derived and validated the model; other channels on the same instrument use the same clock correction.","inputSchema":{"type":"object","required":["apparent_times","target_instrument"],"properties":{"apparent_times":{"type":"array","items":{"type":"string","format":"date-time"},"minItems":1,"maxItems":1000},"target_instrument":{"type":"string","enum":["OO.HYS14.OBS"]},"channel":{"type":"string","pattern":"^[A-Z0-9]{3}$"}}}},
    {"name":"coszo_hys14_clock_context","description":"Disclose the single HYS14 OBS clock correction for any HYS14 question; apply shifts to any channel on that OBS instrument while excluding PREST, VEL3D, and other instruments.","inputSchema":{"type":"object","properties":{"question":{"type":"string"},"day":{"type":"string","format":"date"},"apparent_times":{"type":"array","items":{"type":"string","format":"date-time"},"maxItems":1000},"target_instrument":{"type":"string","enum":["OO.HYS14.OBS"]},"channel":{"type":"string","pattern":"^[A-Z0-9]{3}$"}}}},
    {"name":"coszo_dive_index_config","description":"Return the published COSZO Dive Index formula, sites, thresholds, persistence windows, and hindcast period.","inputSchema":{"type":"object","properties":{}}},
    {"name":"coszo_compute_dive_index","description":"Compute Dive Index from significant wave height and 10-m wind speed or U/V components.","inputSchema":{"type":"object","required":["significant_wave_height_m"],"properties":{"significant_wave_height_m":{"type":"number","minimum":0},"wind_speed_mps":{"type":"number","minimum":0},"u10_mps":{"type":"number"},"v10_mps":{"type":"number"}}}},
    {"name":"coszo_dive_index_page","description":"Render and return a page from the newest Dive Index output PDF, so updated plots can be used in answers.","inputSchema":{"type":"object","properties":{"page":{"type":"integer","minimum":1,"default":1}}}},
    {"name":"coszo_collection_readiness","description":"Check whether a pressure or velocity OOI collection pipeline has its code and future credentials configured; existing outputs remain queryable without credentials.","inputSchema":{"type":"object","required":["repository"],"properties":{"repository":{"type":"string","enum":["absolute-seafloor-pressure","sea-water-velocity"]}}}},
    {"name":"coszo_sync_repository","description":"Fast-forward one allowlisted public COSZO Hub checkout and immediately rescan its growing outputs.","inputSchema":{"type":"object","required":["repository"],"properties":{"repository":{"type":"string","enum":list(SUPPORTED_REPOSITORIES)}}}},
    {"name":"coszo_question_context","description":"Resolve a natural-language question to the relevant COSZO repository, output files, dates, station, and metric summary.","inputSchema":{"type":"object","required":["question"],"properties":{"question":{"type":"string"},"limit":{"type":"integer","default":100}}}},
] + OOI_M2M_TOOL_SCHEMAS + EARTHSCOPE_TOOL_SCHEMAS + PI_PORTAL_TOOL_SCHEMAS


def dispatch(toolkit: CoszoHubToolkit, name: str, arguments: dict) -> dict:
    if name.startswith("pi_portal_"):
        return dispatch_pi_portal(toolkit.pi_portal, name, arguments)
    if name.startswith("earthscope_"):
        return dispatch_earthscope(toolkit.earthscope, name, arguments)
    if name.startswith("ooi_m2m_"):
        return dispatch_ooi_m2m(toolkit.ooi_m2m, name, arguments)
    calls = {
        "coszo_output_status": lambda: toolkit.status(**arguments),
        "coszo_list_outputs": lambda: toolkit.list_outputs(**arguments),
        "coszo_read_output": lambda: toolkit.read_output(**arguments),
        "coszo_get_figure": lambda: toolkit.get_figure(**arguments),
        "coszo_find_diagnostic_figure": lambda: toolkit.find_diagnostic_figure(**arguments),
        "coszo_metric_rows": lambda: toolkit.metric_rows(**arguments),
        "coszo_metric_summary": lambda: toolkit.metric_summary(**arguments),
        "coszo_list_stations": lambda: toolkit.list_stations(),
        "coszo_pressure_detect_gaps": lambda: toolkit.detect_pressure_gaps(**arguments),
        "coszo_refresh_hys14_correction": lambda: toolkit.refresh_hys14_correction(**arguments),
        "coszo_chronfix_model": lambda: toolkit.chronfix_model(**arguments),
        "coszo_hys14_correct_times": lambda: toolkit.hys14_correct_times(**arguments),
        "coszo_hys14_clock_context": lambda: toolkit.hys14_clock_context(**arguments),
        "coszo_dive_index_config": lambda: toolkit.dive_index_config(),
        "coszo_compute_dive_index": lambda: toolkit.compute_dive_index(**arguments),
        "coszo_dive_index_page": lambda: toolkit.dive_index_page(**arguments),
        "coszo_collection_readiness": lambda: toolkit.collection_readiness(**arguments),
        "coszo_sync_repository": lambda: toolkit.sync_repository(**arguments),
        "coszo_question_context": lambda: toolkit.question_context(**arguments),
    }
    if name not in calls:
        return error("unknown_tool", name)
    try:
        return calls[name]()
    except Exception as exc:
        return error(type(exc).__name__, str(exc))
