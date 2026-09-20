"""Credential-free validation and querying of chronfix correction bundles."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


def _dt64(value) -> np.datetime64:
    try:
        parsed = np.datetime64(value, "s")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid UTC time: {value!r}") from exc
    if np.isnat(parsed):
        raise ValueError(f"invalid UTC time: {value!r}")
    return parsed


def _iso(value: np.datetime64) -> str:
    return np.datetime_as_string(value.astype("datetime64[s]"), unit="s") + "Z"


@dataclass(frozen=True)
class ChronfixModel:
    root: Path
    hour_times: np.ndarray
    delta_t_seconds: np.ndarray
    trigger_starts: np.ndarray
    trigger_ends: np.ndarray
    station: str | None = None

    def is_in_trigger(self, value) -> bool:
        point = _dt64(value)
        return any(start <= point <= end for start, end in zip(self.trigger_starts, self.trigger_ends))

    def interpolate(self, values: Iterable) -> list[float | None]:
        query = np.asarray([_dt64(value) for value in values], dtype="datetime64[s]")
        valid = np.isfinite(self.delta_t_seconds)
        if valid.sum() < 2:
            return [None] * len(query)
        anchors = self.hour_times.astype("datetime64[s]").astype(np.int64)
        query_seconds = query.astype(np.int64)
        interpolated = np.interp(query_seconds, anchors[valid], self.delta_t_seconds[valid], left=np.nan, right=np.nan)
        for idx, point in enumerate(query):
            if self.is_in_trigger(point):
                interpolated[idx] = np.nan
        return [float(value) if np.isfinite(value) else None for value in interpolated]

    def stable_intervals(self, start=None, end=None) -> list[dict[str, str]]:
        if len(self.hour_times) == 0:
            return []
        lower = _dt64(start) if start is not None else self.hour_times[0].astype("datetime64[s]")
        upper = _dt64(end) if end is not None else self.hour_times[-1].astype("datetime64[s]")
        if upper <= lower:
            return []
        intervals = [(lower, upper)]
        for trigger_start, trigger_end in zip(self.trigger_starts, self.trigger_ends):
            next_intervals = []
            for left, right in intervals:
                if trigger_end < left or trigger_start > right:
                    next_intervals.append((left, right))
                    continue
                if trigger_start > left:
                    next_intervals.append((left, min(trigger_start, right)))
                if trigger_end < right:
                    next_intervals.append((max(trigger_end, left), right))
            intervals = next_intervals
        return [{"start": _iso(left), "end": _iso(right)} for left, right in intervals if right > left]

    def summary(self) -> dict:
        valid = self.delta_t_seconds[np.isfinite(self.delta_t_seconds)]
        return {
            "root": str(self.root),
            "station": self.station,
            "coverage_start": _iso(self.hour_times[0]) if len(self.hour_times) else None,
            "coverage_end": _iso(self.hour_times[-1]) if len(self.hour_times) else None,
            "n_hours": int(len(self.hour_times)),
            "n_valid": int(len(valid)),
            "n_missing": int(len(self.delta_t_seconds) - len(valid)),
            "n_triggers": int(len(self.trigger_starts)),
            "delta_t_min_seconds": float(valid.min()) if len(valid) else None,
            "delta_t_max_seconds": float(valid.max()) if len(valid) else None,
            "delta_t_median_seconds": float(np.median(valid)) if len(valid) else None,
            "files": {
                "delta_t": "delta_t_hourly_clean.npy",
                "hour_times": "hour_times.npy",
                "triggers": "trigger_periods.csv",
            },
        }


def load_correction_model(
    correction_dir: str | Path,
    *,
    station: str | None = None,
    delta_t_file: str = "delta_t_hourly_clean.npy",
    hour_times_file: str = "hour_times.npy",
    triggers_file: str = "trigger_periods.csv",
    max_hours: int = 5_000_000,
    max_file_bytes: int = 256 * 1024 * 1024,
) -> ChronfixModel:
    """Load and validate the three-file chronfix correction format."""
    root = Path(correction_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    paths = [root / hour_times_file, root / delta_t_file, root / triggers_file]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > max_file_bytes:
            raise ValueError(f"correction file exceeds max_file_bytes={max_file_bytes}: {path.name}")
    hour_times = np.load(paths[0], allow_pickle=False)
    delta_t = np.load(paths[1], allow_pickle=False)
    if hour_times.ndim != 1 or delta_t.ndim != 1:
        raise ValueError("hour_times and delta_t arrays must be one-dimensional")
    if hour_times.shape != delta_t.shape:
        raise ValueError("hour_times and delta_t arrays must have identical shapes")
    if len(hour_times) > max_hours:
        raise ValueError(f"correction model exceeds max_hours={max_hours}")
    if hour_times.dtype.kind != "M":
        raise ValueError("hour_times must have a NumPy datetime64 dtype")
    if delta_t.dtype.kind not in "fiu":
        raise ValueError("delta_t must have a numeric dtype")
    hour_times = hour_times.astype("datetime64[s]")
    delta_t = delta_t.astype(np.float64)
    if len(hour_times) > 1 and not np.all(np.diff(hour_times.astype(np.int64)) > 0):
        raise ValueError("hour_times must be strictly increasing")

    starts: list[np.datetime64] = []
    ends: list[np.datetime64] = []
    with paths[2].open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"start_index", "end_index"}.issubset(reader.fieldnames or []):
            raise ValueError("trigger CSV requires start_index and end_index columns")
        for row_number, row in enumerate(reader, start=2):
            try:
                start_index, end_index = int(row["start_index"]), int(row["end_index"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid trigger indices on CSV row {row_number}") from exc
            if not (0 <= start_index <= end_index < len(hour_times)):
                raise ValueError(f"trigger indices out of bounds on CSV row {row_number}")
            starts.append(hour_times[start_index])
            ends.append(hour_times[end_index])
    if any(starts[idx] < ends[idx - 1] for idx in range(1, len(starts))):
        raise ValueError("trigger periods must be sorted and non-overlapping")
    return ChronfixModel(root, hour_times, delta_t, np.asarray(starts, dtype="datetime64[s]"),
                         np.asarray(ends, dtype="datetime64[s]"), station)


def inspect_correction_model(
    correction_dir: str | Path,
    *,
    station: str | None = None,
    query_times: Iterable | None = None,
    interval_start=None,
    interval_end=None,
) -> dict:
    """Return a JSON-serializable model summary and optional bounded queries."""
    model = load_correction_model(correction_dir, station=station)
    result = model.summary()
    if query_times is not None:
        query = list(query_times)
        if len(query) > 10_000:
            raise ValueError("query_times is limited to 10000 values")
        values = model.interpolate(query)
        result["queries"] = [
            {"time": _iso(_dt64(time)), "delta_t_seconds": delta,
             "in_trigger": model.is_in_trigger(time)}
            for time, delta in zip(query, values)
        ]
    if interval_start is not None or interval_end is not None:
        result["stable_intervals"] = model.stable_intervals(interval_start, interval_end)
    return result
