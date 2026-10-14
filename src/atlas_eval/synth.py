"""Seeded synthetic data with known ground truth for the numerical tool suites.

Every generator is a pure function of its parameters and an integer seed, so a
case in a frozen dataset file is reproduced bit-for-bit from its spec.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

from atlas_tasks.timing import shift_series

# --------------------------------------------------------------------------
# Station pair with a clock error on station B
# --------------------------------------------------------------------------


def bandlimited_noise(rng: np.random.Generator, n: int, fs: float, band: tuple[float, float]) -> np.ndarray:
    sos = butter(4, [band[0], min(band[1], 0.45 * fs)], btype="band", fs=fs, output="sos")
    x = sosfiltfilt(sos, rng.standard_normal(n))
    return x / np.std(x)


def clock_error_series(kind: str, hours: int, rng: np.random.Generator, *, jump_s: float = 0.0,
                       drift_s_per_day: float = 0.0, jump_hour: int | None = None) -> np.ndarray:
    """Hourly Δt(B) truth. Kinds: none, jump, drift, jump+drift. The last day is anchored at 0."""
    t_days = np.arange(hours) / 24.0
    dt = np.zeros(hours)
    if "drift" in kind:
        dt += drift_s_per_day * (t_days - t_days[-1])
    if "jump" in kind:
        h = jump_hour if jump_hour is not None else int(rng.integers(hours // 4, 3 * hours // 4))
        dt[:h] += jump_s           # the error is fixed at hour h: before it, B was late by jump_s
    return dt


def station_pair(*, days: float, fs: float, travel_s: float, snr: float, clock_dt_hourly: np.ndarray,
                 seed: int, band: tuple[float, float] = (0.5, 3.0), gap_hours: tuple[int, ...] = ()) -> tuple[np.ndarray, np.ndarray]:
    """Two records of one diffuse wavefield: B sees it `travel_s` later plus B's clock error.

    `snr` is the coherent-to-incoherent amplitude ratio at each station; each hour
    in `gap_hours` is zero-filled on station B, as an ObsPy merge leaves a gap.
    """
    rng = np.random.default_rng(seed)
    hour_n = int(round(3600 * fs))
    hours = int(round(days * 24))
    a_parts, b_parts = [], []
    pad = int(round((abs(travel_s) + np.max(np.abs(clock_dt_hourly)) + 5) * fs))
    for h in range(hours):
        src = bandlimited_noise(rng, hour_n + 2 * pad, fs, band)
        a = src[pad:pad + hour_n]
        b = shift_series(src, fs, travel_s + clock_dt_hourly[h])[pad:pad + hour_n]
        noise_a = bandlimited_noise(rng, hour_n, fs, band) / max(snr, 1e-6)
        noise_b = bandlimited_noise(rng, hour_n, fs, band) / max(snr, 1e-6)
        a_parts.append(a + noise_a)
        b_parts.append(b + noise_b)
    a, b = np.concatenate(a_parts), np.concatenate(b_parts)
    for h in gap_hours:
        b[h * hour_n:(h + 1) * hour_n] = 0.0
    return a, b


# --------------------------------------------------------------------------
# Cross-correlation functions with a known velocity change
# --------------------------------------------------------------------------


def synthetic_ccf(*, fs: float, maxlag_s: float, seed: int, travel_s: float = 4.0, coda_decay_s: float = 20.0,
                  band: tuple[float, float] = (0.2, 2.0)) -> tuple[np.ndarray, np.ndarray]:
    """A symmetric ballistic arrival plus an exponentially decaying coda on both sides."""
    rng = np.random.default_rng(seed)
    lags = np.arange(-int(maxlag_s * fs), int(maxlag_s * fs) + 1) / fs
    coda = bandlimited_noise(rng, len(lags), fs, band) * np.exp(-np.abs(lags) / coda_decay_s)
    f0 = np.mean(band)
    ricker = lambda t: (1 - 2 * (np.pi * f0 * t) ** 2) * np.exp(-(np.pi * f0 * t) ** 2)
    ballistic = 2.0 * (ricker(lags - travel_s) + ricker(lags + travel_s))
    ref = ballistic + coda
    return lags, ref / np.max(np.abs(ref))


def stretch_ccf(lags: np.ndarray, ref: np.ndarray, dvv: float) -> np.ndarray:
    """Current CCF for a homogeneous velocity change: cur(t) = ref(t·(1 + dv/v))."""
    return np.interp(lags * (1.0 + dvv), lags, ref, left=0.0, right=0.0)


def noisy(x: np.ndarray, snr: float, rng: np.random.Generator) -> np.ndarray:
    return x + rng.standard_normal(len(x)) * np.std(x) / snr


# --------------------------------------------------------------------------
# Seafloor pressure with tides, drift, and calibration sequences
# --------------------------------------------------------------------------

TIDES = {  # constituent: (period hours, amplitude kPa)
    "M2": (12.4206012, 8.5), "S2": (12.0, 2.6), "N2": (12.65834751, 1.7),
    "K1": (23.93447213, 4.6), "O1": (25.81933871, 2.9),
}


def tides_kpa(t_s: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = np.zeros_like(t_s, dtype=np.float64)
    for period_h, amp in TIDES.values():
        out += amp * np.cos(2 * np.pi * t_s / (period_h * 3600.0) + rng.uniform(0, 2 * np.pi))
    return out


def drift_kpa(t_s: np.ndarray, *, rate_kpa_per_yr: float, exp_amp_kpa: float = 0.0, exp_tau_days: float = 30.0) -> np.ndarray:
    years = t_s / (365.25 * 86400.0)
    return rate_kpa_per_yr * years + exp_amp_kpa * (1 - np.exp(-t_s / (exp_tau_days * 86400.0)))


def pressure_record(*, days: float, dt_s: float, seed: int, base_kpa: float = 15300.0, rate_kpa_per_yr: float = 0.0,
                    exp_amp_kpa: float = 0.0, exp_tau_days: float = 30.0, uplift_kpa_per_yr: float = 0.0,
                    noise_kpa: float = 0.01, calibration: str | None = None, cal_every_days: float = 14.0,
                    cal_duration_s: float = 600.0, cal_reference_kpa: float = 101.325, settle_s: float = 120.0,
                    transient_kpa: float = 0.5, first_cal_day: float = 1.0) -> dict:
    """A bottom-pressure record whose sensor reads true pressure + drift + noise.

    With `calibration="a0a"` the valve periodically switches the gauge to the
    housing's internal pressure (≈ atmospheric, `cal_reference_kpa`); with
    `"scpr"` a piston gauge applies `cal_reference_kpa` near seafloor pressure.
    Either way the gauge reads reference + drift there, after an exponential
    thermal transient of `transient_kpa` with time constant `settle_s / 4`.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days * 86400.0, dt_s)
    true = base_kpa + tides_kpa(t, rng) - uplift_kpa_per_yr * t / (365.25 * 86400.0)
    drift = drift_kpa(t, rate_kpa_per_yr=rate_kpa_per_yr, exp_amp_kpa=exp_amp_kpa, exp_tau_days=exp_tau_days)
    reading = true + drift + rng.standard_normal(len(t)) * noise_kpa
    windows = []
    if calibration:
        start = first_cal_day * 86400.0
        while start + cal_duration_s < t[-1]:
            m = (t >= start) & (t < start + cal_duration_s)
            since = t[m] - start
            transient = transient_kpa * np.exp(-since / (settle_s / 4.0))
            reading[m] = cal_reference_kpa + drift[m] + transient + rng.standard_normal(m.sum()) * noise_kpa
            windows.append({"start_s": float(start), "end_s": float(start + cal_duration_s),
                            "drift_kpa": float(np.mean(drift[m]))})
            start += cal_every_days * 86400.0
    return {"t_s": t, "reading_kpa": reading, "true_kpa": true, "drift_kpa": drift, "calibrations": windows}


# --------------------------------------------------------------------------
# Time series with injected data faults
# --------------------------------------------------------------------------


def faulty_series(*, n: int, period_s: float, seed: int, faults: list[dict]) -> dict:
    """A regularly sampled series with injected faults and their truth intervals.

    Fault kinds: gap (samples removed), zero_fill / nan_fill (values replaced),
    duplicate (timestamps repeated), backstep (timestamps step backwards),
    flatline (a stuck constant value), spike (isolated outliers).
    Truth intervals are in seconds of the original sampling grid.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) * period_s
    x = np.cumsum(rng.standard_normal(n)) * 0.05 + np.sin(2 * np.pi * t / (period_s * 500)) * 3 + 10
    keep = np.ones(n, dtype=bool)
    extra_t, extra_x, truth = [], [], []
    for fault in faults:
        kind, i0, length = fault["kind"], int(fault["start"]), int(fault.get("length", 1))
        i1 = min(n, i0 + length)
        interval = {"kind": kind, "start_s": float(t[i0]), "end_s": float(t[i1 - 1])}
        if kind == "gap":
            keep[i0:i1] = False
            interval.update(start_s=float(t[i0 - 1]), end_s=float(t[i1]) if i1 < n else float(t[-1]))
        elif kind == "zero_fill":
            x[i0:i1] = 0.0
        elif kind == "nan_fill":
            x[i0:i1] = np.nan
        elif kind == "flatline":
            x[i0:i1] = x[i0]
        elif kind == "spike":
            x[i0] += fault.get("size", 25.0) * np.sign(rng.standard_normal())
        elif kind == "duplicate":
            extra_t.extend(t[i0:i1])
            extra_x.extend(x[i0:i1])
        elif kind == "backstep":
            t[i0:] -= fault.get("size_s", 3.5 * period_s)
            interval.update(start_s=float(t[i0 - 1]), end_s=float(t[i0 - 1]))
        truth.append(interval)
    times = np.concatenate([t[keep], np.asarray(extra_t)])
    values = np.concatenate([x[keep], np.asarray(extra_x)])
    if extra_t:  # duplicates sit next to their originals in record order
        order = np.argsort(np.concatenate([np.flatnonzero(keep), np.asarray(
            [np.flatnonzero(t == v)[0] for v in extra_t]) + 0.5]), kind="stable")
        times, values = times[order], values[order]
    return {"t_s": times, "x": values, "truth": truth, "period_s": period_s}
