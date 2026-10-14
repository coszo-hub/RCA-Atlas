"""Agent tool surface for the sandbox tasks: JSON schemas and a dispatcher.

Inputs and outputs are files inside one sandbox directory (`.npz`, `.npy`,
`.csv` with a header row, or `.json` objects of arrays); paths outside it are
refused. Every call returns `{"ok": true, ...}` or `{"ok": false, "error": ...}`
like the repository's other toolkits, so the same MCP wrapper serves it.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from . import dvv, earthquakes, gaps, pressure, router, timing


class Sandbox:
    def __init__(self, root: str | Path | None = None, quake_loader=None) -> None:
        root = root or os.getenv("ATLAS_SANDBOX_DIR")
        if not root:
            raise ValueError("no sandbox directory: pass one or set ATLAS_SANDBOX_DIR")
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"sandbox {self.root} is not a directory")
        cache = os.getenv("ATLAS_QUAKE_CACHE")
        if quake_loader is None and cache and os.getenv("ATLAS_QUAKE_OFFLINE"):
            quake_loader = earthquakes.directory_loader(Path(cache))   # cached days only, never the network
        self.quake_loader = quake_loader or earthquakes.http_loader(Path(cache) if cache else None)

    def path(self, name: str, *, must_exist: bool = True) -> Path:
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root):
            raise PermissionError(f"{name!r} is outside the sandbox")
        if must_exist and not p.exists():
            raise FileNotFoundError(f"{name!r} does not exist in the sandbox")
        return p

    def output(self, name: str, suffix: str):
        """Open a new output file for writing, inside the sandbox and never through a symlink.

        The suffix is added before the path is checked (NumPy and matplotlib
        would otherwise add it afterwards), and the file is opened here so no
        library renames it.
        """
        name = name if name.endswith(suffix) else name + suffix
        unresolved = self.root / name
        p = unresolved.parent.resolve() / unresolved.name
        if p == self.root or not p.is_relative_to(self.root) or not p.parent.is_relative_to(self.root):
            raise PermissionError(f"{name!r} is outside the sandbox")
        if p.is_symlink() or p.is_dir():
            raise PermissionError(f"{name!r} is a symlink or a directory")
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o644)
        return p, os.fdopen(fd, "wb")

    def load(self, name: str) -> dict[str, np.ndarray]:
        p = self.path(name)
        if p.suffix == ".npz":
            with np.load(p, allow_pickle=False) as z:
                return {k: z[k] for k in z.files}
        if p.suffix == ".npy":
            return {"data": np.load(p, allow_pickle=False)}
        if p.suffix == ".csv":
            with p.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            return {k: np.array([float(r[k]) if r[k] not in ("", "nan", "NaN") else np.nan for r in rows]) for k in rows[0]}
        if p.suffix == ".json":
            return {k: np.asarray(v) for k, v in json.loads(p.read_text()).items()}
        raise ValueError(f"unsupported file type {p.suffix!r}")

    def save(self, name: str, **arrays: Any) -> str:
        p, stream = self.output(name, ".npz")
        with stream:
            np.savez(stream, **{k: np.asarray(v) for k, v in arrays.items()})
        return str(p.relative_to(self.root))


def _pick(data: dict[str, np.ndarray], key: str | None, *fallbacks: str) -> np.ndarray:
    for k in ([key] if key else []) + list(fallbacks):
        if k in data:
            return np.asarray(data[k], dtype=np.float64)
    raise KeyError(f"none of {[key, *fallbacks]} in the input file (has {sorted(data)})")


def _floats(values: np.ndarray, limit: int = 2000) -> list:
    arr = np.asarray(values, dtype=np.float64)[:limit]
    return [None if not np.isfinite(v) else round(float(v), 6) for v in arr]


# ------------------------------- handlers -----------------------------------

def route_question(sb: Sandbox, question: str) -> dict:
    return router.route(question).to_dict()


def diagnose_series(sb: Sandbox, path: str, time_key: str | None = None, value_key: str | None = None,
                    period_s: float | None = None) -> dict:
    data = sb.load(path)
    t = _pick(data, time_key, "t_s", "time", "t", "timestamps")
    x = _pick(data, value_key, "x", "value", "values", "data", "p_kpa", "pressure")
    out = gaps.diagnose_series(t, x, period_s=period_s)
    out["findings"] = out["findings"][:500]
    return out


def fill_gaps(sb: Sandbox, path: str, output: str, method: str = "nan", time_key: str | None = None,
              value_key: str | None = None, period_s: float | None = None) -> dict:
    data = sb.load(path)
    t = _pick(data, time_key, "t_s", "time", "t", "timestamps")
    x = _pick(data, value_key, "x", "value", "values", "data", "p_kpa", "pressure")
    grid, filled = gaps.fill_gaps(t, x, period_s=period_s, method=method)
    return {"output": sb.save(output, t_s=grid, x=filled), "n_samples": int(len(grid)),
            "n_missing": int(np.isnan(filled).sum())}


def compute_ccf(sb: Sandbox, path: str, output: str, fs: float | None = None, window_s: float = timing.CC_LEN_S,
                step_s: float = timing.CC_STEP_S, maxlag_s: float = timing.MAXLAG_S,
                whiten_band: list[float] | None = None) -> dict:
    data = sb.load(path)
    fs = float(fs or data["fs"])
    res = timing.compute_ccf(_pick(data, "a"), _pick(data, "b"), fs, window_s=window_s, step_s=step_s,
                             maxlag_s=maxlag_s, whiten_band=tuple(whiten_band or timing.WHITEN_BAND))
    ref = timing.stack(res.cc)
    peak = float(timing.peak_lags(ref, res.lags_s)[0])
    return {"output": sb.save(output, cc=res.cc, times_s=res.times_s, lags_s=res.lags_s, fs=fs),
            "n_windows": int(res.cc.shape[0]), "reference_peak_lag_s": peak, "params": res.params}


def peak_lag(sb: Sandbox, path: str, bin_s: float = 3600.0, side: str = "global", output: str | None = None) -> dict:
    data = sb.load(path)
    stacks, bins = timing.stack_by_bin(data["cc"], data["times_s"], bin_s)
    peaks = timing.peak_lags(stacks, data["lags_s"], side)
    out = {"bin_start_s": _floats(bins), "peak_lag_s": _floats(peaks), "n_bins": int(len(bins)),
           "median_peak_lag_s": float(np.nanmedian(peaks))}
    if output:
        out["output"] = sb.save(output, bin_start_s=bins, peak_lag_s=peaks)
    return out


def clock_track(sb: Sandbox, path: str, output: str, fs: float | None = None, bin_s: float | str = "auto",
                anchor: str = "late", jump_threshold_s: float = timing.JUMP_THRESHOLD_S) -> dict:
    data = sb.load(path)
    fs = float(fs or data["fs"])
    res = timing.clock_track(_pick(data, "a"), _pick(data, "b"), fs, bin_s=bin_s, anchor=anchor)
    diagnosis = timing.diagnose_clock(res["delta_t_s"], res["bin_start_s"], jump_threshold_s=jump_threshold_s)
    saved = sb.save(output, bin_start_s=res["bin_start_s"], bin_center_s=res["bin_start_s"] + res["bin_s"] / 2,
                    delta_t_s=res["delta_t_s"], peak_lag_s=res["peak_lag_s"], anchor_lag_s=res["anchor_lag_s"])
    return {"output": saved, "anchor_lag_s": res["anchor_lag_s"], "n_windows": res["n_windows"], "bin_s": res["bin_s"],
            "valid_fraction": res["valid_fraction"], "diagnosis": diagnosis.to_dict(),
            "delta_t_s": _floats(res["delta_t_s"]), "bin_start_s": _floats(res["bin_start_s"]),
            "sign": "delta_t > 0 means station B's clock is late; true time = apparent - delta_t; "
                    "bins too noisy to pick are null"}


def correct_times(sb: Sandbox, track: str, apparent_times_s: list[float]) -> dict:
    data = sb.load(track)
    # Each Δt is the average over its stack, so it belongs at the bin centre.
    at = data["bin_center_s"] if "bin_center_s" in data else data["bin_start_s"]
    corrected = timing.correct_times(np.asarray(apparent_times_s, float), at, data["delta_t_s"])
    return {"corrected_times_s": _floats(corrected)}


def measure_dvv(sb: Sandbox, path: str, method: str = "stretching", tmin: float = 10.0, tmax: float = 50.0,
                fmin: float | None = None, fmax: float | None = None, epsilon_max: float = 0.02) -> dict:
    data = sb.load(path)
    lags, ref = _pick(data, "lags_s", "lags"), _pick(data, "ref", "reference")
    currents = data.get("currents", data.get("cur"))
    if currents is None:
        raise KeyError("input needs 'cur' or 'currents'")
    kwargs: dict[str, Any] = {"tmin": tmin, "tmax": tmax}
    if method == "stretching":
        kwargs["epsilon_max"] = epsilon_max
    elif method == "mwcs":
        kwargs.update(fmin=fmin or 0.2, fmax=fmax or 2.0)
    elif method == "dtw":
        kwargs["max_dvv"] = epsilon_max
    rows = dvv.dvv_series(ref, np.asarray(currents, float), lags, method, **kwargs)
    return {"method": method, "results": rows, "convention": "dv/v > 0 is a velocity increase (fraction, not percent)"}


def pressure_calibrate(sb: Sandbox, path: str, kind: str, reference_kpa: float | None = None, drift_kind: str = "auto",
                       schedule: list[list[float]] | None = None, settle_s: float = 120.0, output: str | None = None) -> dict:
    data = sb.load(path)
    t = _pick(data, "t_s", "time", "t")
    p = _pick(data, "p_kpa", "reading_kpa", "pressure", "x")
    ref = data["reference_kpa"] if "reference_kpa" in data else reference_kpa
    if ref is None:
        ref = 101.325 if kind == "a0a" else None
    if ref is None:
        raise ValueError("SCPR calibration needs reference_kpa (the piston-gauge pressure)")
    res = pressure.calibrate(t, p, kind=kind, reference_kpa=ref, drift_kind=drift_kind, settle_s=settle_s,
                             schedule=[tuple(s) for s in schedule] if schedule else None)
    out = {"n_calibrations": len(res["windows"]), "calibrations": [w.to_dict() for w in res["windows"]],
           "drift_model": res["model"].to_dict()}
    if output:
        out["output"] = sb.save(output, t_s=t, p_kpa=res["corrected_kpa"])
    return out


def pressure_drift(sb: Sandbox, path: str, mode: str = "estimate", rate_kpa_per_yr: float | None = None,
                   output: str | None = None) -> dict:
    data = sb.load(path)
    t = _pick(data, "t_s", "time", "t")
    p = _pick(data, "p_kpa", "reading_kpa", "pressure", "x")
    # Calibration excursions (A-0-A to ~1 atm, SCPR plateaus) are not seafloor pressure;
    # mask anything far from the record's median and say so.
    excursion = np.abs(p - np.nanmedian(p)) > 50.0
    p = np.where(excursion, np.nan, p)
    est = pressure.estimate_linear_drift(t, p)
    rate = est["rate_kpa_per_yr"] if mode == "estimate" else rate_kpa_per_yr
    if rate is None:
        raise ValueError("mode 'apply' needs rate_kpa_per_yr")
    out = {"mode": mode, "estimate": est, "applied_rate_kpa_per_yr": rate, "masked_excursion_samples": int(excursion.sum())}
    if excursion.any():
        out["warning"] = ("The record leaves seafloor pressure for calibration sequences; it is a self-calibrating gauge. "
                          "Use atlas_pressure_calibrate for its drift.")
    if output:
        out["output"] = sb.save(output, t_s=t, p_kpa=pressure.apply_known_drift(t, p, rate_kpa_per_yr=rate))
    return out


def quake_histogram(sb: Sandbox, start: str, end: str, by: str = "day", min_magnitude: float | None = None,
                    max_magnitude: float | None = None, min_depth_km: float | None = None,
                    max_depth_km: float | None = None, plot: str | None = None) -> dict:
    if len(earthquakes.days_between(start, end)) > 366:
        raise ValueError("date ranges are limited to 366 days")
    events, missing = earthquakes.load_events(start, end, sb.quake_loader)
    events = earthquakes.select(events, min_mag=min_magnitude, max_mag=max_magnitude,
                                min_depth_km=min_depth_km, max_depth_km=max_depth_km)
    out = earthquakes.summarize(events, start, end, missing)
    if by != "day":
        out["histogram"] = earthquakes.histogram(events, by=by, start=start, end=end)
    if plot:
        hist = out["histogram"] if by != "day" else out["daily"]
        p, stream = sb.output(plot, ".png")
        with stream:
            earthquakes.plot_histogram(hist, stream)
        out["plot"] = str(p.relative_to(sb.root))
    return out


# ------------------------------- schemas -------------------------------------

def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}


S, N, I = {"type": "string"}, {"type": "number"}, {"type": "integer"}
TOOL_SCHEMAS = [
    _schema("atlas_route_question", "Classify a question into an RCA Atlas task and name the tools that must answer it.",
            {"question": S}, ["question"]),
    _schema("atlas_diagnose_series", "Find and classify faults in a time series: data gaps (missing samples, zero/NaN fill, flatlines, spikes) versus timing errors (duplicate or backward timestamps, jitter).",
            {"path": S, "time_key": S, "value_key": S, "period_s": N}, ["path"]),
    _schema("atlas_fill_gaps", "Put a series back on its regular sampling grid; missing samples become NaN, linear, or zero.",
            {"path": S, "output": S, "method": {"enum": ["nan", "linear", "zero"]}, "time_key": S, "value_key": S, "period_s": N}, ["path", "output"]),
    _schema("atlas_compute_ccf", "Windowed ambient-noise cross-correlations of two co-registered records (npz with a, b, fs), chronos parameters by default.",
            {"path": S, "output": S, "fs": N, "window_s": N, "step_s": N, "maxlag_s": N, "whiten_band": {"type": "array", "items": N}}, ["path", "output"]),
    _schema("atlas_peak_lag", "Binned (default hourly) median stacks of saved CCFs and their ballistic peak lags (envelope of CC²).",
            {"path": S, "bin_s": N, "side": {"enum": ["global", "pos", "neg"]}, "output": S}, ["path"]),
    _schema("atlas_clock_track", "End-to-end timing diagnosis for station B of a pair: CCFs, hourly peak lags, Δt track, jumps and drift.",
            {"path": S, "output": S, "fs": N, "bin_s": {"description": "stack length in seconds, or \"auto\""}, "anchor": {"enum": ["late", "early"]}, "jump_threshold_s": N}, ["path", "output"]),
    _schema("atlas_correct_times", "Correct apparent timestamps with a saved Δt track: true = apparent − Δt.",
            {"track": S, "apparent_times_s": {"type": "array", "items": N}}, ["track", "apparent_times_s"]),
    _schema("atlas_dvv", "Relative velocity change dv/v between a reference CCF and one or more current CCFs by stretching, MWCS, or DTW.",
            {"path": S, "method": {"enum": ["stretching", "mwcs", "dtw"]}, "tmin": N, "tmax": N, "fmin": N, "fmax": N, "epsilon_max": N}, ["path"]),
    _schema("atlas_pressure_calibrate", "Drift of a SELF-CALIBRATING pressure gauge (A-0-A or SCPR): find its calibration sequences, fit the drift through their offsets, and correct the record. Use this, not atlas_pressure_drift, whenever the gauge runs A-0-A or SCPR calibrations.",
            {"path": S, "kind": {"enum": ["a0a", "scpr"]}, "reference_kpa": N, "drift_kind": {"enum": ["auto", "linear", "exp+linear"]},
             "schedule": {"type": "array", "items": {"type": "array", "items": N}}, "settle_s": N, "output": S}, ["path", "kind"]),
    _schema("atlas_pressure_drift", "Linear drift of a gauge that does NOT self-calibrate: estimate it (tides fitted jointly) or apply a known rate. For A-0-A or SCPR gauges use atlas_pressure_calibrate.",
            {"path": S, "mode": {"enum": ["estimate", "apply"]}, "rate_kpa_per_yr": N, "output": S}, ["path"]),
    _schema("atlas_quake_histogram", "Axial earthquake count, summary, and histogram (per day, hour, or magnitude) over a UTC date range from the hypo71 catalog.",
            {"start": S, "end": S, "by": {"enum": ["day", "hour", "magnitude"]}, "min_magnitude": N, "max_magnitude": N,
             "min_depth_km": N, "max_depth_km": N, "plot": S}, ["start", "end"]),
]

HANDLERS = {
    "atlas_route_question": route_question, "atlas_diagnose_series": diagnose_series, "atlas_fill_gaps": fill_gaps,
    "atlas_compute_ccf": compute_ccf, "atlas_peak_lag": peak_lag, "atlas_clock_track": clock_track,
    "atlas_correct_times": correct_times, "atlas_dvv": measure_dvv, "atlas_pressure_calibrate": pressure_calibrate,
    "atlas_pressure_drift": pressure_drift, "atlas_quake_histogram": quake_histogram,
}


def jsonable(value: Any) -> Any:
    """Plain JSON for tool results: NumPy scalars and arrays converted, NaN and inf as null."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def dispatch(sandbox: Sandbox, name: str, arguments: dict | None) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": {"type": "unknown_tool", "message": f"no tool named {name!r}"}}
    try:
        return jsonable({"ok": True, **handler(sandbox, **(arguments or {}))})
    except TypeError as exc:
        return {"ok": False, "error": {"type": "invalid_arguments", "message": str(exc)}}
    except Exception as exc:  # the agent sees the failure and can recover
        return {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
