"""Known-answer suites for the numerical sandbox tools.

Each case is a seeded synthetic record with an injected, known truth (a fault,
a clock error, a velocity change, a sensor drift). The tool must recover it.
This is the standard recovery (synthetic injection) test used to validate
geophysical processing: it isolates the algorithm from data availability and
measures error as a function of signal-to-noise ratio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from atlas_tasks import dvv as dvv_mod
from atlas_tasks import gaps as gaps_mod
from atlas_tasks import pressure as pressure_mod
from atlas_tasks import timing as timing_mod

from .. import plotstyle as ps
from .. import synth
from ..stats import bootstrap, bootstrap_f1, bootstrap_ratio, mcnemar, wilson
from .base import Metric, Suite, Summary, ok_records

REPO_SRC = Path(__file__).resolve().parents[2]


# =============================================================================
# Data faults: gaps versus timing errors
# =============================================================================

FAULT_KINDS = ["gap", "zero_fill", "nan_fill", "flatline", "spike", "duplicate", "backstep"]
FAMILY = {k: ("timing_error" if k in gaps_mod.TIMING_FAMILY else "data_gap") for k in FAULT_KINDS + ["jitter"]}


def match_intervals(truth: list[dict], found: list[dict], tol: float) -> dict[str, list[int]]:
    """Greedy one-to-one matching of same-kind intervals that overlap within `tol` seconds."""
    counts: dict[str, list[int]] = {}
    used = set()
    for t in truth:
        hit = None
        for j, f in enumerate(found):
            if j in used or f["kind"] != t["kind"]:
                continue
            if f["start_s"] <= t["end_s"] + tol and f["end_s"] >= t["start_s"] - tol:
                hit = j
                break
        c = counts.setdefault(t["kind"], [0, 0, 0])
        if hit is None:
            c[2] += 1
        else:
            used.add(hit)
            c[0] += 1
    for j, f in enumerate(found):
        if j not in used:
            counts.setdefault(f["kind"], [0, 0, 0])[1] += 1
    return counts


class GapsSuite(Suite):
    name = "gaps"
    title = "Data-fault diagnosis (gaps vs timing errors)"
    capability = "Diagnose the type of error in a record: data gaps or timing errors"
    axis = "detection"
    dataset = "gaps_v1.jsonl"
    description = ("Each case is a regularly sampled record (0.125–60 s period) with 0–4 injected faults of seven "
                   "kinds. A finding counts when its kind matches and its interval overlaps the truth within 1.5 "
                   "sample periods. The existing `coszo_pressure_detect_gaps` (anomaly algorithm) is scored on the "
                   "`gap` kind as a baseline.")

    def build_cases(self) -> list[dict]:
        cases = []
        for i in range(120):
            rng = np.random.default_rng(1000 + i)
            period = float(rng.choice([0.125, 1.0, 15.0, 60.0]))
            n = int(rng.choice([2000, 5000, 20000]))
            n_faults = 0 if rng.random() < 0.15 else int(rng.integers(1, 5))
            slots = np.sort(rng.choice(np.arange(200, n - 400, 350), size=n_faults, replace=False)) if n_faults else []
            faults = []
            for start in slots:
                kind = str(rng.choice(FAULT_KINDS))
                f = {"kind": kind, "start": int(start)}
                if kind == "gap":
                    f["length"] = int(rng.integers(1, 200))
                elif kind in ("zero_fill", "nan_fill"):
                    f["length"] = int(rng.integers(3, 300))
                elif kind == "flatline":
                    f["length"] = int(rng.integers(20, 300))
                elif kind == "duplicate":
                    f["length"] = int(rng.integers(1, 6))
                elif kind == "spike":
                    f["size"] = float(np.round(rng.uniform(1.0, 25.0), 2))
                elif kind == "backstep":
                    f["size_s"] = float(np.round(rng.uniform(0.5, 5.0) * period, 6))
                faults.append(f)
            cases.append({"id": f"gaps-{i + 1:03d}", "n": n, "period_s": period, "seed": 1000 + i, "faults": faults,
                          "families": sorted({FAMILY[f["kind"]] for f in faults})})
        return cases

    def run_case(self, case, ctx):
        s = synth.faulty_series(n=case["n"], period_s=case["period_s"], seed=case["seed"], faults=case["faults"])
        out = gaps_mod.diagnose_series(s["t_s"], s["x"])
        baseline = None
        try:
            sys.path.insert(0, str(REPO_SRC / "coszo_hub_tools"))
            from gap_detection import detect_gaps
            res = detect_gaps(list(map(float, s["t_s"])), case["period_s"], "anomaly")
            t = s["t_s"]
            baseline = [{"kind": "gap", "start_s": float(t[i]), "end_s": float(t[i + 1])} for i in res.gap_indices]
        except Exception as exc:  # the baseline rejects some faulty timestamp sets outright
            baseline = {"error": f"{type(exc).__name__}: {exc}"}
        return {"findings": out["findings"], "families": out["families"], "truth": s["truth"], "baseline_gaps": baseline}

    def score_case(self, case, output):
        tol = 1.5 * case["period_s"]
        counts = match_intervals(output["truth"], output["findings"], tol)
        truth_gaps = [t for t in output["truth"] if t["kind"] == "gap"]
        base = output["baseline_gaps"]
        base_counts = match_intervals(truth_gaps, base, tol).get("gap", [0, 0, 0]) if isinstance(base, list) else [0, 0, len(truth_gaps)]
        new_gap = counts.get("gap", [0, 0, 0])
        return {"counts": counts, "verdict_correct": sorted(output["families"]) == case["families"],
                "exact": all(c[1] == 0 and c[2] == 0 for c in counts.values()),
                "gap_new": new_gap, "gap_baseline": base_counts, "baseline_error": not isinstance(base, list),
                "gap_new_exact": new_gap[1] == 0 and new_gap[2] == 0,
                "gap_base_exact": base_counts[1] == 0 and base_counts[2] == 0}

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        tot = lambda k, i: [s["counts"].get(k, [0, 0, 0])[i] for s in sc]
        all_tp = [sum(c[0] for c in s["counts"].values()) for s in sc]
        all_fp = [sum(c[1] for c in s["counts"].values()) for s in sc]
        all_fn = [sum(c[2] for c in s["counts"].values()) for s in sc]
        f1 = bootstrap_f1(all_tp, all_fp, all_fn)
        verdict = wilson(sum(s["verdict_correct"] for s in sc), len(sc))
        exact = wilson(sum(s["exact"] for s in sc), len(sc))
        rows = []
        for kind in FAULT_KINDS + ["jitter"]:
            tp, fp, fn = sum(tot(kind, 0)), sum(tot(kind, 1)), sum(tot(kind, 2))
            if tp + fp + fn == 0:
                continue
            kf = bootstrap_f1(tot(kind, 0), tot(kind, 1), tot(kind, 2))
            rows.append({"kind": kind, "family": FAMILY[kind], "truth": tp + fn, "found": tp + fp, "tp": tp,
                         "precision": tp / (tp + fp) if tp + fp else float("nan"),
                         "recall": tp / (tp + fn) if tp + fn else float("nan"),
                         "f1": kf[0], "f1_low": kf[1], "f1_high": kf[2]})
        g_new = [s["gap_new"] for s in sc]
        g_base = [s["gap_baseline"] for s in sc]
        f_new = bootstrap_f1(*zip(*g_new))
        f_base = bootstrap_f1(*zip(*g_base))
        test = mcnemar([s["gap_new_exact"] for s in sc], [s["gap_base_exact"] for s in sc])
        metrics = [
            Metric("Fault detection F1 (all kinds, micro)", *f1, n=len(sc), target=0.9),
            Metric("Error-type verdict accuracy (gap / timing / both / clean)", *verdict, n=len(sc), target=0.9),
            Metric("Cases diagnosed exactly (no miss, no false alarm)", *exact, n=len(sc)),
            Metric("Gap F1: new diagnose_series", *f_new, n=len(sc)),
            Metric("Gap F1: existing coszo_pressure_detect_gaps", *f_base, n=len(sc),
                   note=f"{sum(s['baseline_error'] for s in sc)} case(s) rejected by the baseline"),
        ]
        notes = [f"McNemar on per-case exact gap detection, new vs existing: new-only {test['only_a']}, "
                 f"existing-only {test['only_b']}, p = {test['p_value']:.3g}."]
        return Summary(metrics[0], metrics, {"per_kind": rows}, notes)

    def figures(self, records, outdir):
        rows = self.summarize(records).tables["per_kind"]
        fig, ax = ps.new(6.4, 0.32 * len(rows) + 1.0)
        y = np.arange(len(rows))[::-1]
        for yi, r in zip(y, rows):
            color = ps.SERIES[0] if r["family"] == "data_gap" else ps.SERIES[1]
            ax.plot([r["f1_low"], r["f1_high"]], [yi, yi], color=color, lw=2, solid_capstyle="round")
            ax.plot(r["f1"], yi, "o", color=color, ms=7, mec=ps.SURFACE, mew=1.5)
            ax.text(1.02, yi, f"{r['f1']:.2f}  (n={r['truth']})", va="center", fontsize=8, color=ps.INK_2,
                    transform=ax.get_yaxis_transform())
        ax.set_yticks(y, [r["kind"] for r in rows])
        ax.set_xlim(0, 1)
        ax.set_xlabel("F1 with 95% bootstrap interval")
        ax.plot([], [], "o", color=ps.SERIES[0], label="data gap family")
        ax.plot([], [], "o", color=ps.SERIES[1], label="timing error family")
        ax.legend(loc="lower left", fontsize=8)
        ax.set_title("Fault detection by kind")
        return [ps.save(fig, outdir / "gaps_per_kind.png")]


# =============================================================================
# Clock errors from ambient-noise cross-correlation
# =============================================================================

TIMING_KINDS = ["none", "jump", "drift", "jump+drift"]


class TimingSuite(Suite):
    name = "timing"
    title = "Clock-error recovery (CCF, peak lag, Δt)"
    capability = "Perform cross-correlation, compute peak lags, and correct timing errors"
    axis = "accuracy"
    dataset = "timing_v1.jsonl"
    description = ("Each case is a three-day 8 Hz station pair recording one diffuse wavefield; station B has a "
                   "known hourly clock error (none, a jump, a linear drift, or both) and some cases have zero-filled "
                   "hours. The SNR grid brackets the detection limit of hourly stacks. The chronos-equivalent pipeline "
                   "must recover Δt(B); it may decline to pick noisy bins (pick-quality gate) and may stack longer "
                   "(6 h, 1 day) when hours are too noisy. Each hour is scored with the estimate of the bin that holds "
                   "it. Because the CCF only constrains Δt relative to an anchor period, errors are measured after "
                   "removing their median. 'Confidently wrong' hours carry an estimate more than 0.5 s off.")

    def build_cases(self) -> list[dict]:
        cases = []
        i = 0
        for kind in TIMING_KINDS:
            for snr in (0.08, 0.12, 0.18, 0.25, 0.35):
                for rep in range(3):
                    rng = np.random.default_rng(2000 + i)
                    case = {"id": f"timing-{i + 1:03d}", "kind": kind, "snr": snr, "seed": 2000 + i, "days": 3, "fs": 8.0,
                            "travel_s": float(np.round(rng.uniform(1.5, 8.0), 3)),
                            "jump_s": float(np.round(rng.uniform(1.5, 6.0) * rng.choice([-1, 1]), 3)) if "jump" in kind else 0.0,
                            "drift_s_per_day": float(np.round(rng.uniform(0.1, 0.5) * rng.choice([-1, 1]), 3)) if "drift" in kind else 0.0,
                            "jump_hour": int(rng.integers(18, 54)),
                            "gap_hours": sorted(int(h) for h in rng.choice(np.arange(2, 70), 2, replace=False)) if rng.random() < 0.3 else []}
                    cases.append(case)
                    i += 1
        return cases

    @staticmethod
    def truth(case) -> np.ndarray:
        return synth.clock_error_series(case["kind"], int(case["days"] * 24), np.random.default_rng(0),
                                        jump_s=case["jump_s"], drift_s_per_day=case["drift_s_per_day"], jump_hour=case["jump_hour"])

    def run_case(self, case, ctx):
        truth = self.truth(case)
        a, b = synth.station_pair(days=case["days"], fs=case["fs"], travel_s=case["travel_s"], snr=case["snr"],
                                  clock_dt_hourly=truth, seed=case["seed"], gap_hours=tuple(case["gap_hours"]))
        res = timing_mod.clock_track(a, b, case["fs"])
        bin_h = int(round(res["bin_s"] / 3600))
        per_hour = np.full(len(truth), np.nan)
        for start, v in zip(res["bin_start_s"], res["delta_t_s"]):
            h0 = int(round(start / 3600))
            per_hour[h0:h0 + bin_h] = v
        return {"bin_s": res["bin_s"], "valid_fraction": res["valid_fraction"],
                "delta_t_s": [None if not np.isfinite(v) else float(v) for v in per_hour],
                "truth_s": truth.tolist(), "diagnosis": res["diagnosis"].to_dict(), "anchor_lag_s": res["anchor_lag_s"]}

    def score_case(self, case, output):
        est = np.array([np.nan if v is None else v for v in output["delta_t_s"]])
        truth = np.asarray(output["truth_s"])
        usable = np.array([h not in set(case["gap_hours"]) for h in range(len(truth))])
        covered = usable & np.isfinite(est)
        err = est[covered] - truth[covered]
        if len(err):
            err -= np.median(err)
        diag = output["diagnosis"]
        jumps = diag["jumps"]
        tol_h = max(2, output["bin_s"] / 3600)
        tp = fp = fn = 0
        size_err = None
        if "jump" in case["kind"]:
            near = [j for j in jumps if abs(j["time_s"] / 3600 - case["jump_hour"]) <= tol_h]
            tp, fn = (1, 0) if near else (0, 1)
            fp = len(jumps) - len(near[:1])
            if near:
                size_err = abs(near[0]["size_s"] - (-case["jump_s"]))
        else:
            fp = len(jumps)
        drift = diag.get("drift_s_per_day")
        drift_err = abs(drift - case["drift_s_per_day"]) if "drift" in case["kind"] and drift is not None and np.isfinite(drift) else None
        good = int((np.abs(err) <= 0.125).sum())
        return {"within_1_sample": good, "n_covered": int(covered.sum()), "n_hours": int(usable.sum()),
                "confidently_wrong": int((np.abs(err) > 0.5).sum()),
                "rmse_s": float(np.sqrt(np.mean(err ** 2))) if len(err) else None,
                "kind_correct": diag["kind"] == case["kind"], "predicted_kind": diag["kind"], "bin_h": output["bin_s"] / 3600,
                "abstained": diag["kind"] == "insufficient_snr",
                "jump_tp": tp, "jump_fp": fp, "jump_fn": fn, "jump_size_err_s": size_err, "drift_err_s_per_day": drift_err,
                "pass": (diag["kind"] == case["kind"] and covered.sum() > 0 and good / covered.sum() >= 0.95
                         and fn == 0 and (size_err is None or size_err <= 0.5))}

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        acc = bootstrap_ratio([s["within_1_sample"] for s in sc], [s["n_covered"] for s in sc])
        cov = bootstrap_ratio([s["n_covered"] for s in sc], [s["n_hours"] for s in sc])
        wrong = bootstrap_ratio([s["confidently_wrong"] for s in sc], [s["n_covered"] for s in sc])
        kind = wilson(sum(s["kind_correct"] for s in sc), len(sc))
        passed = wilson(sum(s["pass"] for s in sc), len(sc))
        jf1 = bootstrap_f1([s["jump_tp"] for s in sc], [s["jump_fp"] for s in sc], [s["jump_fn"] for s in sc])
        size = bootstrap([s["jump_size_err_s"] for s in sc if s["jump_size_err_s"] is not None])
        drift = bootstrap([s["drift_err_s_per_day"] for s in sc if s["drift_err_s_per_day"] is not None])
        metrics = [
            Metric("Case pass rate (diagnosis right, jump found, ≥95% of estimated hours within 1 sample)", *passed, n=len(sc), target=0.9),
            Metric("Hours with an estimate (coverage)", *cov, n=sum(s["n_hours"] for s in sc)),
            Metric("Estimated hours within one sample (0.125 s)", *acc, n=sum(s["n_covered"] for s in sc), target=0.95),
            Metric("Estimated hours confidently wrong (> 0.5 s)", *wrong, n=sum(s["n_covered"] for s in sc), higher_is_better=False, target=0.02),
            Metric("Error-kind classification accuracy", *kind, n=len(sc), target=0.9),
            Metric("Cases declined as too noisy to pick", *wilson(sum(s["abstained"] for s in sc), len(sc)), n=len(sc), higher_is_better=False),
            Metric("Clock-jump detection F1 (±2 h or one bin)", *jf1, n=len(sc)),
            Metric("Jump size absolute error", *size, n=sum(s["jump_size_err_s"] is not None for s in sc), unit="s", higher_is_better=False),
            Metric("Drift rate absolute error", *drift, n=sum(s["drift_err_s_per_day"] is not None for s in sc), unit="s/day", higher_is_better=False),
        ]
        by_snr = []
        for snr in sorted({r["case"]["snr"] for r in recs}):
            sub = [r["scores"] for r in recs if r["case"]["snr"] == snr]
            p = wilson(sum(s["pass"] for s in sub), len(sub))
            a = bootstrap_ratio([s["within_1_sample"] for s in sub], [s["n_covered"] for s in sub])
            c = bootstrap_ratio([s["n_covered"] for s in sub], [s["n_hours"] for s in sub])
            by_snr.append({"snr": snr, "n": len(sub), "pass": p[0], "pass_low": p[1], "pass_high": p[2],
                           "hourly_acc": a[0], "hourly_low": a[1], "hourly_high": a[2], "coverage": c[0],
                           "stack_hours": float(np.median([s["bin_h"] for s in sub])),
                           "kind_acc": sum(s["kind_correct"] for s in sub) / len(sub)})
        labels = TIMING_KINDS + ["insufficient_snr"]
        confusion = [{"true": t, **{p: sum(1 for r in recs if r["case"]["kind"] == t and r["scores"]["predicted_kind"] == p)
                                    for p in labels}} for t in TIMING_KINDS]
        notes = ["Accuracy is over the hours that received an estimate; coverage says how many did. A bin whose pick "
                 "quality is below the noise-only 99th percentile is left empty instead of guessed."]
        return Summary(metrics[0], metrics, {"by_snr": by_snr, "confusion": confusion}, notes)

    def figures(self, records, outdir):
        s = self.summarize(records)
        rows = s.tables["by_snr"]
        fig, ax = ps.new(5.8, 3.1)
        x = [r["snr"] for r in rows]
        for key, lo, hi, label, color in (("pass", "pass_low", "pass_high", "case pass rate", ps.SERIES[0]),
                                          ("hourly_acc", "hourly_low", "hourly_high", "estimated hours within 0.125 s", ps.SERIES[1])):
            ax.fill_between(x, [r[lo] for r in rows], [r[hi] for r in rows], color=color, alpha=0.15, lw=0)
            ax.plot(x, [r[key] for r in rows], "-o", color=color, label=label, mec=ps.SURFACE, mew=1.5)
        ax.plot(x, [r["coverage"] for r in rows], "-o", color=ps.SERIES[2], label="hours with an estimate", mec=ps.SURFACE, mew=1.5)
        for r in rows:
            ax.annotate(f"{r['stack_hours']:g} h", (r["snr"], 0.03), ha="center", fontsize=7, color=ps.MUTED)
        ax.set_xscale("log")
        ax.set_xticks(x, [f"{v:g}" for v in x])
        ax.minorticks_off()
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Coherent-to-incoherent amplitude ratio per station (SNR); labels: stack length used")
        ax.set_ylabel("Proportion")
        ax.legend(loc="center right", fontsize=8)
        ax.set_title("Clock-error recovery against noise (95% intervals)")
        paths = [ps.save(fig, outdir / "timing_vs_snr.png")]
        paths.append(confusion_figure(s.tables["confusion"], TIMING_KINDS + ["insufficient_snr"], "Clock-error kind: truth vs diagnosis",
                                      outdir / "timing_confusion.png"))
        return paths


def confusion_figure(rows: list[dict], labels: list[str], title: str, path: Path, size: float = 3.6) -> Path:
    """Counts of truth (rows) against prediction (columns); rows may be fewer than columns."""
    true_labels = [r["true"] for r in rows]
    m = np.array([[r.get(p, 0) for p in labels] for r in rows], float)
    fig, ax = ps.new(size + 0.8, size * (len(true_labels) / len(labels)) + 1.0)
    ax.grid(False)
    norm = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", [ps.SURFACE] + ps.SEQ)
    ax.imshow(norm, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(len(true_labels)):
        for j in range(len(labels)):
            if m[i, j]:
                ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=7,
                        color="#ffffff" if norm[i, j] > 0.55 else ps.INK)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(true_labels)), true_labels, fontsize=7)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ps.save(fig, path)


# =============================================================================
# dv/v
# =============================================================================

DVV_METHODS = ["stretching", "mwcs", "dtw"]


def dvv_tolerance(true: float) -> float:
    return 1e-4 + 0.1 * abs(true)


class DvvSuite(Suite):
    name = "dvv"
    title = "Relative velocity change (stretching, MWCS, DTW)"
    capability = "Measure dv/v by stretching, MWCS, and dynamic time warping"
    axis = "accuracy"
    dataset = "dvv_v1.jsonl"
    description = ("Each case stretches a synthetic CCF (ballistic arrivals plus exponential coda) by a known dv/v "
                   "between −1 % and +1 % and adds noise at a given SNR. A method passes when |error| ≤ 0.01 % + 10 % "
                   "of |dv/v|. Uncertainty calibration checks how often |error| ≤ 2 × the method's reported σ.")

    def build_cases(self) -> list[dict]:
        cases = []
        i = 0
        for true in (-0.01, -0.003, -0.001, -0.0003, 0.0, 0.0003, 0.001, 0.003, 0.01):
            for snr in (2, 5, 10, 30):
                for rep in range(2):
                    cases.append({"id": f"dvv-{i + 1:03d}", "dvv": true, "snr": snr, "seed": 3000 + i,
                                  "fs": 10.0, "maxlag_s": 60.0, "tmin": 10.0, "tmax": 50.0})
                    i += 1
        return cases

    def run_case(self, case, ctx):
        lags, ref = synth.synthetic_ccf(fs=case["fs"], maxlag_s=case["maxlag_s"], seed=case["seed"])
        rng = np.random.default_rng(case["seed"] + 1)
        cur = synth.noisy(synth.stretch_ccf(lags, ref, case["dvv"]), case["snr"], rng)
        ref = synth.noisy(ref, case["snr"] * 3, rng)  # a long-term reference stack is cleaner, not perfect
        out = {}
        for method in DVV_METHODS:
            kw = {"tmin": case["tmin"], "tmax": case["tmax"]}
            if method == "mwcs":
                kw.update(fmin=0.2, fmax=2.0)
            try:
                r = dvv_mod.measure(ref, cur, lags, method, **kw)
                out[method] = {"dvv": r.dvv, "error": r.error, "quality": r.quality}
            except ValueError as exc:
                out[method] = {"dvv": None, "error": None, "message": str(exc)}
        return out

    def score_case(self, case, output):
        scores = {}
        for method in DVV_METHODS:
            r = output[method]
            if r["dvv"] is None:
                scores[method] = {"pass": False, "abs_err": None, "covered": None}
                continue
            err = r["dvv"] - case["dvv"]
            scores[method] = {"pass": abs(err) <= dvv_tolerance(case["dvv"]), "abs_err": abs(err), "err": err,
                              "covered": abs(err) <= 2 * r["error"] if r["error"] else None}
        return scores

    def summarize(self, records):
        recs = ok_records(records)
        metrics, rows = [], []
        for method in DVV_METHODS:
            sc = [r["scores"][method] for r in recs]
            p = wilson(sum(s["pass"] for s in sc), len(sc))
            mae = bootstrap([s["abs_err"] * 100 for s in sc if s["abs_err"] is not None])
            bias = bootstrap([s["err"] * 100 for s in sc if s.get("err") is not None])
            cov = [s["covered"] for s in sc if s["covered"] is not None]
            c = wilson(sum(cov), len(cov))
            metrics.append(Metric(f"{method}: pass rate", *p, n=len(sc), target=0.9))
            metrics.append(Metric(f"{method}: mean |error|", *mae, n=len(sc), unit="% dv/v", higher_is_better=False))
            rows.append({"method": method, "pass": p[0], "pass_low": p[1], "pass_high": p[2], "mae_pct": mae[0],
                         "bias_pct": bias[0], "bias_low": bias[1], "bias_high": bias[2], "coverage_2sigma": c[0],
                         "coverage_low": c[1], "coverage_high": c[2]})
        by_snr = []
        for snr in sorted({r["case"]["snr"] for r in recs}):
            row = {"snr": snr}
            for method in DVV_METHODS:
                sub = [r["scores"][method] for r in recs if r["case"]["snr"] == snr]
                row[method] = float(np.median([s["abs_err"] * 100 for s in sub if s["abs_err"] is not None]))
                row[method + "_pass"] = sum(s["pass"] for s in sub) / len(sub)
            by_snr.append(row)
        headline = metrics[0]
        notes = ["Coverage near 95 % means the reported σ is honest; far below means it is overconfident."]
        return Summary(headline, metrics, {"by_method": rows, "by_snr": by_snr}, notes)

    def figures(self, records, outdir):
        s = self.summarize(records)
        rows = s.tables["by_snr"]
        fig, ax = ps.new(5.6, 3.0)
        x = [r["snr"] for r in rows]
        for method, color in zip(DVV_METHODS, ps.SERIES):
            ax.plot(x, [r[method] for r in rows], "-o", color=color, label=method, mec=ps.SURFACE, mew=1.5)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks(x, [f"{v:g}" for v in x])
        ax.minorticks_off()
        ax.axhline(0.01, color=ps.AXIS, lw=1)
        ax.text(x[-1], 0.0105, "0.01 % floor of the tolerance", ha="right", va="bottom", fontsize=7, color=ps.MUTED)
        ax.set_xlabel("SNR of the current CCF")
        ax.set_ylabel("Median |error| (% dv/v)")
        ax.legend(fontsize=8)
        ax.set_title("dv/v error against noise")
        paths = [ps.save(fig, outdir / "dvv_error_vs_snr.png")]
        recs = ok_records(records)
        fig, axes = ps.new(7.2, 2.6, ncols=3, sharey=True)
        lim = 1.25
        for ax, method, color in zip(axes, DVV_METHODS, ps.SERIES):
            t = [r["case"]["dvv"] * 100 for r in recs if r["output"][method]["dvv"] is not None]
            e = [r["output"][method]["dvv"] * 100 for r in recs if r["output"][method]["dvv"] is not None]
            ax.plot([-lim, lim], [-lim, lim], color=ps.AXIS, lw=1)
            ax.plot(t, e, "o", color=color, ms=4, alpha=0.8, mec=ps.SURFACE, mew=0.8)
            ax.set_title(method)
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)
            ax.set_xlabel("True dv/v (%)")
        axes[0].set_ylabel("Estimated dv/v (%)")
        paths.append(ps.save(fig, outdir / "dvv_true_vs_est.png"))
        return paths


# =============================================================================
# Pressure calibration and drift
# =============================================================================

PASS_KPA = 0.1        # 1 cm of seawater
PASS_RATE = 0.1       # 1 cm/yr


class PressureSuite(Suite):
    name = "pressure"
    title = "Pressure calibration (A-0-A, SCPR) and linear drift"
    capability = "Find calibration sequences and apply calibration; estimate and apply linear drift"
    axis = "accuracy"
    dataset = "pressure_v1.jsonl"
    description = ("Synthetic 1500 m bottom-pressure records (five tidal constituents, 0.01–0.03 kPa noise, 30 s "
                   "sampling) with a known sensor drift (linear ± exponential). A-0-A and SCPR cases include "
                   "calibration sequences every 7–30 days; SCPR cases put the piston-gauge reference inside or "
                   "outside the tidal range, with or without the command-log schedule. Calibration passes when the "
                   "corrected record is within 0.1 kPa (≈1 cm of water) RMS of the truth; drift estimation passes "
                   "within 0.1 kPa/yr. Cases with real uplift test the documented drift/deformation confound.")

    def build_cases(self) -> list[dict]:
        cases = []
        for i in range(72):
            rng = np.random.default_rng(4000 + i)
            task = ["a0a", "scpr", "drift"][i % 3]
            c = {"id": f"pressure-{i + 1:03d}", "task": task, "seed": 4000 + i,
                 "days": int(rng.choice([90, 180, 365])), "dt_s": 30.0,
                 "rate_kpa_per_yr": float(np.round(rng.uniform(-5, 5), 3)),
                 "noise_kpa": float(rng.choice([0.01, 0.03]))}
            if task in ("a0a", "scpr"):
                c.update(exp_amp_kpa=float(np.round(rng.uniform(0, 3), 3)) if rng.random() < 0.5 else 0.0,
                         exp_tau_days=float(np.round(rng.uniform(10, 90), 1)),
                         cal_every_days=float(rng.choice([7, 14, 30])))
                if task == "a0a":
                    c["cal_reference_kpa"] = 101.325
                else:
                    c["reference_inside_tides"] = bool(rng.random() < 0.5)
                    c["cal_reference_kpa"] = 15300.0 + (float(np.round(rng.uniform(-8, 8), 2)) if c["reference_inside_tides"]
                                                        else float(np.round(rng.choice([-1, 1]) * rng.uniform(30, 60), 2)))
                    c["schedule_given"] = bool(rng.random() < 0.5)
            else:
                c.update(exp_amp_kpa=float(np.round(rng.uniform(0.5, 2), 3)) if rng.random() < 0.33 else 0.0,
                         exp_tau_days=20.0,
                         uplift_kpa_per_yr=float(np.round(rng.uniform(2, 5), 3)) if rng.random() < 0.25 else 0.0)
            cases.append(c)
        return cases

    def record(self, case):
        kw = dict(days=case["days"], dt_s=case["dt_s"], seed=case["seed"], rate_kpa_per_yr=case["rate_kpa_per_yr"],
                  exp_amp_kpa=case.get("exp_amp_kpa", 0.0), exp_tau_days=case.get("exp_tau_days", 30.0),
                  noise_kpa=case["noise_kpa"], uplift_kpa_per_yr=case.get("uplift_kpa_per_yr", 0.0))
        if case["task"] in ("a0a", "scpr"):
            kw.update(calibration=case["task"], cal_every_days=case["cal_every_days"],
                      cal_reference_kpa=case["cal_reference_kpa"])
        return synth.pressure_record(**kw)

    def run_case(self, case, ctx):
        r = self.record(case)
        t, p = r["t_s"], r["reading_kpa"]
        if case["task"] == "drift":
            est = pressure_mod.estimate_linear_drift(t, p)
            return {"rate_kpa_per_yr": est["rate_kpa_per_yr"], "rate_stderr": est["rate_stderr_kpa_per_yr"]}
        schedule = [(w["start_s"], w["end_s"]) for w in r["calibrations"]] if case.get("schedule_given") else None
        try:
            out = pressure_mod.calibrate(t, p, kind=case["task"], reference_kpa=case["cal_reference_kpa"],
                                         drift_kind="auto", schedule=schedule)
        except ValueError as exc:
            return {"failed": str(exc), "n_truth": len(r["calibrations"])}
        resid = out["corrected_kpa"] - r["true_kpa"]
        found = [(w.start_s, w.end_s) for w in out["windows"]]
        truth = [(w["start_s"], w["end_s"]) for w in r["calibrations"]]
        matched = sum(any(a <= te and b >= ts for a, b in found) for ts, te in truth)
        offset_err = []
        for w in out["windows"]:
            m = (t >= w.start_s) & (t <= w.end_s)
            offset_err.append(abs(w.offset_kpa - float(np.mean(r["drift_kpa"][m]))))
        return {"n_truth": len(truth), "n_found": len(found), "n_matched": matched,
                "offset_mae_kpa": float(np.mean(offset_err)) if offset_err else None,
                "residual_rms_kpa": float(np.sqrt(np.nanmean(resid ** 2))), "model": out["model"].to_dict()}

    def score_case(self, case, output):
        if case["task"] == "drift":
            err = abs(output["rate_kpa_per_yr"] - case["rate_kpa_per_yr"])
            return {"pass": err <= PASS_RATE, "rate_err": err, "confounded": case.get("uplift_kpa_per_yr", 0) > 0,
                    "curved": case.get("exp_amp_kpa", 0) > 0, "covered_2sigma": err <= 2 * output["rate_stderr"]}
        if output.get("failed"):
            return {"pass": False, "tp": 0, "fp": 0, "fn": output["n_truth"], "residual_rms_kpa": None, "offset_mae_kpa": None}
        return {"pass": output["residual_rms_kpa"] <= PASS_KPA, "residual_rms_kpa": output["residual_rms_kpa"],
                "offset_mae_kpa": output["offset_mae_kpa"], "tp": output["n_matched"],
                "fp": output["n_found"] - output["n_matched"], "fn": output["n_truth"] - output["n_matched"],
                "model_kind": output["model"]["kind"], "curved": case.get("exp_amp_kpa", 0) > 0}

    def summarize(self, records):
        recs = ok_records(records)
        part = lambda task, cond=lambda r: True: [r for r in recs if r["case"]["task"] == task and cond(r)]
        metrics, rows = [], []
        core = [r for r in recs if not r["scores"].get("confounded")]
        p_all = wilson(sum(r["scores"]["pass"] for r in core), len(core))
        metrics.append(Metric("Pass rate, all calibration and drift cases (excl. uplift confound)", *p_all, n=len(core), target=0.9))
        for label, sub in (("A-0-A", part("a0a")), ("SCPR, schedule given", part("scpr", lambda r: r["case"]["schedule_given"])),
                           ("SCPR, detected, reference outside tides", part("scpr", lambda r: not r["case"]["schedule_given"] and not r["case"]["reference_inside_tides"])),
                           ("SCPR, detected, reference inside tides", part("scpr", lambda r: not r["case"]["schedule_given"] and r["case"]["reference_inside_tides"]))):
            if not sub:
                continue
            sc = [r["scores"] for r in sub]
            p = wilson(sum(s["pass"] for s in sc), len(sc))
            det = bootstrap_f1([s["tp"] for s in sc], [s["fp"] for s in sc], [s["fn"] for s in sc])
            rms = bootstrap([s["residual_rms_kpa"] for s in sc if s["residual_rms_kpa"] is not None], np.median)
            metrics.append(Metric(f"{label}: corrected within 1 cm RMS", *p, n=len(sc)))
            rows.append({"subset": label, "n": len(sc), "pass": p[0], "pass_ci": [p[1], p[2]], "detection_f1": det[0],
                         "median_residual_kpa": rms[0],
                         "offset_mae_kpa": float(np.mean([s["offset_mae_kpa"] for s in sc if s["offset_mae_kpa"] is not None] or [np.nan]))})
        for label, cond in (("Linear drift, linear sensor", lambda r: not r["scores"]["curved"] and not r["scores"]["confounded"]),
                            ("Linear drift, sensor with exponential settling", lambda r: r["scores"]["curved"] and not r["scores"]["confounded"]),
                            ("Linear drift with real uplift (confound)", lambda r: r["scores"]["confounded"])):
            sub = part("drift", cond)
            if not sub:
                continue
            sc = [r["scores"] for r in sub]
            p = wilson(sum(s["pass"] for s in sc), len(sc))
            err = bootstrap([s["rate_err"] for s in sc], np.median)
            metrics.append(Metric(f"{label}: rate within 0.1 kPa/yr", *p, n=len(sc)))
            metrics.append(Metric(f"{label}: error within the reported 2σ", *wilson(sum(s["covered_2sigma"] for s in sc), len(sc)), n=len(sc),
                                  note="expected to fail: σ cannot know about real deformation" if "confound" in label else ""))
            rows.append({"subset": label, "n": len(sc), "pass": p[0], "pass_ci": [p[1], p[2]], "median_rate_err_kpa_per_yr": err[0]})
        notes = ["A trend fitted to one non-calibrating gauge absorbs real uplift; the confound subset is expected to fail "
                 "and is excluded from the headline."]
        return Summary(metrics[0], metrics, {"subsets": rows}, notes)

    def figures(self, records, outdir):
        rows = self.summarize(records).tables["subsets"]
        fig, ax = ps.new(6.6, 0.38 * len(rows) + 1.0)
        y = np.arange(len(rows))[::-1]
        for yi, r in zip(y, rows):
            color = ps.SERIES[1] if "confound" in r["subset"] else ps.SERIES[0]
            ax.plot(r["pass_ci"], [yi, yi], color=color, lw=2, solid_capstyle="round")
            ax.plot(r["pass"], yi, "o", color=color, ms=7, mec=ps.SURFACE, mew=1.5)
            ax.text(1.02, yi, f"{r['pass']:.0%}  (n={r['n']})", va="center", fontsize=8, color=ps.INK_2,
                    transform=ax.get_yaxis_transform())
        ax.set_yticks(y, [r["subset"] for r in rows], fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Pass rate with 95% Wilson interval")
        ax.set_title("Pressure calibration and drift correction")
        return [ps.save(fig, outdir / "pressure_subsets.png")]
