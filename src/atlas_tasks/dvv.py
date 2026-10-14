"""Relative seismic velocity change (dv/v) between a reference and a current CCF.

Three standard estimators, each measured in a coda window that excludes the
ballistic arrivals:

- stretching (Sens-Schönfelder & Wegler 2006): grid search for the ε that best
  maps the reference onto the current CCF, cur(t) ≈ ref(t·(1+ε)), so dv/v = ε.
- MWCS, moving-window cross-spectral (Clarke et al. 2011): per-window delays
  from the cross-spectrum phase slope, then dv/v = −(slope of δt against t).
- DTW, dynamic time warping (Mikesell et al. 2015): an optimal sample-by-sample
  warping path gives δt(t); dv/v = −(slope of δt against t).

All three report dv/v as a fraction (0.001 = 0.1 %).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import resample_poly


@dataclass
class DvvResult:
    method: str
    dvv: float
    error: float
    quality: float          # stretching: max correlation; MWCS/DTW: R² of the δt fit
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"method": self.method, "dvv": self.dvv, "dvv_percent": 100 * self.dvv,
                "error": self.error, "quality": self.quality, **self.details}


def coda_mask(lags: np.ndarray, tmin: float, tmax: float, side: str = "both") -> np.ndarray:
    a = np.abs(lags)
    m = (a >= tmin) & (a <= tmax)
    if side == "pos":
        m &= lags > 0
    elif side == "neg":
        m &= lags < 0
    return m


def stretching(ref: np.ndarray, cur: np.ndarray, lags: np.ndarray, *, tmin: float, tmax: float,
               epsilon_max: float = 0.02, n_eps: int = 401, side: str = "both", refine: bool = True) -> DvvResult:
    m = coda_mask(lags, tmin, tmax, side)
    if m.sum() < 10:
        raise ValueError(f"stretching: only {int(m.sum())} lag samples in the {tmin}-{tmax} s coda window")
    eps = np.linspace(-epsilon_max, epsilon_max, n_eps)
    c = cur[m] - cur[m].mean()
    if not np.any(c) or not np.all(np.isfinite(c)):
        raise ValueError("stretching: the current CCF is constant or not finite in the coda window")

    def corr(e: float) -> float:
        r = np.interp(lags[m] * (1.0 + e), lags, ref)
        r = r - r.mean()
        return float(np.dot(r, c) / np.sqrt(np.dot(r, r) * np.dot(c, c)))

    cc = np.array([corr(e) for e in eps])
    if not np.any(np.isfinite(cc)):
        raise ValueError("stretching: the reference CCF is constant in the coda window")
    k = int(np.nanargmax(cc))
    at_edge = k in (0, len(eps) - 1)
    best = float(eps[k])
    if refine and 0 < k < len(eps) - 1:
        fine = np.linspace(eps[k - 1], eps[k + 1], 41)
        fcc = np.array([corr(e) for e in fine])
        best, cmax = float(fine[np.argmax(fcc)]), float(np.max(fcc))
    else:
        cmax = float(cc[k])
    # Weaver et al. (2011) theoretical error of the stretching estimate.
    t1, t2 = tmin, tmax
    freqs = np.fft.rfftfreq(len(ref), d=float(lags[1] - lags[0]))
    spec = np.abs(np.fft.rfft(ref)) ** 2
    omega_c = 2 * np.pi * np.sqrt(np.sum(freqs ** 2 * spec) / np.sum(spec))
    x = max(1e-12, 1 - cmax ** 2)
    error = float(np.sqrt(x) / (2 * max(cmax, 1e-6)) * np.sqrt(6 * np.sqrt(np.pi / 2) / (omega_c ** 2 * (t2 ** 3 - t1 ** 3))))
    return DvvResult("stretching", best, error, cmax, {"epsilon_grid": [float(eps[0]), float(eps[-1]), n_eps],
                                                         "at_grid_edge": at_edge,
                                                         **({"warning": "best fit is at the edge of the search range; "
                                                             "raise epsilon_max"} if at_edge else {})})


def _ar1_inflation(resid: np.ndarray) -> float:
    """Standard-error inflation for AR(1)-correlated residuals: sqrt((1 + r1) / (1 − r1))."""
    if len(resid) < 4 or np.std(resid) == 0:
        return 1.0
    r1 = float(np.clip(np.corrcoef(resid[:-1], resid[1:])[0, 1], 0.0, 0.999))
    return float(np.sqrt((1 + r1) / (1 - r1)))


def _weighted_line(x: np.ndarray, y: np.ndarray, w: np.ndarray, through_origin: bool,
                   correlated: bool = False) -> tuple[float, float, float]:
    """Weighted least-squares slope, its standard error, and R².

    With `correlated`, the error is inflated for lag-1 autocorrelation of the
    residuals (overlapping windows, upsampled warping paths), which otherwise
    makes the reported σ far too small.
    """
    w = np.asarray(w, dtype=np.float64)
    if through_origin:
        slope = float(np.sum(w * x * y) / np.sum(w * x * x))
        resid = y - slope * x
        dof = max(1, len(x) - 1)
        se = float(np.sqrt(np.sum(w * resid ** 2) / dof / np.sum(w * x * x)))
    else:
        design = np.column_stack([x, np.ones_like(x)])
        sw = np.sqrt(w)
        coef, *_ = np.linalg.lstsq(design * sw[:, None], y * sw, rcond=None)
        slope = float(coef[0])
        resid = y - design @ coef
        dof = max(1, len(x) - 2)
        cov = np.linalg.pinv((design * w[:, None]).T @ design) * np.sum(w * resid ** 2) / dof
        se = float(np.sqrt(max(cov[0, 0], 0.0)))
    if correlated:
        se *= _ar1_inflation(resid)
    ss_tot = np.sum(w * (y - np.average(y, weights=w)) ** 2)
    r2 = float(1 - np.sum(w * resid ** 2) / ss_tot) if ss_tot > 0 else 0.0
    return slope, se, r2


def mwcs(ref: np.ndarray, cur: np.ndarray, lags: np.ndarray, *, tmin: float, tmax: float, fmin: float, fmax: float,
         window_s: float = 10.0, step_s: float = 2.5, smoothing_half_win: int = 5, min_coherence: float = 0.5,
         through_origin: bool = True) -> DvvResult:
    fs = 1.0 / float(lags[1] - lags[0])
    win_n, step_n = int(round(window_s * fs)), int(round(step_s * fs))
    nfft = 1 << int(np.ceil(np.log2(2 * win_n)))
    freqs = np.fft.rfftfreq(nfft, d=1.0 / fs)
    band = (freqs >= fmin) & (freqs <= fmax)
    taper = np.hanning(win_n)
    kernel = np.hanning(2 * smoothing_half_win + 1)
    kernel /= kernel.sum()
    times, delays, errs, cohs = [], [], [], []
    for start in range(0, len(lags) - win_n + 1, step_n):
        mid = float(lags[start + win_n // 2])
        if not (tmin <= abs(mid) <= tmax):
            continue
        r = ref[start:start + win_n]
        c = cur[start:start + win_n]
        R = np.fft.rfft((r - r.mean()) * taper, nfft)
        C = np.fft.rfft((c - c.mean()) * taper, nfft)
        smooth = lambda z: np.convolve(z, kernel, mode="same")
        cross = smooth(np.conj(R) * C)
        coh = np.abs(cross) / np.sqrt(smooth(np.abs(R) ** 2) * smooth(np.abs(C) ** 2) + 1e-30)
        coh = np.clip(coh[band], 0, 0.999)
        phase = np.unwrap(np.angle(cross[band]))
        omega = 2 * np.pi * freqs[band]
        weight = np.sqrt(coh ** 2 / (1 - coh ** 2)) * np.sqrt(np.abs(cross[band]))
        if weight.sum() <= 0 or np.mean(coh) < min_coherence:
            continue
        # Phase of conj(R)·C is −ω·δt when cur is ref delayed by δt.
        slope, se, _ = _weighted_line(omega, phase, weight, through_origin=True)
        times.append(mid)
        delays.append(-slope)
        errs.append(se)
        cohs.append(float(np.mean(coh)))
    if len(times) < 3:
        raise ValueError("MWCS: fewer than three coherent windows in the coda")
    t, d, e = np.array(times), np.array(delays), np.maximum(np.array(errs), 1e-9)
    slope, se, r2 = _weighted_line(t, d, 1.0 / e ** 2, through_origin, correlated=True)
    return DvvResult("mwcs", -slope, se, r2, {"n_windows": len(t), "mean_coherence": float(np.mean(cohs))})


def dtw_delays(ref: np.ndarray, cur: np.ndarray, max_lag: int, b: int = 1) -> np.ndarray:
    """Integer-sample delays u[i] with cur[i] ≈ ref[i − u[i]], |u[i]−u[i−1]| ≤ 1 every b samples.

    Accumulates the alignment error forward and backtracks (Hale 2013; Mikesell et al. 2015).
    """
    n = len(cur)
    shifts = np.arange(-max_lag, max_lag + 1)
    err = np.full((n, len(shifts)), np.inf)
    for j, s in enumerate(shifts):
        lo, hi = max(0, s), min(n, n + s)
        err[lo:hi, j] = (cur[lo:hi] - ref[lo - s:hi - s]) ** 2
    err[~np.isfinite(err)] = np.max(err[np.isfinite(err)]) * 10
    acc = err.copy()
    for i in range(b, n):
        prev = acc[i - b]
        best = np.minimum(prev, np.minimum(np.r_[np.inf, prev[:-1]], np.r_[prev[1:], np.inf]))
        acc[i] = err[i] + best
    u = np.empty(n, dtype=int)
    j = int(np.argmin(acc[-1]))
    u[-1] = shifts[j]
    for i in range(n - 1, 0, -1):
        if i % b == 0 or b == 1:
            cands = [k for k in (j - 1, j, j + 1) if 0 <= k < len(shifts)]
            j = min(cands, key=lambda k: acc[i - 1, k])
        u[i - 1] = shifts[j]
    return u


DTW_MAX_CELLS = 20_000_000      # error + accumulation matrices, about 320 MB of float64


def dtw(ref: np.ndarray, cur: np.ndarray, lags: np.ndarray, *, tmin: float, tmax: float, max_dvv: float = 0.02,
        upsample: int = 8, side: str = "both") -> DvvResult:
    dt = float(lags[1] - lags[0])
    # Warp only the coda (plus room for the largest shift), one side at a time.
    pad = max_dvv * tmax + 4 * dt
    slopes_x, slopes_u = [], []
    for sign in ((1, -1) if side == "both" else (1,) if side == "pos" else (-1,)):
        sel = (sign * lags >= tmin - pad) & (sign * lags <= tmax + pad)
        if sel.sum() < 10:
            continue
        seg_lags = lags[sel]
        fine_ref = resample_poly(ref[sel], upsample, 1)
        fine_cur = resample_poly(cur[sel], upsample, 1)
        fine_lags = seg_lags[0] + np.arange(len(fine_ref)) * dt / upsample
        max_lag = max(2, int(np.ceil(max_dvv * tmax / (dt / upsample))) + 2)
        if len(fine_ref) * (2 * max_lag + 1) > DTW_MAX_CELLS:
            raise ValueError("dtw: the warping problem is too large; lower upsample, max_dvv, or tmax")
        u = dtw_delays(fine_ref, fine_cur, max_lag) * (dt / upsample)
        m = coda_mask(fine_lags, tmin, tmax, "pos" if sign > 0 else "neg")
        slopes_x.append(fine_lags[m])
        slopes_u.append(u[m])
    if not slopes_x or sum(len(x) for x in slopes_x) < 10:
        raise ValueError(f"dtw: too few lag samples in the {tmin}-{tmax} s coda window")
    x, u = np.concatenate(slopes_x), np.concatenate(slopes_u)
    if not np.any(x):
        raise ValueError("dtw: degenerate coda window")
    slope, se, r2 = _weighted_line(x, u, np.ones(len(x)), through_origin=True, correlated=True)
    return DvvResult("dtw", -slope, se, r2, {"upsample": upsample, "max_shift_samples": max_lag})


def measure(ref: np.ndarray, cur: np.ndarray, lags: np.ndarray, method: str = "stretching", **kwargs) -> DvvResult:
    if method == "stretching":
        return stretching(ref, cur, lags, **kwargs)
    if method == "mwcs":
        return mwcs(ref, cur, lags, **kwargs)
    if method == "dtw":
        return dtw(ref, cur, lags, **kwargs)
    raise ValueError(f"unknown dv/v method {method!r}")


def dvv_series(ref: np.ndarray, currents: np.ndarray, lags: np.ndarray, method: str = "stretching", **kwargs) -> list[dict]:
    """dv/v for each row of `currents` (for example daily stacks) against one reference."""
    out = []
    for i, cur in enumerate(np.atleast_2d(currents)):
        try:
            out.append({"index": i, **measure(ref, cur, lags, method, **kwargs).to_dict()})
        except ValueError as exc:
            out.append({"index": i, "method": method, "dvv": None, "error": None, "message": str(exc)})
    return out
