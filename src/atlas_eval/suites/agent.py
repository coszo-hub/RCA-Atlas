"""Agentic sandbox tasks: a natural-language request, files in a sandbox, a numeric answer.

The agent sees only the task text and the `atlas_tasks` MCP tools. It must
choose the tool, pass the right arguments, and report the result as a final
JSON object `{"answer": ...}`. Two adapters run the same tasks:

- `oracle`: a scripted agent that calls the intended tool directly. Its score
  is the tool ceiling (and checks the harness itself).
- `claude`: Claude Code in headless mode (`claude -p`) with only the sandbox
  MCP server enabled, recording every tool call.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from atlas_tasks.tools import Sandbox, dispatch

from .. import plotstyle as ps
from .. import synth
from ..stats import bootstrap, wilson
from .base import Metric, Suite, Summary, ok_records
from .offline import FIXTURES
from .scientific import TimingSuite

ROOT = Path(__file__).resolve().parents[3]
MCP_SERVER = ROOT / "src" / "atlas_tasks" / "mcp_server.py"
ANSWER_RULE = 'Finish with one line containing only a JSON object of the form {"answer": ...}.'


def last_json_answer(text: str):
    for m in reversed(list(re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text or ""))):
        try:
            obj = json.loads(m[0])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "answer" in obj:
            return obj["answer"]
    return None


class AgentSuite(Suite):
    name = "agent"
    title = "Agentic sandbox tasks (scripted oracle)"
    capability = "Carry out the notes' correction tasks end to end from a plain request"
    axis = "task success"
    dataset = "agent_tasks_v1.jsonl"
    description = ("21 requests over files the agent has not seen: diagnose faults, find a clock jump, measure dv/v, "
                   "calibrate an A-0-A record, estimate a drift, count earthquakes with a magnitude filter, find the "
                   "busiest day. A task succeeds when the final answer is within the task's tolerance; tool choice "
                   "is checked against the intended tool.")

    def build_cases(self) -> list[dict]:
        cases = []
        for i in range(3):
            faults = [[{"kind": "gap", "start": 600, "length": 40}, {"kind": "spike", "start": 1500, "size": 20.0}],
                      [{"kind": "duplicate", "start": 900, "length": 3}, {"kind": "zero_fill", "start": 2200, "length": 80}],
                      [{"kind": "backstep", "start": 1200, "size_s": 3.0}, {"kind": "flatline", "start": 2600, "length": 120}]][i]
            cases.append({"id": f"agent-diagnose-{i + 1}", "type": "diagnose", "file": f"series_{i + 1}.npz", "tool": "atlas_diagnose_series",
                          "spec": {"n": 4000, "period_s": 1.0, "seed": 6000 + i, "faults": faults},
                          "prompt": f"The file series_{i + 1}.npz holds a time series (t_s, x). What kinds of faults does it contain? "
                                    "Use the fault kind names the tools report. " + ANSWER_RULE + " The answer is a list of kind names."})
        for i, (jump, hour) in enumerate([(3.0, 30), (-2.5, 40), (0.0, 0)]):
            kind = "jump" if jump else "none"
            cases.append({"id": f"agent-clock-{i + 1}", "type": "clock", "file": f"pair_{i + 1}.npz", "tool": "atlas_clock_track",
                          "spec": {"kind": kind, "snr": 0.25, "seed": 6100 + i, "days": 3, "fs": 8.0, "travel_s": 4.0,
                                   "jump_s": jump, "drift_s_per_day": 0.0, "jump_hour": hour or 30, "gap_hours": []},
                          "prompt": f"pair_{i + 1}.npz has two stations' 8 Hz records (a, b, fs). Did station B's clock jump? "
                                    "If so give the jump size in seconds (Δt after minus before) and the hour index where it happened. "
                                    + ANSWER_RULE + ' Use {"answer": {"jump_s": <number>, "hour": <int>}} or {"answer": "none"}.'})
        for i, (dvv, method) in enumerate([(0.002, "stretching"), (-0.005, "mwcs"), (0.001, "dtw")]):
            cases.append({"id": f"agent-dvv-{i + 1}", "type": "dvv", "file": f"ccf_{i + 1}.npz", "tool": "atlas_dvv",
                          "spec": {"dvv": dvv, "snr": 10, "seed": 6200 + i, "fs": 10.0, "maxlag_s": 60.0}, "method": method,
                          "prompt": f"ccf_{i + 1}.npz has a reference CCF (ref), a current CCF (cur), and lags_s. Measure dv/v with "
                                    f"{method.upper() if method != 'stretching' else 'the stretching method'} in the 10–50 s coda. "
                                    + ANSWER_RULE + " The answer is dv/v in percent."})
        for i, rate in enumerate([2.5, -1.5, 4.0]):
            cases.append({"id": f"agent-a0a-{i + 1}", "type": "rate", "file": f"a0a_{i + 1}.npz", "tool": "atlas_pressure_calibrate",
                          "spec": {"task": "a0a", "rate_kpa_per_yr": rate, "seed": 6300 + i, "days": 180, "dt_s": 30.0,
                                   "noise_kpa": 0.01, "exp_amp_kpa": 0.0, "cal_every_days": 14.0, "cal_reference_kpa": 101.325},
                          "prompt": f"a0a_{i + 1}.npz is a bottom-pressure record (t_s, p_kpa) from a gauge that runs A-0-A "
                                    "calibrations against its internal barometer (101.325 kPa). What is the sensor drift rate? "
                                    + ANSWER_RULE + " The answer is in kPa per year."})
        for i, rate in enumerate([-2.0, 3.2, 0.8]):
            cases.append({"id": f"agent-drift-{i + 1}", "type": "rate", "file": f"prest_{i + 1}.npz", "tool": "atlas_pressure_drift",
                          "spec": {"task": "drift", "rate_kpa_per_yr": rate, "seed": 6400 + i, "days": 120, "dt_s": 60.0,
                                   "noise_kpa": 0.01, "exp_amp_kpa": 0.0},
                          "prompt": f"prest_{i + 1}.npz is a record (t_s, p_kpa) from a pressure gauge that does not self-calibrate. "
                                    "Calculate its linear drift. " + ANSWER_RULE + " The answer is in kPa per year."})
        for i, (start, end, mmin) in enumerate([("2026-09-23", "2026-09-24", 0.5), ("2026-09-24", "2026-09-24", 1.0), ("2026-09-23", "2026-09-25", None)]):
            filt = f" with magnitude of at least {mmin}" if mmin is not None else ""
            cases.append({"id": f"agent-quakes-{i + 1}", "type": "count", "tool": "atlas_quake_histogram",
                          "spec": {"start": start, "end": end, "min_mag": mmin},
                          "prompt": f"How many Axial Seamount earthquakes were there from {start} to {end} (UTC){filt}? "
                                    + ANSWER_RULE + " The answer is an integer."})
        for i, (start, end) in enumerate([("2026-09-23", "2026-09-25"), ("2026-09-22", "2026-09-24"), ("2026-09-23", "2026-09-23")]):
            cases.append({"id": f"agent-busiest-{i + 1}", "type": "busiest", "tool": "atlas_quake_histogram",
                          "spec": {"start": start, "end": end},
                          "prompt": f"Make a daily histogram of Axial earthquakes from {start} to {end}. Which UTC day had the most, "
                                    "and how many? " + ANSWER_RULE + ' Use {"answer": {"day": "YYYY-MM-DD", "count": <int>}}.'})
        return cases

    # ------------------------------------------------------------------ data
    def materialize(self, case: dict, root: Path) -> None:
        spec = case["spec"]
        if case["type"] == "diagnose":
            s = synth.faulty_series(**spec)
            np.savez(root / case["file"], t_s=s["t_s"], x=s["x"])
        elif case["type"] == "clock":
            truth = TimingSuite.truth(spec)
            a, b = synth.station_pair(days=spec["days"], fs=spec["fs"], travel_s=spec["travel_s"], snr=spec["snr"],
                                      clock_dt_hourly=truth, seed=spec["seed"])
            np.savez(root / case["file"], a=a, b=b, fs=spec["fs"])
        elif case["type"] == "dvv":
            lags, ref = synth.synthetic_ccf(fs=spec["fs"], maxlag_s=spec["maxlag_s"], seed=spec["seed"])
            cur = synth.noisy(synth.stretch_ccf(lags, ref, spec["dvv"]), spec["snr"], np.random.default_rng(spec["seed"] + 1))
            np.savez(root / case["file"], lags_s=lags, ref=ref, cur=cur)
        elif case["type"] == "rate":
            kw = {k: spec[k] for k in ("rate_kpa_per_yr", "seed", "days", "dt_s", "noise_kpa", "exp_amp_kpa")}
            if spec["task"] == "a0a":
                kw.update(calibration="a0a", cal_every_days=spec["cal_every_days"], cal_reference_kpa=spec["cal_reference_kpa"])
            r = synth.pressure_record(**kw)
            np.savez(root / case["file"], t_s=r["t_s"], p_kpa=r["reading_kpa"])

    def expected(self, case: dict):
        spec = case["spec"]
        if case["type"] == "diagnose":
            return sorted({f["kind"] for f in spec["faults"]})
        if case["type"] == "clock":
            return "none" if spec["kind"] == "none" else {"jump_s": -spec["jump_s"], "hour": spec["jump_hour"]}
        if case["type"] == "dvv":
            return spec["dvv"] * 100
        if case["type"] == "rate":
            return spec["rate_kpa_per_yr"]
        from .offline import oracle_rows
        per_day = {}
        for p in FIXTURES.glob("hypo71_*.dat"):
            stamp = p.stem.split("_")[1]
            day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
            if spec["start"] <= day <= spec["end"]:
                rows = oracle_rows(p.read_text(), stamp)
                per_day[day] = sum(1 for r in rows if spec.get("min_mag") is None or float(r[8]) >= spec["min_mag"])
        if case["type"] == "count":
            return sum(per_day.values())
        day = max(sorted(per_day), key=lambda d: per_day[d])
        return {"day": day, "count": per_day[day]}

    # ---------------------------------------------------------------- adapters
    def oracle(self, case: dict, sb: Sandbox) -> tuple[object, list[str]]:
        t = case["type"]
        if t == "diagnose":
            r = dispatch(sb, "atlas_diagnose_series", {"path": case["file"]})
            return sorted({f["kind"] for f in r["findings"]}), ["atlas_diagnose_series"]
        if t == "clock":
            r = dispatch(sb, "atlas_clock_track", {"path": case["file"], "output": "track.npz"})
            jumps = r["diagnosis"]["jumps"]
            return ({"jump_s": jumps[0]["size_s"], "hour": int(jumps[0]["time_s"] // 3600)} if jumps else "none"), ["atlas_clock_track"]
        if t == "dvv":
            r = dispatch(sb, "atlas_dvv", {"path": case["file"], "method": case["method"]})
            return r["results"][0]["dvv_percent"], ["atlas_dvv"]
        if t == "rate":
            if case["tool"] == "atlas_pressure_calibrate":
                r = dispatch(sb, "atlas_pressure_calibrate", {"path": case["file"], "kind": "a0a"})
                return r["drift_model"]["rate_kpa_per_yr"], [case["tool"]]
            r = dispatch(sb, "atlas_pressure_drift", {"path": case["file"]})
            return r["estimate"]["rate_kpa_per_yr"], [case["tool"]]
        spec = case["spec"]
        args = {"start": spec["start"], "end": spec["end"]}
        if spec.get("min_mag") is not None:
            args["min_magnitude"] = spec["min_mag"]
        r = dispatch(sb, "atlas_quake_histogram", args)
        if t == "count":
            return r["count"], ["atlas_quake_histogram"]
        return {"day": r["busiest_day"]["day"], "count": r["busiest_day"]["count"]}, ["atlas_quake_histogram"]

    def claude(self, case: dict, root: Path, ctx: dict) -> tuple[object, list[str], dict]:
        config = {"mcpServers": {"atlas": {"command": str(ROOT / ".venv" / "bin" / "python"), "args": [str(MCP_SERVER)],
                                           "env": {"ATLAS_SANDBOX_DIR": str(root), "ATLAS_QUAKE_CACHE": str(root / "quake_cache"),
                                                   "ATLAS_QUAKE_OFFLINE": "1"}}}}
        (root / "mcp.json").write_text(json.dumps(config))
        system = ("You are the RCA Atlas data agent. Work only through the atlas MCP tools; files named in the request are in "
                  "the tool sandbox. Do not ask questions; finish the task.")
        cmd = ["claude", "-p", case["prompt"], "--model", ctx.get("agent_model", "haiku"), "--mcp-config", str(root / "mcp.json"),
               "--strict-mcp-config", "--allowedTools", "mcp__atlas__*", "--disallowedTools",
               "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit",
               "--append-system-prompt", system, "--output-format", "stream-json", "--verbose", "--max-turns", "12"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=root, stdin=subprocess.DEVNULL)
        tools, final, usage = [], "", {}
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    # Only atlas tools count; ToolSearch is Claude Code loading deferred tool schemas.
                    if block.get("type") == "tool_use" and block["name"].startswith("mcp__atlas__"):
                        tools.append(block["name"].removeprefix("mcp__atlas__"))
            if ev.get("type") == "result":
                final = ev.get("result", "")
                usage = {"cost_usd": ev.get("total_cost_usd"), "turns": ev.get("num_turns"), "duration_ms": ev.get("duration_ms")}
        if final.startswith("API Error"):          # infrastructure, not the agent: record as an error and retry
            raise RuntimeError(final[:200])
        if not final and proc.returncode:
            raise RuntimeError(proc.stderr.strip()[-400:] or "claude exited without a result")
        return last_json_answer(final), tools, {**usage, "final_text": final[-600:]}

    def run_case(self, case, ctx):
        adapter = ctx.get("agent", "oracle")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "quake_cache"
            cache.mkdir()
            for p in FIXTURES.glob("hypo71_*.dat"):
                shutil.copy(p, cache / p.name)
            self.materialize(case, root)
            t0 = time.perf_counter()
            if adapter == "oracle":
                from atlas_tasks.earthquakes import directory_loader
                sb = Sandbox(root, quake_loader=directory_loader(cache))
                answer, tools = self.oracle(case, sb)
                extra = {}
            else:
                answer, tools, extra = self.claude(case, root, ctx)
            return {"adapter": adapter if adapter == "oracle" else f"claude:{ctx.get('agent_model', 'haiku')}",
                    "answer": answer, "tools": tools, "latency_ms": (time.perf_counter() - t0) * 1000,
                    "expected": self.expected(case), **extra}

    def score_case(self, case, output):
        exp, got = output["expected"], output["answer"]
        ok = False
        try:
            if case["type"] == "diagnose":
                ok = sorted(set(got)) == exp
            elif case["type"] == "clock":
                ok = (got == "none" and exp == "none") or (isinstance(got, dict) and isinstance(exp, dict)
                                                           and abs(float(got["jump_s"]) - exp["jump_s"]) <= 0.25 and abs(int(got["hour"]) - exp["hour"]) <= 2)
            elif case["type"] == "dvv":
                ok = abs(float(got) - exp) <= 0.01 + 0.1 * abs(exp)
            elif case["type"] == "rate":
                ok = abs(float(got) - exp) <= 0.1
            elif case["type"] == "count":
                ok = int(got) == exp
            elif case["type"] == "busiest":
                ok = got["day"] == exp["day"] and int(got["count"]) == exp["count"]
        except (TypeError, ValueError, KeyError):
            ok = False
        return {"success": ok, "answered": got is not None, "right_tool": case["tool"] in output["tools"],
                "first_tool_right": bool(output["tools"]) and output["tools"][0] == case["tool"], "n_tool_calls": len(output["tools"])}

    def summarize(self, records):
        recs = ok_records(records)
        sc = [r["scores"] for r in recs]
        adapter = recs[0]["output"]["adapter"] if recs else "n/a"
        metrics = [Metric(f"Task success ({adapter})", *wilson(sum(s["success"] for s in sc), len(records)), n=len(records), target=0.9,
                          note="errors count as failures"),
                   Metric("Intended tool called", *wilson(sum(s["right_tool"] for s in sc), len(sc)), n=len(sc)),
                   Metric("Intended tool called first", *wilson(sum(s["first_tool_right"] for s in sc), len(sc)), n=len(sc)),
                   Metric("Final answer in the required JSON form", *wilson(sum(s["answered"] for s in sc), len(sc)), n=len(sc)),
                   Metric("Tool calls per task", *bootstrap([s["n_tool_calls"] for s in sc]), n=len(sc), unit="calls", higher_is_better=False)]
        costs = [r["output"].get("cost_usd") for r in recs if r["output"].get("cost_usd") is not None]
        if costs:
            metrics.append(Metric("Cost per task", *bootstrap(costs), n=len(costs), unit="USD", higher_is_better=False))
        by_type = {}
        for r in records:
            by_type.setdefault(r["case"]["type"], []).append(bool(r.get("scores", {}).get("success")))
        rows = [{"type": k, "n": len(v), "success": sum(v) / len(v)} for k, v in by_type.items()]
        failures = [{"id": r["case"]["id"], "expected": r["output"]["expected"], "answer": r["output"]["answer"], "tools": r["output"]["tools"]}
                    for r in recs if not r["scores"]["success"]]
        return Summary(metrics[0], metrics, {"by_type": rows, "failures": failures})


class AgentLLMSuite(AgentSuite):
    """The same tasks driven by a language-model agent (Claude Code headless) instead of the script."""
    name = "agent_llm"
    title = "Agentic sandbox tasks (LLM agent)"
    requires = "live"

    def run_case(self, case, ctx):
        return super().run_case(case, {**ctx, "agent": ctx.get("agent") if ctx.get("agent") not in (None, "oracle") else "claude"})
