"""Seafloor-pressure calibration and drift correction.

Self-calibrating gauges periodically expose the transducer to a known
reference pressure; the reading minus that reference is the gauge offset
(drift) at that moment.

- A-0-A (ambient-zero-ambient; Sasagawa et al. 2016):
  a valve switches the gauge from seafloor pressure to the housing's internal
  pressure (≈ atmospheric, measured by a barometer) for a few minutes.
- SCPR (self-calibrating pressure recorder; Sasagawa & Zumberge 2013): a
  piston gauge applies a known reference pressure near seafloor pressure.

Both reduce to the same steps: find the calibration sequences, take the
settled reading in each, subtract the reference, fit a drift model through
the offsets, and subtract the model from the record (with the calibration
windows masked). For gauges that do not self-calibrate, the drift is either
fitted directly (tides and a linear trend jointly) or supplied as a known rate.

A linear drift fitted from a single non-calibrating gauge is indistinguishable
from real vertical deformation (for example inflation at Axial Seamount); the
result reports that confound rather than hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SECONDS_PER_YEAR = 365.25 * 86400.0
TIDAL_PERIODS_H = {"M2": 12.4206012, "S2": 12.0, "N2": 12.65834751, "K2": 11.96723606,
                   "K1": 23.93447213, "O1": 25.81933871, "P1": 24.06588766, "Q1": 26.868350}


# ------------------------------- sequences ----------------------------------

@dataclass
class CalibrationWindow:
    start_s: float
    end_s: float
    reading_kpa: float
    reference_kpa: float
    offset_kpa: float
    n_used: int
    scatter_kpa: float
    mask_start_s: float | None = None   # the whole valve excursion, transient included
    mask_end_s: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive-exclusive index runs where mask is true."""
    padded = np.r_[False, mask, False].astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2], edges[1::2]))


def rolling_std(x: np.ndarray, t: np.ndarray, window_s: float) -> np.ndarray:
    """Centred rolling standard deviation over about `window_s` seconds of samples."""
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    k = max(3, int(round(window_s / dt)))
    finite = np.where(np.isfinite(x), x, 0.0)
    c1 = np.r_[0.0, np.cumsum(finite)]
    c2 = np.r_[0.0, np.cumsum(finite ** 2)]
    idx = np.arange(len(x))
    lo = np.clip(idx - k // 2, 0, len(x))
    hi = np.clip(idx + k // 2 + 1, 0, len(x))
    n = hi - lo
    mean = (c1[hi] - c1[lo]) / n
    return np.sqrt(np.clip((c2[hi] - c2[lo]) / n - mean ** 2, 0, None))


def find_calibrations(t_s: np.ndarray, p_kpa: np.ndarray, *, kind: str, reference_kpa: float | np.ndarray,
                      tolerance_kpa: float | None = None, min_duration_s: float = 120.0, settle_s: float = 120.0,
                      max_scatter_kpa: float | None = None, merge_gap_s: float = 60.0, min_step_kpa: float = 1.0,
                      schedule: list[tuple[float, float]] | None = None) -> list[CalibrationWindow]:
    """Locate calibration sequences and measure the gauge offset in each.

    `kind="a0a"`: samples far below seafloor pressure (within `tolerance_kpa`,
    default 500 kPa, of the internal reference). `kind="scpr"`: samples within
    `tolerance_kpa` (default 10 kPa, room for drift) of the piston-gauge reference that are
    locally flat and bounded by abrupt valve steps of at least `min_step_kpa`
    (tidal slack water is flat too, but has no edges). `reference_kpa` may be a
    scalar or an array aligned with `t_s` (for example the internal barometer).
    With `schedule` (start, end) pairs from the instrument's command log, those
    windows are measured directly and nothing is detected.
    The first `settle_s` seconds of each sequence (the valve transient) are
    excluded from the offset estimate.
    """
    t = np.asarray(t_s, dtype=np.float64)
    p = np.asarray(p_kpa, dtype=np.float64)
    ref = np.broadcast_to(np.asarray(reference_kpa, dtype=np.float64), p.shape)
    if kind == "a0a":
        tol = 500.0 if tolerance_kpa is None else tolerance_kpa
        mask = np.abs(p - ref) < tol
    elif kind == "scpr":
        # Tides carry seafloor pressure through the reference level too, so a
        # piston-gauge plateau must also be locally flat.
        tol = 10.0 if tolerance_kpa is None else tolerance_kpa
        max_scatter_kpa = 0.2 if max_scatter_kpa is None else max_scatter_kpa
        mask = (np.abs(p - ref) < tol) & (rolling_std(p, t, min(min_duration_s, 120.0)) < max_scatter_kpa)
    else:
        raise ValueError("kind must be 'a0a' or 'scpr'")
    mask &= np.isfinite(p)
    if schedule is not None:
        merged = [[int(np.searchsorted(t, a)), int(np.searchsorted(t, b))] for a, b in schedule]
    else:
        merged = []
        for lo, hi in _runs(mask):
            if merged and t[lo] - t[merged[-1][1] - 1] <= merge_gap_s:
                merged[-1][1] = hi
            else:
                merged.append([lo, hi])
    windows = []
    for lo, hi in merged:
        if hi - lo < 3 or t[hi - 1] - t[lo] < min_duration_s:
            continue
        if kind == "scpr" and schedule is None:
            # Back off to the valve edges (the flatness test trims the transient), then require a step at both.
            lo_edge = int(np.searchsorted(t, t[lo] - 240.0))
            hi_edge = int(np.searchsorted(t, t[hi - 1] + 60.0, side="right"))
            inside = np.median(p[lo:hi])
            before, after = p[max(0, lo_edge - 4):lo_edge], p[hi_edge:hi_edge + 4]
            if len(before) == 0 or len(after) == 0 or min(abs(np.median(before) - inside),
                                                          abs(np.median(after) - inside)) < min_step_kpa:
                continue
        used = (t[lo:hi] - t[lo]) >= settle_s
        if used.sum() < 3:
            continue
        values = p[lo:hi][used] - ref[lo:hi][used]
        scatter = float(np.std(values))
        if kind == "scpr" and max_scatter_kpa is not None and scatter > max_scatter_kpa:
            continue  # a tidal crossing of the reference level, not a calibration
        offset = float(np.median(values))
        # Mask out to the valve edges: the settling transient before a detected
        # plateau is still far from seafloor pressure (and wrong to keep).
        level = float(np.median(p[lo:hi][used]))
        a, b = lo, hi
        while a > 0 and abs(p[a - 1] - level) < 2.0 and t[lo] - t[a - 1] < 900:
            a -= 1
        while b < len(p) and abs(p[b] - level) < 2.0 and t[b] - t[hi - 1] < 900:
            b += 1
        windows.append(CalibrationWindow(float(t[lo]), float(t[hi - 1]), level, float(np.median(ref[lo:hi][used])),
                                         offset, int(used.sum()), scatter, float(t[a]), float(t[b - 1])))
    return windows


# ------------------------------- drift models -------------------------------

@dataclass
class DriftModel:
    kind: str                          # "linear" | "exp+linear"
    t0_s: float
    params: dict
    stderr: dict = field(default_factory=dict)
    rms_residual_kpa: float = 0.0
    n_points: int = 0

    def __call__(self, t_s: np.ndarray) -> np.ndarray:
        years = (np.asarray(t_s, dtype=np.float64) - self.t0_s) / SECONDS_PER_YEAR
        out = self.params["offset_kpa"] + self.params["rate_kpa_per_yr"] * years
        if self.kind == "exp+linear":
            days = years * 365.25
            out = out + self.params["exp_amp_kpa"] * (1 - np.exp(-days / self.params["exp_tau_days"]))
        return out

    def to_dict(self) -> dict:
        return {"kind": self.kind, "t0_s": self.t0_s, **self.params,
                "stderr": self.stderr, "rms_residual_kpa": self.rms_residual_kpa, "n_points": self.n_points}


def fit_drift(t_s: np.ndarray, offsets_kpa: np.ndarray, *, kind: str = "linear", t0_s: float | None = None,
              tau_grid_days: np.ndarray | None = None) -> DriftModel:
    """Least-squares drift through calibration offsets.

    `exp+linear` searches the exponential time constant on a grid and solves the
    remaining coefficients linearly at each, keeping the best fit.
    """
    t = np.asarray(t_s, dtype=np.float64)
    y = np.asarray(offsets_kpa, dtype=np.float64)
    t0 = float(t[0]) if t0_s is None else float(t0_s)
    years = (t - t0) / SECONDS_PER_YEAR

    def solve(design: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        resid = y - design @ coef
        dof = max(1, len(y) - design.shape[1])
        cov = np.linalg.pinv(design.T @ design) * (resid @ resid) / dof
        return coef, np.sqrt(np.clip(np.diag(cov), 0, None)), float(np.sqrt(np.mean(resid ** 2)))

    if kind == "linear":
        if len(y) < 2:
            raise ValueError("a linear drift needs at least two calibrations")
        coef, se, rms = solve(np.column_stack([np.ones_like(years), years]))
        return DriftModel("linear", t0, {"offset_kpa": float(coef[0]), "rate_kpa_per_yr": float(coef[1])},
                          {"offset_kpa": float(se[0]), "rate_kpa_per_yr": float(se[1])}, rms, len(y))
    if kind == "exp+linear":
        if len(y) < 4:
            raise ValueError("an exponential+linear drift needs at least four calibrations")
        best = None
        grid = tau_grid_days if tau_grid_days is not None else np.geomspace(2, 400, 120)
        design_for = lambda tau: np.column_stack([np.ones_like(years), years, 1 - np.exp(-years * 365.25 / tau)])
        for tau in grid:
            coef, se, rms = solve(design_for(tau))
            if best is None or rms < best[3]:
                best = (tau, coef, se, rms)
        from scipy.optimize import minimize_scalar
        k = int(np.argmin(np.abs(np.asarray(grid) - best[0])))
        lo, hi = np.log(grid[max(0, k - 1)]), np.log(grid[min(len(grid) - 1, k + 1)])
        if hi > lo:
            opt = minimize_scalar(lambda lt: solve(design_for(np.exp(lt)))[2], bounds=(lo, hi), method="bounded")
            coef, se, rms = solve(design_for(np.exp(opt.x)))
            if rms <= best[3]:
                best = (float(np.exp(opt.x)), coef, se, rms)
        tau, coef, se, rms = best
        return DriftModel("exp+linear", t0, {"offset_kpa": float(coef[0]), "rate_kpa_per_yr": float(coef[1]),
                                             "exp_amp_kpa": float(coef[2]), "exp_tau_days": float(tau)},
                          {"offset_kpa": float(se[0]), "rate_kpa_per_yr": float(se[1]), "exp_amp_kpa": float(se[2])},
                          rms, len(y))
    raise ValueError("kind must be 'linear' or 'exp+linear'")


def select_drift_model(t_s: np.ndarray, offsets_kpa: np.ndarray, *, t0_s: float | None = None) -> DriftModel:
    """Linear unless exponential+linear lowers the BIC (it costs two more parameters)."""
    linear = fit_drift(t_s, offsets_kpa, kind="linear", t0_s=t0_s)
    if len(offsets_kpa) < 6:
        return linear
    curved = fit_drift(t_s, offsets_kpa, kind="exp+linear", t0_s=t0_s)
    n = len(offsets_kpa)
    bic = lambda m, k: n * np.log(max(m.rms_residual_kpa, 1e-9) ** 2) + k * np.log(n)
    return curved if bic(curved, 4) < bic(linear, 2) else linear


def apply_drift(t_s: np.ndarray, p_kpa: np.ndarray, model: DriftModel, *,
                mask_windows: list[CalibrationWindow] | None = None, pad_s: float = 60.0) -> np.ndarray:
    """Subtract the drift model; calibration windows (± pad) become NaN."""
    t = np.asarray(t_s, dtype=np.float64)
    out = np.asarray(p_kpa, dtype=np.float64) - model(t)
    for w in mask_windows or []:
        lo = w.start_s if w.mask_start_s is None else min(w.start_s, w.mask_start_s)
        hi = w.end_s if w.mask_end_s is None else max(w.end_s, w.mask_end_s)
        out[(t >= lo - pad_s) & (t <= hi + pad_s)] = np.nan
    return out


def calibrate(t_s: np.ndarray, p_kpa: np.ndarray, *, kind: str, reference_kpa: float | np.ndarray,
              drift_kind: str = "linear", **find_kwargs) -> dict:
    """Find calibrations, fit the drift through their offsets, and correct the record.

    `drift_kind` is "linear", "exp+linear", or "auto" (chosen by BIC).
    """
    windows = find_calibrations(t_s, p_kpa, kind=kind, reference_kpa=reference_kpa, **find_kwargs)
    if len(windows) < 2:
        raise ValueError(f"found {len(windows)} {kind} calibration sequence(s); at least two are needed")
    mid = np.array([(w.start_s + w.end_s) / 2 for w in windows])
    offsets = np.array([w.offset_kpa for w in windows])
    if drift_kind == "auto":
        model = select_drift_model(mid, offsets, t0_s=float(t_s[0]))
    else:
        model = fit_drift(mid, offsets, kind=drift_kind, t0_s=float(t_s[0]))
    corrected = apply_drift(t_s, p_kpa, model, mask_windows=windows)
    return {"windows": windows, "model": model, "corrected_kpa": corrected}


# --------------------------- non-self-calibrating ----------------------------

def resolvable_constituents(duration_s: float, rayleigh: float = 1.0) -> tuple[str, ...]:
    """Constituents separable over the record (Rayleigh criterion, as in T_TIDE/UTide).

    Two constituents are fitted together only if their frequencies differ by at
    least `rayleigh` / duration; otherwise their slow beat trades off against
    the drift. Major constituents are kept first (TIDAL_PERIODS_H order).
    """
    chosen: list[str] = []
    for name in TIDAL_PERIODS_H:
        f = 1 / (TIDAL_PERIODS_H[name] * 3600.0)
        if all(abs(f - 1 / (TIDAL_PERIODS_H[c] * 3600.0)) * duration_s >= rayleigh for c in chosen):
            chosen.append(name)
    return tuple(chosen)


def tidal_design(t_s: np.ndarray, constituents: tuple[str, ...] = tuple(TIDAL_PERIODS_H)) -> np.ndarray:
    cols = []
    for name in constituents:
        w = 2 * np.pi / (TIDAL_PERIODS_H[name] * 3600.0)
        cols += [np.cos(w * t_s), np.sin(w * t_s)]
    return np.column_stack(cols)


def estimate_linear_drift(t_s: np.ndarray, p_kpa: np.ndarray, *, remove_tides: bool = True,
                          decimate_s: float = 600.0, model: str = "auto") -> dict:
    """Jointly fit an offset, a linear trend, and tidal harmonics; report the trend.

    Quartz gauges often settle exponentially after deployment before drifting
    linearly. `model="exp+linear"` adds a 1 − exp(−t/τ) term (τ searched on a
    grid); `"auto"` keeps it only when it lowers the BIC. Samples are
    block-averaged to `decimate_s` first. The trend's standard error is
    inflated by the lag-1 autocorrelation of the residuals (effective sample size).
    """
    t = np.asarray(t_s, dtype=np.float64)
    p = np.asarray(p_kpa, dtype=np.float64)
    ok = np.isfinite(p)
    t, p = t[ok], p[ok]
    if decimate_s and len(t) > 1 and decimate_s > np.median(np.diff(t)):
        keys = np.floor((t - t[0]) / decimate_s).astype(np.int64)
        uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
        t = np.bincount(inv, weights=t) / counts
        p = np.bincount(inv, weights=p) / counts
    t0 = float(t[0])
    years = (t - t0) / SECONDS_PER_YEAR
    base = [np.ones_like(t), years] + ([tidal_design(t, resolvable_constituents(t[-1] - t[0]))] if remove_tides else [])

    def fit(extra: list[np.ndarray]):
        design = np.column_stack(base + extra)
        coef, *_ = np.linalg.lstsq(design, p, rcond=None)
        resid = p - design @ coef
        return design, coef, resid, float(resid @ resid)

    design, coef, resid, rss = fit([])
    tau = None
    profile: list[tuple[float, float]] = []      # (rss, rate) for each τ on the grid
    if model in ("auto", "exp+linear") and len(p) > 50:
        best = None
        grid = np.geomspace(2, 200, 40)
        for tau_days in grid:
            trial = fit([1 - np.exp(-years * 365.25 / tau_days)])
            profile.append((trial[3], float(trial[1][1])))
            if best is None or trial[3] < best[1][3]:
                best = (tau_days, trial)
        # Refine τ between the grid neighbours of the best point: a grid-step
        # misfit in τ leaks straight into the linear rate on short records.
        from scipy.optimize import minimize_scalar
        k = int(np.argmin(np.abs(grid - best[0])))
        lo, hi = np.log(grid[max(0, k - 1)]), np.log(grid[min(len(grid) - 1, k + 1)])
        opt = minimize_scalar(lambda lt: fit([1 - np.exp(-years * 365.25 / np.exp(lt))])[3], bounds=(lo, hi), method="bounded")
        refined = fit([1 - np.exp(-years * 365.25 / np.exp(opt.x))])
        if refined[3] <= best[1][3]:
            best = (float(np.exp(opt.x)), refined)
            profile.append((refined[3], float(refined[1][1])))
        n = len(p)
        bic = lambda r, k: n * np.log(max(r, 1e-30) / n) + k * np.log(n)
        if model == "exp+linear" or bic(best[1][3], design.shape[1] + 2) < bic(rss, design.shape[1]):
            tau, (design, coef, resid, rss) = best[0], best[1]
    dof = max(1, len(p) - design.shape[1])
    cov = np.linalg.pinv(design.T @ design) * (resid @ resid) / dof
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 2 else 0.0
    inflation = np.sqrt((1 + r1) / (1 - r1)) if -1 < r1 < 1 else 1.0
    stderr = float(np.sqrt(max(cov[1, 1], 0)) * inflation)
    if tau and profile:
        # Profile likelihood over τ: settling and linear drift trade off on short
        # records, so every τ within Δ(−2 log L) ≤ 4 (with the effective sample
        # size) is plausible; half the spread of their rates is about one σ.
        n_eff = max(10.0, len(p) * (1 - r1) / (1 + r1)) if -1 < r1 < 1 else float(len(p))
        floor = min(r for r, _ in profile)
        plausible = [rate for r, rate in profile if n_eff * np.log(r / floor) <= 4.0]
        stderr = max(stderr, (max(plausible) - min(plausible)) / 4.0)
    return {"rate_kpa_per_yr": float(coef[1]), "rate_stderr_kpa_per_yr": stderr,
            "offset_kpa": float(coef[0]), "t0_s": t0, "rms_residual_kpa": float(np.sqrt(np.mean(resid ** 2))),
            "residual_lag1_autocorr": r1, "n_points": int(len(p)),
            "model": "exp+linear" if tau else "linear",
            "exp_amp_kpa": float(coef[-1]) if tau else None, "exp_tau_days": float(tau) if tau else None,
            "confound": "A linear trend from one non-calibrating gauge includes any real vertical "
                        "deformation; use a co-located self-calibrating gauge or a known drift to separate them."}


def apply_known_drift(t_s: np.ndarray, p_kpa: np.ndarray, *, rate_kpa_per_yr: float, t0_s: float | None = None,
                      offset_kpa: float = 0.0) -> np.ndarray:
    """Remove a known linear drift (rate from a calibration, a co-located gauge, or the manufacturer)."""
    t = np.asarray(t_s, dtype=np.float64)
    t0 = float(t[0]) if t0_s is None else float(t0_s)
    return np.asarray(p_kpa, dtype=np.float64) - (offset_kpa + rate_kpa_per_yr * (t - t0) / SECONDS_PER_YEAR)
