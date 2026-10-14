"""LLM-as-judge for Ask Atlas answers, plus a sheet for checking the judge against people.

The judge sees the question, the reference answer (when the gold set has one),
the evidence excerpts the Worker retrieved, and the answer. It returns a fixed
JSON rubric. Judge scores are only trusted after agreement with human labels
on a sample is measured (Cohen's κ; see EVALUATION_METHOD.md §6).
"""

from __future__ import annotations

import csv
import json
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .runner import load_records, rescore
from .suites.agent import last_json_answer

RUBRIC = """You are grading an answer from RCA Atlas, a research assistant for the OOI Regional Cabled Array.

Question: {question}

Reference answer (written by the maintainers; may be absent): {reference}

Evidence the system retrieved (titles and excerpts):
{evidence}

System answer:
{answer}

Grade strictly and return only JSON:
{{"correct": 0 | 1 | 2 | null,   // vs the reference: 2 = all key facts right, 1 = partly right or incomplete, 0 = wrong or misses the point; null if there is no reference
  "supported": true | false,     // every factual claim in the answer is backed by the evidence excerpts above
  "abstained_properly": true | false | null,  // only for questions that need a live computation or tool result the system did not run: true if it says so instead of giving a made-up value; else null
  "reason": "<one sentence>"}}"""


def judge_prompt(record: dict) -> str:
    case, out = record["case"], record["output"]
    evidence = "\n".join(f"- {h.get('title')}: {h.get('excerpt')}" for h in out.get("hits", [])) or "(none)"
    return RUBRIC.format(question=case["question"], reference=case.get("gold", {}).get("reference_answer") or "(none)",
                         evidence=evidence, answer=out["answer"])


def claude_judge(prompt: str, model: str = "haiku") -> dict:
    proc = subprocess.run(["claude", "-p", prompt, "--model", model, "--output-format", "json", "--max-turns", "1",
                           "--strict-mcp-config", "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task"],
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    envelope = json.loads(proc.stdout)
    text = envelope.get("result", "")
    start, end = text.find("{"), text.rfind("}")
    verdict = json.loads(text[start:end + 1]) if start >= 0 else {}
    verdict["_cost_usd"] = envelope.get("total_cost_usd")
    return verdict


def judge_run(out: Path, model: str = "haiku", workers: int = 4, log=print) -> None:
    records = load_records(out, "answers")
    todo = [r for r in records if not r.get("error") and "judge" not in r["output"]]

    def one(r):
        try:
            v = claude_judge(judge_prompt(r), model)
            r["output"]["judge"] = {k: v.get(k) for k in ("correct", "supported", "abstained_properly", "reason")}
            r["output"]["judge"]["model"] = f"claude:{model}"
            r["output"]["judge"]["cost_usd"] = v.get("_cost_usd")
        except Exception as exc:
            r["output"]["judge_error"] = str(exc)[:300]
    with ThreadPoolExecutor(workers) as pool:
        for i, _ in enumerate(pool.map(one, todo), 1):
            if i % 10 == 0:
                log(f"  judged {i}/{len(todo)}")
    from .suites.base import write_jsonl
    write_jsonl(out / "answers.jsonl", records)
    rescore(out, "answers")
    write_calibration_sheet(out, records)


def write_calibration_sheet(out: Path, records: list[dict], n: int = 20, seed: int = 7) -> Path:
    """A blind sample for two people to grade with the same rubric; agreement with the judge gives κ."""
    judged = [r for r in records if r.get("output", {}).get("judge")]
    sample = random.Random(seed).sample(judged, min(n, len(judged)))
    path = out / "judge_calibration_sheet.csv"
    with path.open("w", newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["case_id", "question", "reference_answer", "answer", "human_correct_0_1_2", "human_supported_true_false"])
        for r in sample:
            w.writerow([r["case_id"], r["case"]["question"], r["case"].get("gold", {}).get("reference_answer", ""),
                        r["output"]["answer"], "", ""])
    return path


def cohen_kappa(a: list, b: list) -> float:
    labels = sorted(set(a) | set(b), key=str)
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


__all__ = ["judge_run", "cohen_kappa", "last_json_answer"]
