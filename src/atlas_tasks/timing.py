"""Clock-error diagnosis and correction from ambient-noise cross-correlation.

A port of the chronos pipeline (github.com/MaleenKidiwela/chronos):
`compute_ccf` (30-min whitened 1-bit CCFs, 75% overlap), `compute_peak_lag`
(hourly median stacks, envelope-of-CC² picker), `combine_clock` (anchor and
sign), and `filter_and_triggers` (|Δdt| jump triggers). Station I/O and
instrument-response removal stay with the caller; these functions take
preprocessed, equally sampled arrays.

Sign conventions, as in chronos: a positive lag means station B lags station A.
If B's clock is late by δ (its timestamps read true time + δ), the B side of
every CCF moves by +δ, so Δt(B) = peak lag − anchor lag, and the true time of a
B sample is its apparent time − Δt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.signal import hilbert

CC_LEN_S = 1800.0
CC_STEP_S = 450.0
MAXLAG_S = 60.0
SEG_TAPER_S = 20.0
WHITEN_BAND = (0.5, 3.8)
JUMP_THRESHOLD_S = 1.0


# ------------------------------ preprocessing ------------------------------

def taper_fill_runs(x: np.ndarray, fs: float, taper_s: float = 100.0) -> np.ndarray:
    """Cosine-taper the edges of zero-filled gaps so they do not ring in the CCF."""
    data = np.asarray(x, dtype=np.float64).copy()
    is_zero = data == 0.0
    if not is_zero.any():
        return data
    taper_n = int(round(taper_s * fs))
    dz = np.diff(is_zero.astype(np.int8))
    for zs in np.where(dz == 1)[0] + 1:
        lo = max(0, zs - taper_n)
        k = zs - lo
        if k > 0:
            data[lo:zs] *= 0.5 * (1.0 - np.cos(np.pi * np.arange(k) / k))
    for ze in np.where(dz == -1)[0]:
        lo, hi = ze + 1, min(len(data), ze + 1 + taper_n)
        k = hi - lo
        if k > 0:
            data[lo:hi] *= 0.5 * (1.0 + np.cos(np.pi * np.arange(k) / k))
    return data


def cosine_taper_edges(x: np.ndarray, fs: float, taper_s: float = SEG_TAPER_S) -> np.ndarray:
    n, taper_n = len(x), int(round(taper_s * fs))
    if taper_n <= 0 or 2 * taper_n >= n:
        return x
    fade = 0.5 * (1.0 - np.cos(np.pi * np.arange(taper_n) / taper_n))
    taper = np.ones(n)
    taper[:taper_n], taper[-taper_n:] = fade, fade[::-1]
    return x * taper


def whiten(x: np.ndarray, fs: float, fmin: float, fmax: float) -> np.ndarray:
    """Spectral whitening with cosine-tapered band edges (chronos `whiten_segment`)."""
    n = len(x)
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    amp = np.abs(spectrum)
    flat = spectrum / np.where(amp > 0, amp, 1.0)
    lo1, lo2, hi1 = fmin * 0.5, fmin, fmax
    hi2 = min(fmax * 1.2, fs / 2.0 - 1e-6)
    w = np.ones_like(freqs)
    w[(freqs < lo1) | (freqs > hi2)] = 0.0
    m = (freqs >= lo1) & (freqs < lo2)
    if lo2 > lo1:
        w[m] = 0.5 * (1.0 - np.cos(np.pi * (freqs[m] - lo1) / (lo2 - lo1)))
    m = (freqs > hi1) & (freqs <= hi2)
    if hi2 > hi1:
        w[m] = 0.5 * (1.0 + np.cos(np.pi * (freqs[m] - hi1) / (hi2 - hi1)))
    return np.fft.irfft(flat * w, n)


def cross_correlate(a: np.ndarray, b: np.ndarray, fs: float, maxlag_s: float = MAXLAG_S) -> np.ndarray:
    """Cross-correlation of a and b on lags −maxlag..+maxlag; positive lag = b lags a."""
    n = len(a)
    nfft = 1 << int(np.ceil(np.log2(2 * n - 1)))
    c = np.fft.irfft(np.conj(np.fft.rfft(a, nfft)) * np.fft.rfft(b, nfft), nfft)
    half = int(round(maxlag_s * fs))
    return np.concatenate([c[-half:], c[: half + 1]])


def lag_axis(fs: float, maxlag_s: float = MAXLAG_S) -> np.ndarray:
    half = int(round(maxlag_s * fs))
    return np.arange(-half, half + 1) / fs


# ------------------------------- CCF windows --------------------------------

@dataclass
class CCFResult:
    cc: np.ndarray          # (n_windows, n_lags)
    times_s: np.ndarray     # window mid-times, seconds from the record start
    lags_s: np.ndarray
    fs: float
    params: dict = field(default_factory=dict)


def compute_ccf(a: np.ndarray, b: np.ndarray, fs: float, *, window_s: float = CC_LEN_S,
                step_s: float = CC_STEP_S, maxlag_s: float = MAXLAG_S,
                whiten_band: tuple[float, float] = WHITEN_BAND, one_bit: bool = True,
                taper_s: float = SEG_TAPER_S) -> CCFResult:
    """Windowed CCFs of two co-registered records (chronos `process_day`).

    Windows where either record is constant (a gap filled with zeros) are skipped.
    """
    if not (60.0 <= window_s <= 86400.0) or step_s < 0.05 * window_s or not (0 < maxlag_s <= window_s / 2):
        raise ValueError("compute_ccf needs 60 s ≤ window_s ≤ 1 day, step_s ≥ 5 % of window_s, "
                         "and 0 < maxlag_s ≤ window_s / 2")
    a = taper_fill_runs(a, fs)
    b = taper_fill_runs(b, fs)
    n = min(len(a), len(b))
    seg_n, step_n = int(window_s * fs), int(step_s * fs)
    idx = np.arange(seg_n)
    rows, mids = [], []
    for i in range(0, n - seg_n + 1, step_n):
        za, zb = a[i:i + seg_n].copy(), b[i:i + seg_n].copy()
        if np.std(za) == 0 or np.std(zb) == 0:
            continue
        for arr in (za, zb):
            arr -= np.polyval(np.polyfit(idx, arr, 1), idx)
        za = whiten(cosine_taper_edges(za, fs, taper_s), fs, *whiten_band)
        zb = whiten(cosine_taper_edges(zb, fs, taper_s), fs, *whiten_band)
        if one_bit:
            za, zb = np.sign(za), np.sign(zb)
        rows.append(cross_correlate(za, zb, fs, maxlag_s))
        mids.append((i + seg_n / 2.0) / fs)
    lags = lag_axis(fs, maxlag_s)
    cc = np.asarray(rows, dtype=np.float64).reshape(-1, len(lags))
    return CCFResult(cc, np.asarray(mids), lags, fs, {
        "window_s": window_s, "step_s": step_s, "maxlag_s": maxlag_s,
        "whiten_band": list(whiten_band), "one_bit": one_bit})


def stack(cc: np.ndarray, method: Literal["linear", "median", "pws"] = "linear", pws_power: float = 2.0) -> np.ndarray:
    """Stack CCF rows: linear mean, per-lag median, or phase-weighted stack."""
    cc = np.asarray(cc, dtype=np.float64)
    cc = cc[~np.isnan(cc).any(axis=1)]
    if not len(cc):
        raise ValueError("no finite CCF rows to stack")
    if method == "linear":
        return cc.mean(axis=0)
    if method == "median":
        return np.median(cc, axis=0)
    if method == "pws":
        phase = np.exp(1j * np.angle(hilbert(cc, axis=1)))
        return cc.mean(axis=0) * np.abs(phase.mean(axis=0)) ** pws_power
    raise ValueError(f"unknown stack method {method!r}")


def stack_by_bin(cc: np.ndarray, times_s: np.ndarray, bin_s: float = 3600.0) -> tuple[np.ndarray, np.ndarray]:
    """Per-lag median of the CCF windows in each time bin (chronos `stack_hourly`).

    Returns (stacks, bin_start_s); empty bins are absent.
    """
    keys = np.floor(np.asarray(times_s) / bin_s).astype(np.int64)
    out_bins = np.unique(keys)
    stacks = np.vstack([np.median(cc[keys == k], axis=0) for k in out_bins]) if len(out_bins) else np.empty((0, cc.shape[1]))
    return stacks, out_bins * bin_s


# ------------------------------ peak lags ----------------------------------

def peak_lags(cc: np.ndarray, lags_s: np.ndarray, side: Literal["global", "pos", "neg"] = "global",
              refine: bool = True) -> np.ndarray:
    """Ballistic peak lag per row from the envelope of CC² (chronos picker).

    With `refine`, a parabola through the envelope maximum and its neighbours
    gives sub-sample resolution; chronos itself reports the sample lag.
    """
    cc = np.atleast_2d(np.asarray(cc, dtype=np.float64))
    env = np.abs(hilbert(cc ** 2, axis=-1))
    sel = {"global": np.ones_like(lags_s, bool), "pos": lags_s > 0, "neg": lags_s < 0}[side]
    sel_idx = np.where(sel)[0]
    local = np.argmax(env[:, sel], axis=-1)
    picks = sel_idx[local]
    out = lags_s[picks].astype(np.float64)
    if refine:
        dt = float(lags_s[1] - lags_s[0])
        for r, p in enumerate(picks):
            if 0 < p < env.shape[1] - 1:
                y0, y1, y2 = env[r, p - 1], env[r, p], env[r, p + 1]
                denom = y0 - 2 * y1 + y2
                if denom < 0:
                    out[r] += 0.5 * (y0 - y2) / denom * dt
    invalid = np.all(~np.isfinite(env) | (env == 0), axis=-1)
    out[invalid] = np.nan
    return out


def pick_quality(cc: np.ndarray) -> np.ndarray:
    """Peak-to-median ratio of the CC² envelope per row: how far a pick stands above noise.

    Noise-only hourly stacks (8 Hz, 30-min windows) reach about 18 at their 99th
    percentile, so `MIN_PICK_QUALITY` = 20 keeps false picks near 1 %.
    """
    env = np.abs(hilbert(np.atleast_2d(np.asarray(cc, dtype=np.float64)) ** 2, axis=-1))
    med = np.median(env, axis=-1)
    return np.where(med > 0, env.max(axis=-1) / np.where(med > 0, med, 1), 0.0)


MIN_PICK_QUALITY = 20.0
AUTO_BINS_S = (3600.0, 21600.0, 86400.0)


def anchor_lag(peaks: np.ndarray, lag_extent_s: float, ref_window: int = 168, where: Literal["late", "early"] = "late") -> float:
    """Median of the most recent (or earliest) valid picks, excluding picks at the lag boundary."""
    valid = np.where(np.isfinite(peaks) & (np.abs(peaks) < 0.99 * lag_extent_s))[0]
    if not len(valid):
        raise ValueError("no valid peak picks to anchor")
    chosen = valid[-ref_window:] if where == "late" else valid[:ref_window]
    return float(np.median(peaks[chosen]))


def clock_offsets(peaks: np.ndarray, anchor: float, *, target_side: Literal["a", "b"] = "b",
                  max_shift_s: float | None = None) -> np.ndarray:
    """Δt(target) from a peak-lag track: target clock late by Δt seconds is positive."""
    dt = (peaks - anchor) if target_side == "b" else (anchor - peaks)
    dt = np.asarray(dt, dtype=np.float64)
    if max_shift_s is not None:
        dt[np.abs(dt) > max_shift_s] = np.nan
    return dt


# ----------------------------- jump detection -------------------------------

def hampel_mask(x: np.ndarray, window: int, sigma: float = 4.0, min_abs: float = 0.5) -> np.ndarray:
    """Flag points farther than max(sigma·MAD·1.4826, min_abs) from a centred rolling median."""
    x = np.asarray(x, dtype=np.float64)
    n, half = len(x), window // 2
    flags = np.zeros(n, dtype=bool)
    for i in range(n):
        seg = x[max(0, i - half): i + half + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) < max(5, window // 4) or not np.isfinite(x[i]):
            continue
        med = np.median(seg)
        mad = np.median(np.abs(seg - med)) * 1.4826
        flags[i] = abs(x[i] - med) > max(sigma * mad, min_abs)
    return flags


@dataclass
class TimingDiagnosis:
    kind: str                       # "none" | "jump" | "drift" | "jump+drift"
    jumps: list[dict]               # [{"index", "time_s", "size_s"}]
    drift_s_per_day: float
    drift_stderr_s_per_day: float
    outliers: int
    cleaned: np.ndarray

    def to_dict(self) -> dict:
        return {"kind": self.kind, "jumps": self.jumps, "drift_s_per_day": self.drift_s_per_day,
                "drift_stderr_s_per_day": self.drift_stderr_s_per_day, "outliers": self.outliers}


def diagnose_clock(dt: np.ndarray, times_s: np.ndarray, *, jump_threshold_s: float = JUMP_THRESHOLD_S,
                   drift_threshold_s_per_day: float = 0.05, hampel_window: int | None = None,
                   min_segment: int | None = None) -> TimingDiagnosis:
    """Classify a Δt track as clean, stepped (jumps), drifting, or both.

    Outliers are removed with a Hampel filter. A jump is a change of more than
    `jump_threshold_s` between consecutive retained points that persists (the
    median of the next `min_segment` points differs from the previous
    `min_segment` by more than the threshold), so isolated mis-picks do not
    trigger. Drift is the slope of a line fitted within each jump-free segment.
    """
    dt = np.asarray(dt, dtype=np.float64)
    times_s = np.asarray(times_s, dtype=np.float64)
    bin_s = float(np.median(np.diff(times_s))) if len(times_s) > 1 else 3600.0
    hampel_window = hampel_window or max(5, int(round(25 * 3600 / bin_s)))
    min_segment = min_segment or int(np.clip(round(6 * 3600 / bin_s), 2, 6))
    if np.isfinite(dt).sum() < 2:
        return TimingDiagnosis("insufficient_snr", [], float("nan"), float("nan"), 0, dt.copy())
    out = hampel_mask(dt, hampel_window, sigma=4.0, min_abs=max(0.5, jump_threshold_s / 2))
    clean = dt.copy()
    clean[out] = np.nan
    keep = np.where(np.isfinite(clean))[0]
    jumps: list[dict] = []
    for j in range(1, len(keep)):
        i0, i1 = keep[j - 1], keep[j]
        step = clean[i1] - clean[i0]
        if abs(step) <= jump_threshold_s:
            continue
        before = clean[keep[max(0, j - min_segment):j]]
        after = clean[keep[j:j + min_segment]]
        persistent = np.median(after) - np.median(before)
        if abs(persistent) > jump_threshold_s:
            jumps.append({"index": int(i1), "time_s": float(times_s[i1]), "size_s": float(persistent)})
    # Drift: pooled slope across jump-free segments (segment intercepts free).
    bounds = [0] + [jump["index"] for jump in jumps] + [len(clean)]
    xs, ys, groups = [], [], []
    for g, (lo, hi) in enumerate(zip(bounds, bounds[1:])):
        idx = keep[(keep >= lo) & (keep < hi)]
        if len(idx) >= min_segment:
            xs.append(times_s[idx] / 86400.0)
            ys.append(clean[idx])
            groups.append(np.full(len(idx), g))
    slope = stderr = 0.0
    if xs:
        x, y, gid = np.concatenate(xs), np.concatenate(ys), np.concatenate(groups)
        design = np.column_stack([x] + [(gid == g).astype(float) for g in np.unique(gid)])
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        slope = float(coef[0])
        resid = y - design @ coef
        dof = max(1, len(y) - design.shape[1])
        cov = np.linalg.pinv(design.T @ design) * (resid @ resid) / dof
        stderr = float(np.sqrt(max(cov[0, 0], 0.0)))
    drifting = abs(slope) > drift_threshold_s_per_day and abs(slope) > 3 * stderr
    kind = ("jump+drift" if drifting else "jump") if jumps else ("drift" if drifting else "none")
    return TimingDiagnosis(kind, jumps, slope, stderr, int(out.sum()), clean)


def correct_times(apparent_s: np.ndarray, dt_times_s: np.ndarray, dt_s: np.ndarray) -> np.ndarray:
    """True time = apparent − Δt, with Δt linearly interpolated (NaN outside the model)."""
    finite = np.isfinite(dt_s)
    if finite.sum() < 2:
        return np.full(np.shape(apparent_s), np.nan)
    delta = np.interp(apparent_s, dt_times_s[finite], dt_s[finite], left=np.nan, right=np.nan)
    return np.asarray(apparent_s, dtype=np.float64) - delta


def shift_series(x: np.ndarray, fs: float, shift_s: float) -> np.ndarray:
    """Delay a series by `shift_s` seconds with a Fourier phase shift (fractional samples allowed).

    Used to apply a timing correction to samples: correcting a clock late by Δt
    is `shift_series(x, fs, -Δt)`.
    """
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fs)
    padded = np.zeros(nfft)
    padded[:n] = x
    return np.fft.irfft(np.fft.rfft(padded) * np.exp(-2j * np.pi * freqs * shift_s), nfft)[:n]


def clock_track(a: np.ndarray, b: np.ndarray, fs: float, *, bin_s: float | str = "auto", anchor: Literal["late", "early"] = "late",
                anchor_hours: float = 24.0, min_quality: float = MIN_PICK_QUALITY, **ccf_kwargs) -> dict:
    """End to end: CCFs → binned stacks → quality-gated peak lags → Δt(B) track and its diagnosis.

    Bins whose pick quality is below `min_quality` are left empty (NaN) rather
    than reported. With `bin_s="auto"` the shortest stack length in
    `AUTO_BINS_S` (1 h, 6 h, 1 day) where at least half the bins pass is used.
    """
    ccf = compute_ccf(a, b, fs, **ccf_kwargs)
    candidates = AUTO_BINS_S if bin_s == "auto" else (float(bin_s),)
    best = None
    for size in candidates:
        stacks, bins = stack_by_bin(ccf.cc, ccf.times_s, size)
        quality = pick_quality(stacks)
        frac = float(np.mean(quality >= min_quality)) if len(quality) else 0.0
        if best is None or frac > best[3]:
            best = (size, stacks, bins, frac, quality)
        if frac >= 0.5:
            best = (size, stacks, bins, frac, quality)
            break
    size, stacks, bins, frac, quality = best
    peaks = peak_lags(stacks, ccf.lags_s)
    peaks[quality < min_quality] = np.nan
    try:
        ref = anchor_lag(peaks, float(ccf.lags_s[-1]), max(1, int(round(anchor_hours * 3600 / size))), anchor)
        dt = clock_offsets(peaks, ref)
    except ValueError:
        ref, dt = float("nan"), np.full(len(peaks), np.nan)
    diagnosis = diagnose_clock(dt, bins)
    return {"bin_start_s": bins, "bin_s": size, "peak_lag_s": peaks, "pick_quality": quality, "valid_fraction": frac,
            "anchor_lag_s": ref, "delta_t_s": dt, "diagnosis": diagnosis, "n_windows": int(ccf.cc.shape[0]),
            "reference_ccf": stack(ccf.cc), "lags_s": ccf.lags_s}
