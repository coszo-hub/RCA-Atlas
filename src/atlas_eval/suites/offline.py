"""Offline suites over real fixtures and labelled questions: earthquake catalog tools and task routing."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

from atlas_tasks import earthquakes as eq
from atlas_tasks.router import TASKS, route

from .. import plotstyle as ps
from ..stats import bootstrap_macro_f1, mcnemar, wilson
from .base import Metric, Suite, Summary, ok_records
from .scientific import confusion_figure

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "src" / "atlas_worker" / "test" / "fixtures"
BRIDGE = ROOT / "src" / "atlas_eval" / "js" / "worker_bridge.mjs"


def node_bridge(payload: dict) -> object:
    result = subprocess.run(["node", str(BRIDGE)], input=json.dumps(payload), capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-500:])
    return json.loads(result.stdout)


# =============================================================================
# Earthquake catalog: counts, filters, histograms, cross-implementation agreement
# =============================================================================

HEADER = "yyyymmdd HHMMSSS.SS Lat(D M)  Lon(D M)  Depth    MW NWR GAP DMIN  RMS  ERH  ERZ            ID         PMom    SMom"


def synthetic_day(day: str, seed: int, edge: str) -> tuple[str, list[dict]]:
    """A daily file with seeded events plus one class of edge rows; returns (text, valid events)."""
    rng = np.random.default_rng(seed)
    stamp = day.replace("-", "")
    n = int(rng.integers(0, 120))
    rows, events = [HEADER], []
    for k in range(n):
        h, m = int(rng.integers(0, 24)), int(rng.integers(0, 60))
        s = float(np.round(rng.uniform(0, 59.99), 2))
        if edge == "rollover" and k == 0:
            s = 60.00
        mag = float(np.round(rng.normal(0.4, 0.4), 2))
        if edge == "negative" and k < 5:
            mag = -abs(mag) - 0.01
        depth = float(np.round(rng.uniform(0.5, 2.5), 2))
        rows.append(f"{stamp} {h:02d}{m:02d} {s:5.2f} 45 {rng.uniform(55, 58):5.2f} 130 {rng.uniform(0, 2):5.2f} "
                    f"{depth:6.2f} {mag:6.2f} {int(rng.integers(5, 20)):2d} {int(rng.integers(90, 300)):3d}  0.5 0.04  0.5  1.0 "
                    f"{570000 + k:13d}      1.0e+18 1.0e+18")
        events.append({"mag": mag, "depth_km": depth})
    if edge == "short_rows":
        rows += [f"{stamp} 0101 10.00 45 56.00 130 1.00 1.20", f"{stamp} 0202"]
    if edge == "other_day":
        other = f"{int(stamp[:4])}{stamp[4:6]}{int(stamp[6:]) % 28 + 1:02d}"
        rows.append(f"{other} 0303 03.00 45 56.00 130  1.00   1.10   0.30 10 200  0.5 0.04  0.5  1.0        1           1e18 1e18")
    if edge == "bad_number":
        rows.append(f"{stamp} 0404 04.00 45 56.00 130  1.00   1.10   --   10 200  0.5 0.04  0.5  1.0        2           1e18 1e18")
    text = "\n".join(rows) + "\n"
    if edge == "crlf":
        text = text.replace("\n", "\r\n")
    if edge == "blank_lines":
        text = text.replace("\n", "\n\n")
    return text, events


def oracle_rows(text: str, stamp: str) -> list[list[str]]:
    """The catalog rule, applied as plainly as possible: first token is the day, 18+ columns, numbers parse."""
    rows = []
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 18 and p[0] == stamp:
            try:
                [float(v) for v in p[2:9]]
            except ValueError:
                continue
            rows.append(p)
    return rows


class QuakesSuite(Suite):
    name = "quakes"
    title = "Earthquake catalog: counts, filters, histograms"
    capability = "How many earthquakes; histogram panel for date ranges"
    axis = "accuracy"
    dataset = "quakes_v1.jsonl"
    description = ("Count, filter, and histogram questions over the three committed UW hypo71 fixture days plus 24 "
                   "synthetic days with edge rows (60.00 s rollover, negative magnitudes, short rows, rows dated "
                   "another day, a non-numeric value, CRLF and blank lines). Truth comes from an independent plain "
                   "reading of the catalog rule. The same files are also parsed by the two shipping parsers "
                   "(`axial_agent_tools.parse_hypo71` and the Worker's `parseHypo71Events`) to measure agreement.")

    def build_cases(self) -> list[dict]:
        cases = []
        real = [("2026-09-23", "2026-09-23"), ("2026-09-24", "2026-09-24"), ("2026-09-25", "2026-09-25"),
                ("2026-09-23", "2026-09-25"), ("2026-09-22", "2026-09-25")]
        for start, end in real:
            cases.append({"id": f"quakes-real-{len(cases) + 1:02d}", "source": "fixture", "start": start, "end": end, "by": "day"})
        for start, end, filt in (("2026-09-24", "2026-09-24", {"min_mag": 0.5}), ("2026-09-23", "2026-09-24", {"min_mag": 1.0}),
                                 ("2026-09-23", "2026-09-25", {"max_depth_km": 1.5}), ("2026-09-23", "2026-09-24", {"min_mag": 0.0, "max_mag": 0.5})):
            cases.append({"id": f"quakes-real-{len(cases) + 1:02d}", "source": "fixture", "start": start, "end": end, "by": "day", "filter": filt})
        cases.append({"id": f"quakes-real-{len(cases) + 1:02d}", "source": "fixture", "start": "2026-09-23", "end": "2026-09-25", "by": "magnitude"})
        cases.append({"id": f"quakes-real-{len(cases) + 1:02d}", "source": "fixture", "start": "2026-09-24", "end": "2026-09-24", "by": "hour"})
        edges = ["none", "rollover", "negative", "short_rows", "other_day", "bad_number", "crlf", "blank_lines"]
        for i in range(24):
            day = f"2026-08-{i + 1:02d}"
            cases.append({"id": f"quakes-synth-{i + 1:02d}", "source": "synthetic", "start": day, "end": day, "by": "day",
                          "edge": edges[i % len(edges)], "seed": 5000 + i})
        return cases

    def files_for(self, case) -> dict[str, str]:
        if case["source"] == "fixture":
            return {p.stem.split("_")[1]: p.read_text() for p in FIXTURES.glob("hypo71_*.dat")}
        text, _ = synthetic_day(case["start"], case["seed"], case["edge"])
        return {case["start"].replace("-", ""): text}

    def run_case(self, case, ctx):
        files = self.files_for(case)
        with tempfile.TemporaryDirectory() as tmp:
            for stamp, text in files.items():
                Path(tmp, f"hypo71_{stamp}.dat").write_text(text, newline="")
            events, missing = eq.load_events(case["start"], case["end"], eq.directory_loader(Path(tmp)))
        f = case.get("filter", {})
        events = eq.select(events, **f)
        hist = eq.histogram(events, by=case["by"], start=case["start"], end=case["end"])
        days = [d for d in eq.days_between(case["start"], case["end"]) if d.replace("-", "") in files]
        sys.path.insert(0, str(ROOT / "src" / "axial_earthquakes"))
        from axial_agent_tools import parse_hypo71 as legacy_parse
        legacy = sum(1 for d in days for e in legacy_parse(files[d.replace("-", "")]) if e["event_date_utc"] == d)
        js = node_bridge({"op": "parse", "files": [[files[d.replace("-", "")], d.replace("-", "")] for d in days]})
        return {"count": len(events), "missing": missing, "histogram": hist,
                "unfiltered_counts": {"atlas_tasks": None, "axial_agent_tools": legacy, "worker_js": sum(len(x) for x in js)},
                "unfiltered_atlas": sum(len(eq.parse_hypo71(files[d.replace('-', '')], d)) for d in days)}

    def truth(self, case) -> dict:
        files = self.files_for(case)
        rows = []
        for d in eq.days_between(case["start"], case["end"]):
            stamp = d.replace("-", "")
            if stamp in files:
                rows += oracle_rows(files[stamp], stamp)
        f = case.get("filter", {})
        keep = [r for r in rows if (f.get("min_mag") is None or float(r[8]) >= f["min_mag"])
                and (f.get("max_mag") is None or float(r[8]) <= f["max_mag"])
                and (f.get("max_depth_km") is None or float(r[7]) <= f["max_depth_km"])]
        missing = [d for d in eq.days_between(case["start"], case["end"]) if d.replace("-", "") not in files]
        per_day = Counter(f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:]}" for r in keep)
        return {"count": len(keep), "missing": missing, "unfiltered": len(rows),
                "per_day": [per_day.get(d, 0) for d in eq.days_between(case["start"], case["end"])],
                "mags": [float(r[8]) for r in keep]}

    def score_case(self, case, output):
        t = self.truth(case)
        hist_ok = True
        if case["by"] == "day":
            hist_ok = output["histogram"]["counts"] == t["per_day"]
        elif case["by"] == "magnitude":
            edges = np.asarray(output["histogram"]["bin_edges"])
            hist_ok = list(np.histogram(t["mags"], bins=edges)[0]) == output["histogram"]["counts"] and sum(output["histogram"]["counts"]) == t["count"]
        elif case["by"] == "hour":
            hist_ok = sum(output["histogram"]["counts"]) == t["count"] and len(output["histogram"]["counts"]) == 24
        u = output["unfiltered_counts"]
        agree = {"atlas_tasks": output["unfiltered_atlas"] == t["unfiltered"],
                 "axial_agent_tools": u["axial_agent_tools"] == t["unfiltered"],
                 "worker_js": u["worker_js"] == t["unfiltered"]}
        return {"count_correct": output["count"] == t["count"] and output["missing"] == t["missing"],
                "histogram_correct": hist_ok, "truth_count": t["count"], "agree": agree,
                "disagreements": {k: v for k, v in {"axial_agent_tools": u["axial_agent_tools"], "worker_js": u["worker_js"],
                                                     "atlas_tasks": output["unfiltered_atlas"]}.items() if v != t["unfiltered"]}}

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        both = wilson(sum(s["count_correct"] and s["histogram_correct"] for s in sc), len(sc))
        metrics = [Metric("Count and histogram exactly right", *both, n=len(sc), target=1.0),
                   Metric("Count exactly right (with missing days reported)", *wilson(sum(s["count_correct"] for s in sc), len(sc)), n=len(sc)),
                   Metric("Histogram exactly right", *wilson(sum(s["histogram_correct"] for s in sc), len(sc)), n=len(sc))]
        rows = []
        for impl in ("atlas_tasks", "axial_agent_tools", "worker_js"):
            a = wilson(sum(s["agree"][impl] for s in sc), len(sc))
            metrics.append(Metric(f"Unfiltered day count agrees with the catalog rule: {impl}", *a, n=len(sc)))
            bad = [r["case"].get("edge", r["case"]["id"]) for r in recs if not r["scores"]["agree"][impl]]
            rows.append({"implementation": impl, "agreement": a[0], "disagrees_on": sorted(set(bad))})
        return Summary(metrics[0], metrics, {"implementations": rows})


# =============================================================================
# Task routing (per-task priority)
# =============================================================================


class RoutingSuite(Suite):
    name = "routing"
    title = "Per-task routing"
    capability = "Recognise which task a question is, so the right tool or prompt answers it"
    axis = "routing"
    dataset = "routing_v1.jsonl"
    description = ("156 questions labelled with one of 15 task types (10–12 each, written before the rules, half "
                   "paraphrased without the obvious keyword). The new rule-based router (`atlas_tasks/router_rules.json`) "
                   "was tuned on the dev half only and is scored on the held-out test half. The baseline is the "
                   "deployed Worker's own decision logic (live day count → named download / compact → inventory → "
                   "research), run unchanged through Node.")

    def run_all(self, cases: list[dict]) -> list[dict]:
        baseline = node_bridge({"op": "route", "questions": [c["question"] for c in cases]})
        return [{"router": route(c["question"]).task, "worker": b} for c, b in zip(cases, baseline)]

    def run_case(self, case, ctx):
        raise NotImplementedError("routing runs as a batch")

    def score_case(self, case, output):
        return {"router_correct": output["router"] == case["task"], "worker_correct": output["worker"] == case["task"]}

    def summarize(self, records):
        recs = ok_records(records)
        test = [r for r in recs if r["case"]["split"] == "test"]
        dev = [r for r in recs if r["case"]["split"] == "dev"]
        labels = list(TASKS)
        metrics = []
        for name, subset in (("held-out test", test), ("dev (rules tuned here)", dev)):
            for sysname in ("router", "worker"):
                acc = wilson(sum(r["scores"][f"{sysname}_correct"] for r in subset), len(subset))
                label = "new router" if sysname == "router" else "deployed Worker"
                metrics.append(Metric(f"Accuracy, {label}, {name}", *acc, n=len(subset), target=0.9 if sysname == "router" and name == "held-out test" else None))
        for sysname, label in (("router", "new router"), ("worker", "deployed Worker")):
            f1 = bootstrap_macro_f1([r["case"]["task"] for r in test], [r["output"][sysname] for r in test], labels)
            metrics.append(Metric(f"Macro-F1 over 15 tasks, {label}, test", *f1, n=len(test)))
        hard = [r for r in test if r["case"]["difficulty"] == "hard"]
        metrics.append(Metric("Accuracy on paraphrased (hard) test questions, new router",
                              *wilson(sum(r["scores"]["router_correct"] for r in hard), len(hard)), n=len(hard)))
        test_stat = mcnemar([r["scores"]["router_correct"] for r in test], [r["scores"]["worker_correct"] for r in test])
        per_task = []
        for task in labels:
            sub = [r for r in test if r["case"]["task"] == task]
            if sub:
                per_task.append({"task": task, "n": len(sub),
                                 "router_recall": sum(r["scores"]["router_correct"] for r in sub) / len(sub),
                                 "worker_recall": sum(r["scores"]["worker_correct"] for r in sub) / len(sub)})
        confusion = [{"true": t, **{p: sum(1 for r in test if r["case"]["task"] == t and r["output"]["router"] == p) for p in labels}}
                     for t in labels]
        misses = [{"question": r["case"]["question"], "gold": r["case"]["task"], "router": r["output"]["router"]}
                  for r in test if not r["scores"]["router_correct"]]
        notes = [f"McNemar, new router vs deployed Worker on the test split: router-only correct {test_stat['only_a']}, "
                 f"Worker-only correct {test_stat['only_b']}, p = {test_stat['p_value']:.2g}.",
                 "The Worker has no route for 11 of the 15 tasks, so its ceiling on this set is the share of questions "
                 "in its four classes; the comparison shows coverage, not a tuned competitor."]
        return Summary(metrics[0], metrics, {"per_task": per_task, "confusion": confusion, "router_misses": misses}, notes)

    def figures(self, records, outdir):
        s = self.summarize(records)
        rows = s.tables["per_task"]
        fig, ax = ps.new(6.4, 0.3 * len(rows) + 1.1)
        y = np.arange(len(rows))[::-1]
        h = 0.36
        ax.barh(y + h / 2, [r["router_recall"] for r in rows], height=h - 0.04, color=ps.SERIES[0], label="new router")
        ax.barh(y - h / 2, [r["worker_recall"] for r in rows], height=h - 0.04, color=ps.SERIES[1], label="deployed Worker")
        ax.set_yticks(y, [r["task"] for r in rows], fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Recall on held-out test questions")
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, fontsize=8)
        ax.grid(axis="y", visible=False)
        ax.set_title("Which task is this question? Recall per task", pad=22)
        paths = [ps.save(fig, outdir / "routing_per_task.png")]
        paths.append(confusion_figure(s.tables["confusion"], list(TASKS), "New router confusion (test split)",
                                      outdir / "routing_confusion.png", size=5.2))
        return paths
