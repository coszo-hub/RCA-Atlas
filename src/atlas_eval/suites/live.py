"""Suites that exercise the deployed RCA Atlas Worker (retrieval and answers) and its question parsing."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

from atlas_tasks.earthquakes import parse_quake_request

from .. import plotstyle as ps
from ..stats import bootstrap, mcnemar, percentile, wilson
from .base import DATASETS, Metric, Suite, Summary, ok_records
from .offline import node_bridge

WORKER = "https://rca-atlas.quakehunt.workers.dev"
ORIGIN = "https://coszo.org"
V1 = Path(__file__).resolve().parents[2] / "model_eval" / "datasets"

# The v1 set names several tools that do not exist; these are the real tools that do that job.
TOOL_ALIASES = {
    "axial_daily_count": ["axial_count_events"], "axial_events_by_date": ["axial_search_events"],
    "axial_histogram": ["axial_activity_summary", "atlas_quake_histogram"], "axial_map": ["axial_plot_events", "axial_get_figure"],
    "axial_figure_retrieval": ["axial_get_figure", "axial_list_figures"], "qaqc_generate_plot": ["qaqc_generate_plots", "qaqc_pipeline_plan"],
    "chronfix_lookup": ["coszo_chronfix_model", "coszo_refresh_hys14_correction"], "chronfix_correct": ["coszo_hys14_correct_times"],
    "pi_portal_search": ["pi_portal_find_files", "pi_portal_browse"], "coszo_output_discovery": ["coszo_list_outputs", "coszo_output_status"],
    "nereus_file_status": [], "nereus_ping_status": [],
}


def ask_worker(query: str, *, quick: bool = False, model: str | None = None, tz: str | None = None,
               timeout: float = 90.0, endpoint: str = WORKER) -> tuple[dict, float]:
    body = {"query": query}
    if quick:
        body["answer_mode"] = "quick"
    if model:
        body["model"] = model
    if tz:
        body["tz"] = tz
    req = urllib.request.Request(f"{endpoint}/v1/answer", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "origin": ORIGIN, "user-agent": "rca-atlas-eval/1"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        data = {"error": f"HTTP {exc.code}", "body": exc.read().decode("utf-8", "replace")[:300]}
    except Exception as exc:
        data = {"error": f"{type(exc).__name__}: {exc}"}
    return data, (time.perf_counter() - t0) * 1000


def norm_collection(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def load_v1() -> list[dict]:
    questions = [json.loads(line) for line in (V1 / "rca_eval_v1.jsonl").read_text().splitlines() if line.strip()]
    gold = {g["question_id"]: g for g in (json.loads(line) for line in (V1 / "rca_eval_v1_gold.jsonl").read_text().splitlines() if line.strip())}
    return [{**q, "gold": gold.get(q["id"], {})} for q in questions]


# =============================================================================
# Earthquake question parsing (offline: the Worker's own function vs the new parser)
# =============================================================================


class QuakeQuestionsSuite(Suite):
    name = "quake_questions"
    title = "Earthquake question understanding (dates, ranges, magnitudes)"
    capability = "Understand which days and magnitudes 'how many earthquakes' means"
    axis = "robustness"
    dataset = "quake_questions_v1.jsonl"
    description = ("26 count questions with the intended UTC date range and magnitude floor (or none, when the "
                   "question names no period), at a fixed 'now' of 2026-09-25 12:00 UTC. The deployed Worker's "
                   "`axialDayWindow` (run unchanged through Node) is compared with the new `parse_quake_request`. "
                   "The Worker answers a count only for one day and ignores magnitude, so a range or a magnitude "
                   "filter it accepts is counted wrong, and a question it lets fall to the language model is not a count.")

    def run_all(self, cases):
        worker = node_bridge({"op": "window", "questions": [[c["question"], c["now_utc"], None] for c in cases]})
        out = []
        for c, w in zip(cases, worker):
            today = date.fromisoformat(c["now_utc"][:10])
            out.append({"worker": w and {"start": w["day"], "end": w["day"], "min_mag": None},
                        "parser": parse_quake_request(c["question"], today=today)})
        return out

    def score_case(self, case, output):
        exp = case["expected"]
        return {"parser_correct": output["parser"] == exp, "worker_correct": output["worker"] == exp,
                "range_or_filter": bool(exp and (exp["start"] != exp["end"] or exp["min_mag"] is not None))}

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        p = wilson(sum(s["parser_correct"] for s in sc), len(sc))
        w = wilson(sum(s["worker_correct"] for s in sc), len(sc))
        test = mcnemar([s["parser_correct"] for s in sc], [s["worker_correct"] for s in sc])
        sub = [s for s in sc if s["range_or_filter"]]
        metrics = [Metric("Correct date range and magnitude, new parser", *p, n=len(sc), target=0.9),
                   Metric("Correct date range and magnitude, deployed Worker", *w, n=len(sc)),
                   Metric("Range or magnitude questions, deployed Worker", *wilson(sum(s["worker_correct"] for s in sub), len(sub)), n=len(sub))]
        wrong = [{"question": r["case"]["question"], "expected": r["case"]["expected"], "worker": r["output"]["worker"],
                  "parser": r["output"]["parser"]} for r in recs if not (r["scores"]["worker_correct"] and r["scores"]["parser_correct"])]
        return Summary(metrics[0], metrics, {"disagreements": wrong},
                       [f"McNemar new vs Worker: new-only {test['only_a']}, Worker-only {test['only_b']}, p = {test['p_value']:.2g}."])


# =============================================================================
# Retrieval (live, no language model)
# =============================================================================


class RetrievalSuite(Suite):
    name = "retrieval"
    title = "Evidence retrieval (Graph-RAG hits)"
    capability = "Search and retrieve the right corpus evidence for a question"
    axis = "retrieval"
    dataset = "../../model_eval/datasets/rca_eval_v1.jsonl"
    requires = "live"
    description = ("The 60 questions of `model_eval/datasets/rca_eval_v1.jsonl` sent to the live Worker in quick "
                   "mode (retrieval and graph only, no language model). Gold chunk IDs come from "
                   "`rca_eval_v1_gold.jsonl`; questions without gold chunks are scored only on collections and tool "
                   "hints. Tool hints are the `/v1/tools` router's suggestions, checked for questions that need a tool "
                   "(v1 tool names mapped to the tools that exist).")

    def cases(self):
        return load_v1()

    def run_case(self, case, ctx):
        data, ms = ask_worker(case["question"], quick=True, endpoint=ctx.get("endpoint", WORKER))
        if data.get("error"):
            return {"error": data["error"], "latency_ms": ms}
        return {"latency_ms": ms, "hit_ids": [h["chunk_id"] for h in data.get("hits", [])],
                "hit_collections": [h["collection_id"] for h in data.get("hits", [])],
                "tool_hints": [t["name"] for t in data.get("tool_hints", [])],
                "neighbors": len(data.get("neighbors", []))}

    def score_case(self, case, output):
        gold = set(case["gold"].get("required_chunk_ids") or [])
        hits = output["hit_ids"]
        s = {"has_gold": bool(gold)}
        if gold:
            s["recall_at_5"] = len(set(hits[:5]) & gold) / len(gold)
            s["recall_at_10"] = len(set(hits[:10]) & gold) / len(gold)
            s["mrr"] = next((1 / i for i, h in enumerate(hits, 1) if h in gold), 0.0)
            s["hit_at_10"] = bool(set(hits[:10]) & gold)
        expected = {norm_collection(c) for c in case.get("expected_collections", [])}
        found = {norm_collection(c) for c in output["hit_collections"][:10]}
        s["collection_hit"] = bool(expected & found) if expected else None
        if case.get("answer_mode") == "tool" and case.get("expected_tool"):
            names = TOOL_ALIASES.get(case["expected_tool"], [case["expected_tool"]])
            s["tool_exists"] = bool(names)
            s["tool_hint_hit"] = bool(set(names) & set(output["tool_hints"])) if names else None
            s["tool_hint_any"] = bool(output["tool_hints"])
        return s

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        g = [s for s in sc if s["has_gold"]]
        tool = [s for s in sc if s.get("tool_hint_hit") is not None]
        metrics = [
            Metric("Gold evidence in top 10 (any required chunk)", *wilson(sum(s["hit_at_10"] for s in g), len(g)), n=len(g), target=0.8),
            Metric("Recall@5 of required chunks", *bootstrap([s["recall_at_5"] for s in g]), n=len(g)),
            Metric("Recall@10 of required chunks", *bootstrap([s["recall_at_10"] for s in g]), n=len(g)),
            Metric("MRR of first required chunk", *bootstrap([s["mrr"] for s in g]), n=len(g)),
            Metric("Expected collection in top 10", *wilson(sum(bool(s["collection_hit"]) for s in sc if s["collection_hit"] is not None),
                                                           sum(s["collection_hit"] is not None for s in sc)), n=sum(s["collection_hit"] is not None for s in sc)),
            Metric("Tool router suggests the needed tool", *wilson(sum(s["tool_hint_hit"] for s in tool), len(tool)), n=len(tool)),
            Metric("Tool router suggests any tool when one is needed", *wilson(sum(s["tool_hint_any"] for s in tool), len(tool)), n=len(tool)),
            Metric("Latency p50 (quick mode)", percentile([r["output"]["latency_ms"] for r in recs], 50) / 1000, n=len(recs), unit="s", higher_is_better=False),
            Metric("Latency p95 (quick mode)", percentile([r["output"]["latency_ms"] for r in recs], 95) / 1000, n=len(recs), unit="s", higher_is_better=False),
            Metric("Request success rate", *wilson(len(recs), len(records)), n=len(records)),
        ]
        cats = {}
        for r in recs:
            if r["scores"]["has_gold"]:
                cats.setdefault(r["case"]["category"], []).append(r["scores"])
        per_cat = [{"category": c, "n": len(v), "hit_at_10": float(np.mean([s["hit_at_10"] for s in v])),
                    "recall_at_10": float(np.mean([s["recall_at_10"] for s in v])), "mrr": float(np.mean([s["mrr"] for s in v]))}
                   for c, v in sorted(cats.items())]
        missing = sorted({r["case"]["expected_tool"] for r in recs if r["scores"].get("tool_exists") is False})
        notes = [f"v1 expected tools with no implementation at all: {', '.join(missing) or 'none'}."]
        return Summary(metrics[0], metrics, {"per_category": per_cat}, notes)

    def figures(self, records, outdir):
        rows = self.summarize(records).tables["per_category"]
        fig, ax = ps.new(6.2, 0.32 * len(rows) + 1.1)
        y = np.arange(len(rows))[::-1]
        h = 0.36
        ax.barh(y + h / 2, [r["hit_at_10"] for r in rows], height=h - 0.04, color=ps.SERIES[0], label="gold evidence in top 10")
        ax.barh(y - h / 2, [r["mrr"] for r in rows], height=h - 0.04, color=ps.SERIES[1], label="MRR")
        for yi, r in zip(y, rows):
            ax.text(1.01, yi, f"n={r['n']}", va="center", fontsize=7, color=ps.MUTED, transform=ax.get_yaxis_transform())
        ax.set_yticks(y, [r["category"] for r in rows], fontsize=8)
        ax.set_xlim(0, 1)
        ax.grid(axis="y", visible=False)
        ax.legend(loc="lower right", fontsize=8)
        ax.set_title("Retrieval by question category")
        return [ps.save(fig, outdir / "retrieval_per_category.png")]


# =============================================================================
# Answers (live, language model)
# =============================================================================

CITE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
NUMERIC_CLAIM = re.compile(r"(?<![\[\w])[-+]?\d+(?:\.\d+)?\s*(?:%|kpa|s\b|seconds|ms\b|cm|mm|earthquakes|events|quakes)", re.I)


def cited_numbers(answer: str) -> list[int]:
    out = []
    for m in CITE.finditer(answer):
        for part in re.split(r"\s*,\s*", m[1]):
            if re.search(r"[-–]", part):
                a, b = (int(x) for x in re.split(r"\s*[-–]\s*", part))
                out += list(range(a, b + 1))
            else:
                out.append(int(part))
    return out


class AnswersSuite(Suite):
    name = "answers"
    title = "End-to-end answers (Ask Atlas)"
    capability = "Answer research, inventory, download, and task questions with cited evidence"
    axis = "answer quality"
    dataset = "answers_extra_v1.jsonl"
    requires = "live"
    description = ("The 60 v1 questions plus the task questions from Maleen's notes, sent to the live Worker with "
                   "the default model route. Automatic checks: the request is served; every [n] citation points at "
                   "a listed source; the plain-text format the prompt demands (no Markdown asterisks or hashes); gold "
                   "entities and gold sources appear. For questions that need a computation the Worker cannot run, "
                   "the answer must not state a computed number. An optional LLM judge grades correctness against the "
                   "reference answer and support by the retrieved evidence.")

    def cases(self):
        extra = [json.loads(line) for line in (DATASETS / self.dataset).read_text().splitlines() if line.strip()]
        return load_v1() + extra

    def run_case(self, case, ctx):
        time.sleep(ctx.get("pace_s", 0))
        data, ms = ask_worker(case["question"], endpoint=ctx.get("endpoint", WORKER), model=ctx.get("model"))
        if data.get("error"):
            return {"error": data["error"], "latency_ms": ms}
        return {"latency_ms": ms, "answer": data.get("answer", ""), "answer_model": data.get("answer_model"),
                "citations": data.get("answer_citations", []), "hits": [{"title": h.get("title"), "excerpt": h.get("excerpt")}
                                                                       for h in data.get("hits", [])[:8]]}

    def score_case(self, case, output):
        answer = output["answer"]
        n_sources = len(output["citations"])
        refs = cited_numbers(answer)
        gold = case.get("gold", {})
        urls = {c.get("url", "").rstrip("/").lower() for c in output["citations"]} | {str(c.get("id", "")).lower() for c in output["citations"]}
        need = gold.get("required_citations") or []
        cited_gold = sum(1 for c in need if (c.get("url", "").rstrip("/").lower() in urls) or (str(c.get("source_id", "")).lower() in urls))
        entities = gold.get("required_entity_ids") or case.get("expected_entities") or []
        s = {
            "has_citation": bool(refs),
            "citations_valid": all(1 <= n <= n_sources for n in refs) if refs else None,
            "empty": not answer.strip(),
            "format_ok": "**" not in answer and not re.search(r"^\s*#", answer, re.M),
            "entity_recall": (sum(e.lower() in answer.lower() for e in entities) / len(entities)) if entities else None,
            "gold_source_recall": (cited_gold / len(need)) if need else None,
            "words": len(answer.split()),
            "is_tool_task": case.get("answer_mode") == "tool" or case.get("expects") == "computation",
        }
        if case.get("expects") == "computation":
            s["states_number"] = bool(NUMERIC_CLAIM.search(CITE.sub("", answer)))
        judge = output.get("judge")
        if judge:
            s.update({f"judge_{k}": v for k, v in judge.items() if k in ("correct", "supported", "abstained_properly")})
        return s

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        corpus = [s for s, r in zip(sc, recs) if r["case"].get("answer_mode") == "corpus"]
        comp = [s for s in sc if "states_number" in s]
        ent = [s["entity_recall"] for s in sc if s["entity_recall"] is not None]
        src = [s["gold_source_recall"] for s in sc if s["gold_source_recall"] is not None]
        first_ok = sum(1 for r in records if not r.get("first_error") and not r.get("error"))
        metrics = [
            Metric("Served on the first attempt", *wilson(first_ok, len(records)), n=len(records), target=0.98),
            Metric("Served after one slower retry", *wilson(len(recs), len(records)), n=len(records)),
            Metric("Every citation points at a listed source (answers that cite)", *wilson(sum(bool(s["citations_valid"]) for s in sc if s["citations_valid"] is not None),
                                                                                          sum(s["citations_valid"] is not None for s in sc)),
                   n=sum(s["citations_valid"] is not None for s in sc), target=1.0),
            Metric("Empty answers", *wilson(sum(s.get("empty", False) for s in sc), len(sc)), n=len(sc), higher_is_better=False),
            Metric("Corpus answers carry at least one citation", *wilson(sum(s["has_citation"] for s in corpus), len(corpus)), n=len(corpus)),
            Metric("Plain-text format the prompt requires", *wilson(sum(s["format_ok"] for s in sc), len(sc)), n=len(sc)),
            Metric("Gold entities named in the answer", *bootstrap(ent), n=len(ent)),
            Metric("Gold sources among the answer's citations", *bootstrap(src), n=len(src)),
            Metric("Computation questions with no numeric claim at all (regex; also flags quoted literature values)", *wilson(sum(not s["states_number"] for s in comp), len(comp)), n=len(comp)),
            Metric("Latency p50", percentile([r["output"]["latency_ms"] for r in recs], 50) / 1000, n=len(recs), unit="s", higher_is_better=False),
            Metric("Latency p95", percentile([r["output"]["latency_ms"] for r in recs], 95) / 1000, n=len(recs), unit="s", higher_is_better=False),
        ]
        judged = [s for s in sc if "judge_correct" in s]
        if judged:
            corr = [s["judge_correct"] for s in judged if s["judge_correct"] is not None]
            sup = [s["judge_supported"] for s in judged if s.get("judge_supported") is not None]
            metrics.insert(1, Metric("Judge: correct against the reference answer", *wilson(sum(c >= 1 for c in corr), len(corr)), n=len(corr), target=0.8,
                                     note="score ≥ 1 of 2 (partially or fully correct)"))
            metrics.insert(2, Metric("Judge: fully correct", *wilson(sum(c == 2 for c in corr), len(corr)), n=len(corr)))
            metrics.insert(3, Metric("Judge: every claim supported by the public excerpts (lower bound)", *wilson(sum(bool(x) for x in sup), len(sup)), n=len(sup),
                                     note="the judge sees 280-character excerpts; the answering model saw full chunks"))
            ab = [s["judge_abstained_properly"] for s in judged if s.get("judge_abstained_properly") is not None]
            metrics.insert(4, Metric("Judge: says it cannot compute instead of inventing a value (tool questions)", *wilson(sum(bool(x) for x in ab), len(ab)), n=len(ab)))
        headline = next(m for m in metrics if m.name.startswith("Judge: correct")) if judged else metrics[0]
        models = {}
        for r in recs:
            models[r["output"]["answer_model"]] = models.get(r["output"]["answer_model"], 0) + 1
        per_cat = {}
        for r in recs:
            per_cat.setdefault(r["case"].get("category", "notes_task"), []).append(r["scores"])
        rows = [{"category": c, "n": len(v), "format_ok": float(np.mean([s["format_ok"] for s in v])),
                 "citations_valid": float(np.mean([s["citations_valid"] for s in v if s["citations_valid"] is not None] or [np.nan])),
                 "judge_correct": float(np.mean([s["judge_correct"] >= 1 for s in v if s.get("judge_correct") is not None])) if any(s.get("judge_correct") is not None for s in v) else None}
                for c, v in sorted(per_cat.items())]
        invented = [{"question": r["case"]["question"], "answer": r["output"]["answer"][:400]} for r in recs if r["scores"].get("states_number")]
        return Summary(headline, metrics, {"per_category": rows, "answer_models": [{"model": k, "n": v} for k, v in models.items()],
                                           "invented_numbers": invented})
