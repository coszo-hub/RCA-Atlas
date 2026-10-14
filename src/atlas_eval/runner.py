"""Run suites, record every case with provenance, and re-score saved runs."""

from __future__ import annotations

import json
import platform
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .suites import SUITES
from .suites.base import DATASETS, write_jsonl

ROOT = Path(__file__).resolve().parents[2]


def git_state() -> dict:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": run("rev-parse", "HEAD"), "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(run("status", "--porcelain"))}


def environment() -> dict:
    """What the run executed on: interpreter, libraries, and the external CLIs the suites call."""
    import importlib.metadata as md
    import shutil

    def version(cmd: list[str]) -> str | None:
        if not shutil.which(cmd[0]):
            return None
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else None

    packages = {}
    for name in ("numpy", "scipy", "matplotlib"):
        try:
            packages[name] = md.version(name)
        except md.PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "packages": packages, "node": version(["node", "--version"]), "claude_cli": version(["claude", "--version"])}


def build_datasets(names: list[str] | None = None) -> dict[str, int]:
    written = {}
    for name, suite in SUITES.items():
        if names and name not in names:
            continue
        cases = suite.build_cases()
        if cases:
            write_jsonl(DATASETS / suite.dataset, cases)
            written[name] = len(cases)
    return written


def run_suite(name: str, ctx: dict, out: Path, limit: int | None = None, log=print) -> list[dict]:
    suite = SUITES[name]
    cases = suite.cases()[:limit] if limit else suite.cases()
    records = []
    started = time.perf_counter()
    if hasattr(suite, "run_all"):
        outputs = suite.run_all(cases)
        for case, output in zip(cases, outputs):
            records.append({"suite": name, "case_id": case["id"], "case": case, "output": output,
                            "scores": suite.score_case(case, output)})
    else:
        for i, case in enumerate(cases, 1):
            t0 = time.perf_counter()
            rec = {"suite": name, "case_id": case["id"], "case": case}
            try:
                output = suite.run_case(case, ctx)
                rec["output"] = output
                if output.get("error"):
                    rec["error"] = output["error"]
                else:
                    rec["scores"] = suite.score_case(case, output)
            except Exception as exc:
                rec["error"] = f"{type(exc).__name__}: {exc}"
                rec["traceback"] = traceback.format_exc(limit=4)
            rec["wall_ms"] = (time.perf_counter() - t0) * 1000
            records.append(rec)
            if i % 10 == 0 or i == len(cases):
                log(f"  {name}: {i}/{len(cases)} ({sum('error' in r for r in records)} errors)")
    write_jsonl(out / f"{name}.jsonl", records)
    log(f"{name}: {len(records)} cases in {time.perf_counter() - started:.0f} s")
    return records


def run(names: list[str], out: Path, ctx: dict, limit: int | None = None, log=print) -> Path:
    """Run suites into `out`. Each suite writes its own provenance file, so separate
    processes (offline and live suites, say) can fill one run directory concurrently."""
    out.mkdir(parents=True, exist_ok=True)
    header = out / "run.json"
    if not header.exists():
        header.write_text(json.dumps({"run_id": out.name, "created_utc": datetime.now(timezone.utc).isoformat(),
                                      "git": git_state(), "python": platform.python_version(),
                                      "environment": environment()}, indent=2) + "\n")
    env = environment()
    for name in names:
        suite = SUITES[name]
        records = run_suite(name, ctx, out, limit, log)
        prov = {"suite": name, "title": suite.title, "dataset": suite.dataset, "dataset_sha256": suite.dataset_sha256(),
                "n_cases": len(records), "n_errors": sum("error" in r for r in records),
                "ran_utc": datetime.now(timezone.utc).isoformat(), "git": git_state(), "context": ctx,
                "environment": env}
        (out / "provenance").mkdir(exist_ok=True)
        (out / "provenance" / f"{name}.json").write_text(json.dumps(prov, indent=2) + "\n")
    return out


def load_records(out: Path, name: str) -> list[dict]:
    path = out / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def rescore(out: Path, name: str) -> list[dict]:
    """Recompute scores from saved outputs (after a scoring change or a judge pass), without re-running."""
    suite = SUITES[name]
    records = load_records(out, name)
    for r in records:
        if not r.get("error") and "output" in r:
            r["scores"] = suite.score_case(r["case"], r["output"])
    write_jsonl(out / f"{name}.jsonl", records)
    return records


def retry_errors(out: Path, name: str, ctx: dict, log=print) -> list[dict]:
    """Re-run only the cases that errored, keeping the first failure on the record.

    First-attempt availability stays measurable (`first_error`), while quality
    metrics use the retried answer.
    """
    suite = SUITES[name]
    records = load_records(out, name)
    todo = [r for r in records if r.get("error")]
    for i, rec in enumerate(todo, 1):
        first = rec.pop("error")
        rec.pop("traceback", None)
        rec.setdefault("first_error", first)
        rec["attempts"] = rec.get("attempts", 1) + 1
        try:
            output = suite.run_case(rec["case"], ctx)
            rec["output"] = output
            if output.get("error"):
                rec["error"] = output["error"]
            else:
                rec["scores"] = suite.score_case(rec["case"], output)
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
        log(f"  retry {i}/{len(todo)} {rec['case_id']}: {rec.get('error', 'ok')}")
    write_jsonl(out / f"{name}.jsonl", records)
    return records
