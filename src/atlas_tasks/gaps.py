"""Diagnose what is wrong with a sampled time series.

`diagnose_series` sorts every fault into one of two families the correction
step treats differently:

- data gaps: missing samples (timestamp jumps), runs filled with zeros or
  NaN by a merge, stuck (flatlined) values, and isolated spikes;
- timing errors: duplicated timestamps, timestamps that step backwards, and
  sampling jitter (timestamps off their regular grid).

Clock errors between stations (a whole record shifted in time) cannot be seen
in one series; those come from cross-correlation in `timing`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

GAP_FAMILY = {"gap", "zero_fill", "nan_fill", "flatline", "spike"}
TIMING_FAMILY = {"duplicate", "backstep", "jitter", "bad_timestamp"}


@dataclass(frozen=True)
class Finding:
    kind: str
    start_s: float
    end_s: float
    n_samples: int
    detail: str = ""

    @property
    def family(self) -> str:
        return "data_gap" if self.kind in GAP_FAMILY else "timing_error"

    def to_dict(self) -> dict:
        return {**asdict(self), "family": self.family}


def nominal_period(t_s: np.ndarray) -> float:
    d = np.diff(np.asarray(t_s, dtype=np.float64))
    d = d[np.isfinite(d) & (d > 0)]
    if not len(d):
        raise ValueError("timestamps contain no positive interval")
    return float(np.median(d))


def _runs(mask: np.ndarray, min_len: int = 1) -> list[tuple[int, int]]:
    padded = np.r_[False, mask, False].astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= min_len]


def timestamp_glitches(t: np.ndarray, period: float, tolerance_periods: float = 10.0) -> np.ndarray:
    """Samples whose timestamp is non-finite or jumps far off its neighbours and comes back.

    For monotone timestamps a 5-point running median equals the timestamp
    itself, so only out-of-order glitches (a clock word read wrong) stand out;
    gaps and small backward steps are left to the gap and timing checks.
    """
    from scipy.ndimage import median_filter
    t = np.asarray(t, dtype=np.float64)
    bad = ~np.isfinite(t)
    good = np.flatnonzero(~bad)
    if len(good) >= 5:
        tg = t[good]
        bad[good] = np.abs(tg - median_filter(tg, size=5, mode="nearest")) > tolerance_periods * period
    return bad


def diagnose_series(t_s: np.ndarray, x: np.ndarray, *, period_s: float | None = None, gap_factor: float = 1.5,
                    min_fill_run: int = 3, min_flat_run: int = 20, spike_sigma: float = 8.0,
                    jitter_fraction: float = 0.25) -> dict:
    """Find and classify faults in a series.

    A gap is an interval longer than `gap_factor` × the nominal period. Fill
    runs need `min_fill_run` consecutive zeros or NaNs; a flatline needs
    `min_flat_run` identical non-zero values. Zero runs and flatlines must also
    be well beyond the record's own usual plateau length (quantized data). A spike departs from its local
    median by more than `spike_sigma` robust standard deviations of the
    first differences. Jitter is reported when samples sit more than
    `jitter_fraction` of a period off the best-fit regular grid.
    """
    t = np.asarray(t_s, dtype=np.float64)
    v = np.asarray(x, dtype=np.float64)
    if len(t) != len(v) or len(t) < 3:
        raise ValueError("t_s and x must be equal-length arrays with at least three samples")
    period = float(period_s) if period_s else nominal_period(t[np.isfinite(t)])
    findings: list[Finding] = []
    glitch = timestamp_glitches(t, period)
    if glitch.any():
        clean_t = np.where(glitch, np.nan, t)
        for a, b in _runs(glitch):
            near = clean_t[max(0, a - 1)] if a > 0 else clean_t[min(len(t) - 1, b)]
            findings.append(Finding("bad_timestamp", float(near), float(near), b - a,
                                    f"{b - a} non-finite or out-of-place timestamp(s), excluded from the other checks"))
        t, v = t[~glitch], v[~glitch]
        if len(t) < 3:
            raise ValueError("fewer than three usable timestamps")
    d = np.diff(t)

    dup = np.flatnonzero(d == 0)
    if len(dup):  # repeated samples interleave with their originals, so group by time
        groups = np.split(dup, np.flatnonzero(np.diff(t[dup]) > gap_factor * period) + 1)
        for g in groups:
            findings.append(Finding("duplicate", t[g[0]], t[g[-1]], len(g), f"{len(g)} repeated timestamp(s)"))
    for i in np.flatnonzero(d < 0):
        findings.append(Finding("backstep", t[i], t[i], 1, f"timestamps step back {-d[i]:.6g} s"))
    for i in np.flatnonzero(d > gap_factor * period):
        missing = int(round(d[i] / period)) - 1
        findings.append(Finding("gap", t[i], t[i + 1], missing, f"{missing} sample(s) missing over {d[i]:.6g} s"))

    # Coarsely quantized, slowly varying records sit on one value for a while
    # naturally; a constant run counts as a fault only if it is also much longer
    # than the record's usual plateaus (3 × the 95th percentile of run lengths).
    finite = np.isfinite(v)
    change = np.r_[True, (np.diff(v) != 0) | ~finite[1:] | ~finite[:-1]]
    run_lengths = np.diff(np.r_[np.flatnonzero(change), len(v)])
    usual = 3 * float(np.percentile(run_lengths, 95)) if len(run_lengths) else 0.0

    for kind, mask in (("nan_fill", ~finite), ("zero_fill", v == 0.0)):
        floor = min_fill_run if kind == "nan_fill" else max(min_fill_run, int(usual))
        for a, b in _runs(mask, floor):
            findings.append(Finding(kind, t[a], t[b - 1], b - a, f"{b - a} consecutive {'NaN' if kind == 'nan_fill' else 'zero'} values"))

    same = np.r_[False, (np.diff(v) == 0) & finite[1:] & finite[:-1] & (v[1:] != 0)]
    for a, b in _runs(same, max(min_flat_run, int(usual)) - 1):
        findings.append(Finding("flatline", t[a - 1], t[b - 1], b - a + 1, f"value stuck at {v[a]:.6g}"))

    if finite.sum() > 10:
        dv = np.diff(v[finite])
        # Quantized records can have a zero MAD; never let the scale fall below one quantum.
        nonzero = np.abs(dv[dv != 0])
        quantum = float(nonzero.min()) if len(nonzero) else 1e-12
        scale = max(1.4826 * float(np.median(np.abs(dv - np.median(dv)))), quantum, 1e-12)
        idx = np.flatnonzero(finite)
        for j in range(1, len(idx) - 1):
            left, right = v[idx[j]] - v[idx[j - 1]], v[idx[j + 1]] - v[idx[j]]
            if abs(left) > spike_sigma * scale and abs(right) > spike_sigma * scale and np.sign(left) != np.sign(right):
                findings.append(Finding("spike", t[idx[j]], t[idx[j]], 1, f"departure {left:.6g}"))

    # Jitter: distance from the best-fit regular grid, fitted separately between
    # timestamp faults so a backward step does not shift the grid for the rest.
    breaks = np.r_[0, np.flatnonzero(d <= 0) + 1, len(t)]
    for lo, hi in zip(breaks, breaks[1:]):
        tt = t[lo:hi]
        if len(tt) <= 3:
            continue
        steps = np.round((tt - tt[0]) / period)
        if np.ptp(steps) == 0:
            continue
        try:
            slope, intercept = np.polyfit(steps, tt, 1)
        except np.linalg.LinAlgError:
            continue
        off = (tt - (intercept + slope * steps)) / period
        for a, b in _runs(np.abs(off) > jitter_fraction, 3):
            findings.append(Finding("jitter", tt[a], tt[b - 1], b - a, f"up to {np.max(np.abs(off[a:b])):.2f} periods off grid"))

    findings.sort(key=lambda f: (f.start_s, f.kind))
    families = sorted({f.family for f in findings})
    return {
        "period_s": period, "n_samples": int(len(t)),
        "findings": [f.to_dict() for f in findings],
        "families": families,
        "summary": {kind: sum(1 for f in findings if f.kind == kind) for kind in sorted({f.kind for f in findings})},
        "verdict": " and ".join(families) if families else "clean",
    }


def fill_gaps(t_s: np.ndarray, x: np.ndarray, *, period_s: float | None = None, method: str = "nan") -> tuple[np.ndarray, np.ndarray]:
    """Put a series back on its regular grid; missing samples become NaN, or linear/zero fill.

    Duplicate timestamps keep their first value; samples that step backwards and
    non-finite or out-of-place timestamps are dropped.
    """
    t = np.asarray(t_s, dtype=np.float64)
    v = np.asarray(x, dtype=np.float64)
    period = float(period_s) if period_s else nominal_period(t[np.isfinite(t)])
    ok = ~timestamp_glitches(t, period)
    t, v = t[ok], v[ok]
    keep = np.r_[True, np.diff(np.maximum.accumulate(t)) > 0] & (t >= np.maximum.accumulate(t))
    t, v = t[keep], v[keep]
    n_grid = int(round((t[-1] - t[0]) / period)) + 1
    if n_grid > 10 * len(t) + 1000:
        raise ValueError(f"the regular grid would need {n_grid} samples for {len(t)} data points; check the timestamps or period")
    grid = t[0] + np.arange(n_grid) * period
    idx = np.clip(np.round((t - t[0]) / period).astype(int), 0, len(grid) - 1)
    out = np.full(len(grid), np.nan)
    out[idx] = v
    if method == "linear":
        ok = np.isfinite(out)
        out = np.interp(grid, grid[ok], out[ok])
    elif method == "zero":
        out = np.nan_to_num(out, nan=0.0)
    elif method != "nan":
        raise ValueError("method must be 'nan', 'linear', or 'zero'")
    return grid, out
