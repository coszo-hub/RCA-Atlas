"""Interval estimates and paired comparisons for evaluation metrics.

- Proportions (pass rates, accuracy): Wilson score interval, which stays
  inside [0, 1] and behaves at small n and at 0 % or 100 %.
- Means and other statistics: percentile bootstrap over cases (seeded).
- Two systems on the same cases: paired bootstrap of the difference, and an
  exact McNemar test on discordant pass/fail pairs.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np
from scipy.stats import binomtest, norm

Z95 = float(norm.ppf(0.975))


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    """(point, low, high) for a binomial proportion."""
    if n == 0:
        return (math.nan, math.nan, math.nan)
    p = successes / n
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def bootstrap(values: Sequence[float], stat: Callable[[np.ndarray], float] = np.mean, n_boot: int = 2000,
              seed: int = 0, alpha: float = 0.05) -> tuple[float, float, float]:
    """(point, low, high) percentile bootstrap of `stat` over the values (NaNs dropped)."""
    x = np.asarray([v for v in values if v is not None], dtype=np.float64)
    x = x[np.isfinite(x)]
    if not len(x):
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    boots = np.array([stat(x[rng.integers(0, len(x), len(x))]) for _ in range(n_boot)])
    return (float(stat(x)), float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2)))


def bootstrap_ratio(numerators: Sequence[float], denominators: Sequence[float], n_boot: int = 2000,
                    seed: int = 0) -> tuple[float, float, float]:
    """Micro-averaged ratio Σnum/Σden with cases resampled together (for example pooled recall)."""
    num, den = np.asarray(numerators, float), np.asarray(denominators, float)
    if den.sum() == 0:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(num), len(num))
        d = den[idx].sum()
        boots.append(num[idx].sum() / d if d else np.nan)
    boots = np.asarray(boots)
    boots = boots[np.isfinite(boots)]
    return (float(num.sum() / den.sum()), float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975)))


def f1_from_counts(tp: float, fp: float, fn: float) -> float:
    return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else math.nan


def bootstrap_f1(tps: Sequence[float], fps: Sequence[float], fns: Sequence[float], n_boot: int = 2000,
                 seed: int = 0) -> tuple[float, float, float]:
    tp, fp, fn = (np.asarray(v, float) for v in (tps, fps, fns))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(tp), len(tp))
        boots.append(f1_from_counts(tp[idx].sum(), fp[idx].sum(), fn[idx].sum()))
    boots = np.asarray([b for b in boots if np.isfinite(b)])
    point = f1_from_counts(tp.sum(), fp.sum(), fn.sum())
    if not len(boots):
        return (point, math.nan, math.nan)
    return (point, float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975)))


def macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str] | None = None) -> float:
    labels = list(labels or sorted(set(gold)))
    scores = []
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        scores.append(f1_from_counts(tp, fp, fn) if (tp + fn) else math.nan)
    scores = [s if np.isfinite(s) else 0.0 for s in scores]
    return float(np.mean(scores)) if scores else math.nan


def bootstrap_macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str], n_boot: int = 2000,
                       seed: int = 0) -> tuple[float, float, float]:
    gold, pred = list(gold), list(pred)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(gold), len(gold))
        g = [gold[i] for i in idx]
        boots.append(macro_f1(g, [pred[i] for i in idx], [label for label in labels if label in g]))
    return (macro_f1(gold, pred, labels), float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975)))


def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float], n_boot: int = 4000, seed: int = 0) -> dict:
    """Mean of (a − b) over shared cases with a bootstrap CI and a two-sided p-value."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    rng = np.random.default_rng(seed)
    boots = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(n_boot)])
    p = 2 * min((boots <= 0).mean(), (boots >= 0).mean())
    return {"mean_diff": float(d.mean()), "low": float(np.quantile(boots, 0.025)),
            "high": float(np.quantile(boots, 0.975)), "p_value": float(min(1.0, p)), "n": int(len(d))}


def mcnemar(a_pass: Sequence[bool], b_pass: Sequence[bool]) -> dict:
    """Exact McNemar test: do two systems differ on the same pass/fail cases?"""
    only_a = sum(bool(x) and not bool(y) for x, y in zip(a_pass, b_pass))
    only_b = sum(bool(y) and not bool(x) for x, y in zip(a_pass, b_pass))
    n = only_a + only_b
    p = binomtest(only_a, n, 0.5).pvalue if n else 1.0
    return {"only_a": only_a, "only_b": only_b, "p_value": float(p)}


def percentile(values: Sequence[float], q: float) -> float:
    x = np.asarray([v for v in values if v is not None], float)
    return float(np.percentile(x, q)) if len(x) else math.nan


def fmt_ci(point: float, low: float, high: float, digits: int = 3, pct: bool = False) -> str:
    if not np.isfinite(point):
        return "n/a"
    k = 100 if pct else 1
    unit = "%" if pct else ""
    d = max(0, digits - 2) if pct else digits
    if not (np.isfinite(low) and np.isfinite(high)):
        return f"{point * k:.{d}f}{unit}"
    return f"{point * k:.{d}f}{unit} [{low * k:.{d}f}, {high * k:.{d}f}]"
