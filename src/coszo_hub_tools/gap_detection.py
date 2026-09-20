"""Pure-Python port of the public PREST gap detectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import islice
from math import isfinite, sqrt
from statistics import median
from typing import Any, Iterable


@dataclass(frozen=True)
class GapResult:
    sample_rate_hz: float
    sample_period_seconds: float
    gap_indices: tuple[int, ...]
    segment_splits: tuple[int, ...]
    is_full: bool
    n_gaps: int
    n_segments: int
    algorithm_requested: str
    algorithm_used: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile90(values: list[float]) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = 0.9 * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _legacy(t: list[float], nominal: float, duration: float | None, requested: str) -> GapResult:
    del nominal  # retained for interface parity with the source implementation
    diffs = [b - a for a, b in zip(t, t[1:])]
    positive = [d for d in diffs if isfinite(d) and d > 0]
    if not positive:
        raise ValueError("timestamps must contain a positive interval")
    cutoff = _percentile90(positive)
    cleaned = [d for d in positive if d <= cutoff] or positive
    period = float(median(cleaned))
    actual_duration = duration if duration is not None else t[-1] - t[0]
    expected = round(actual_duration / period) + 1
    tolerance = max(5, int(0.001 * expected))
    is_full = abs(len(t) - expected) <= tolerance
    multiplier = (4.0 if is_full else 3.0) if period >= 10 else ((3.5 if is_full else 2.5) if period >= 0.5 else (2.5 if is_full else 2.0))
    threshold = multiplier * period
    gaps = tuple(i for i, d in enumerate(diffs) if d > threshold)
    missing = sum(round(diffs[i] / period) - 1 for i in gaps)
    return GapResult(1 / period, period, gaps, tuple(i + 1 for i in gaps), is_full,
                     len(gaps), len(gaps) + 1, requested, "legacy",
                     {"multiplier": multiplier, "gap_threshold_seconds": threshold,
                      "expected_npts": expected, "gap_total_missing_estimate": missing})


def _anomaly(t: list[float], nominal: float, requested: str) -> GapResult:
    del nominal
    diffs = [b - a for a, b in zip(t, t[1:])]
    first_guess = float(median(diffs))
    if first_guess <= 0:
        raise ValueError("timestamps must be strictly increasing in the median")
    steps = [round(d / first_guess) for d in diffs]
    index = [0]
    for step in steps:
        index.append(index[-1] + step)
    n_ideal = index[-1] + 1
    true_missing = max(0, n_ideal - len(t))
    xbar = sum(index) / len(index)
    ybar = sum(t) / len(t)
    denom = sum((x - xbar) ** 2 for x in index)
    if denom == 0:
        raise ValueError("cannot fit sample interval")
    period = sum((x - xbar) * (y - ybar) for x, y in zip(index, t)) / denom
    if period <= 0:
        raise ValueError("fitted sample interval is not positive")
    residuals = [y - (t[0] + (x - index[0]) * period) for x, y in zip(index, t)]
    residual_mean = sum(residuals) / len(residuals)
    sigma_ms = 1000 * sqrt(sum((e - residual_mean) ** 2 for e in residuals) / len(residuals))
    frac_max = max(abs(e / period) for e in residuals)
    raw_gaps = tuple(i for i, step in enumerate(steps) if step > 1)
    gaps = raw_gaps if true_missing > 0 else ()
    return GapResult(1 / period, period, gaps, tuple(i + 1 for i in gaps),
                     true_missing == 0, len(gaps), len(gaps) + 1, requested, "anomaly",
                     {"dt_first_guess_seconds": first_guess, "n_ideal": n_ideal,
                      "true_missing": true_missing, "n_gaps_raw": len(raw_gaps),
                      "fractional_residual_max_abs": frac_max,
                      "jitter_unstable": frac_max > 0.4, "sigma_ms": sigma_ms})


def detect_gaps(
    timestamps_seconds: Iterable[float],
    nominal_sample_period_seconds: float,
    algorithm: str = "anomaly",
    request_duration_seconds: float | None = None,
    max_samples: int = 5_000_000,
) -> GapResult:
    """Detect gaps without filesystem, credential, or network access.

    As in the source pipeline, anomaly mode falls back to legacy below 100
    samples. Inputs are bounded by the caller; no large intermediate arrays are
    returned.
    """
    if max_samples < 2:
        raise ValueError("max_samples must be at least 2")
    times = [float(value) for value in islice(timestamps_seconds, max_samples + 1)]
    if len(times) > max_samples:
        raise ValueError(f"timestamps exceed max_samples={max_samples}")
    if len(times) < 2:
        raise ValueError("at least two timestamps are required")
    if not all(isfinite(value) for value in times):
        raise ValueError("timestamps must be finite")
    if nominal_sample_period_seconds <= 0:
        raise ValueError("nominal_sample_period_seconds must be positive")
    if algorithm not in {"legacy", "anomaly"}:
        raise ValueError("algorithm must be 'legacy' or 'anomaly'")
    if request_duration_seconds is not None and request_duration_seconds <= 0:
        raise ValueError("request_duration_seconds must be positive")
    if algorithm == "anomaly" and len(times) < 100:
        return _legacy(times, nominal_sample_period_seconds, request_duration_seconds, algorithm)
    if algorithm == "legacy":
        return _legacy(times, nominal_sample_period_seconds, request_duration_seconds, algorithm)
    return _anomaly(times, nominal_sample_period_seconds, algorithm)
