"""A single self-contained HTML catalog of one evaluation run.

`python -m atlas_eval site results/<run>` writes `results/<run>/catalog.html`:
every suite (method, metrics with intervals, figures, notes, tables), every
case (input, expected truth, the system's output, scores, errors) in one
filterable browser, and the environment the run executed in (commit,
interpreter, libraries, CLIs, endpoints, models, dataset hashes, and the
agent's sandbox tools). Figures and data are embedded, so the file can be
opened offline, attached, or hosted as-is.
"""

from __future__ import annotations

import base64
import html
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .report import fmt_metric, scorecard_figure, status
from .runner import ROOT, environment, load_records
from .suites import SUITES
from .suites.base import to_jsonable

MAX_LIST = 150
MAX_STR = 8000


# ------------------------------------------------------------------ case views

def _fmt(v: Any, digits: int = 3) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}g}" if math.isfinite(v) else "–"
    return str(v)


def _ok(v: Any) -> str | None:
    return None if v is None else ("pass" if v else "fail")


def _answers_status(r: dict) -> str | None:
    judge = r.get("output", {}).get("judge") or {}
    if judge.get("correct") is not None:
        return "pass" if judge["correct"] >= 1 else "fail"
    if judge.get("abstained_properly") is not None:
        return _ok(judge["abstained_properly"])
    return None


VIEWS: dict[str, Callable[[dict], tuple[str, str | None, str]]] = {
    # suite: record -> (what the case asks, status, one-line result)
    "routing": lambda r: (r["case"]["question"], _ok(r["scores"]["router_correct"]),
                          f"gold {r['case']['task']} · router {r['output']['router']} · Worker {r['output']['worker']}"),
    "quake_questions": lambda r: (r["case"]["question"], _ok(r["scores"]["parser_correct"]),
                                  "expected " + json.dumps(r["case"]["expected"]) + " · Worker "
                                  + ("✓" if r["scores"]["worker_correct"] else "✗")),
    "retrieval": lambda r: (r["case"]["question"],
                            _ok(r["scores"].get("hit_at_10")) if r["scores"].get("has_gold") else _ok(r["scores"].get("collection_hit")),
                            f"MRR {_fmt(r['scores'].get('mrr'))} · recall@10 {_fmt(r['scores'].get('recall_at_10'))}"
                            f" · {r['output'].get('latency_ms', 0) / 1000:.1f} s"),
    "answers": lambda r: (r["case"]["question"], _answers_status(r),
                          f"{r['output'].get('answer_model')} · judge {_fmt((r['output'].get('judge') or {}).get('correct'))}/2"
                          f" · {r['output'].get('latency_ms', 0) / 1000:.1f} s"),
    "quakes": lambda r: (f"{r['case']['source']} {r['case']['start']} → {r['case']['end']} by {r['case']['by']}"
                         + (f" · filter {json.dumps(r['case']['filter'])}" if r["case"].get("filter") else "")
                         + (f" · edge rows: {r['case']['edge']}" if r["case"].get("edge") else ""),
                         _ok(r["scores"]["count_correct"] and r["scores"]["histogram_correct"]),
                         f"count {r['output']['count']} (truth {r['scores']['truth_count']})"),
    "gaps": lambda r: (f"{len(r['case']['faults'])} injected fault(s): "
                       + (", ".join(f["kind"] for f in r["case"]["faults"]) or "none")
                       + f" · period {r['case']['period_s']} s · n {r['case']['n']}",
                       _ok(r["scores"]["exact"]),
                       "found: " + (", ".join(sorted({f["kind"] for f in r["output"]["findings"]})) or "nothing")),
    "timing": lambda r: (f"{r['case']['kind']} · SNR {r['case']['snr']}"
                         + (f" · jump {r['case']['jump_s']} s at h{r['case']['jump_hour']}" if r["case"]["jump_s"] else "")
                         + (f" · drift {r['case']['drift_s_per_day']} s/day" if r["case"]["drift_s_per_day"] else ""),
                         _ok(r["scores"]["pass"]),
                         f"diagnosed {r['scores']['predicted_kind']} · {r['scores']['bin_h']:g} h stacks · "
                         f"{r['scores']['n_covered']}/{r['scores']['n_hours']} hours estimated"),
    "dvv": lambda r: (f"dv/v {r['case']['dvv'] * 100:+.2f} % · SNR {r['case']['snr']}", _ok(r["scores"]["stretching"]["pass"]),
                      " · ".join(f"{m} {_fmt((r['output'][m]['dvv'] or 0) * 100)} % {'✓' if r['scores'][m]['pass'] else '✗'}"
                                 for m in ("stretching", "mwcs", "dtw"))),
    "pressure": lambda r: (f"{r['case']['task']} · {r['case']['days']} d · drift {r['case']['rate_kpa_per_yr']} kPa/yr"
                           + (f" · settling {r['case']['exp_amp_kpa']} kPa" if r["case"].get("exp_amp_kpa") else "")
                           + (f" · uplift {r['case']['uplift_kpa_per_yr']} kPa/yr" if r["case"].get("uplift_kpa_per_yr") else ""),
                           _ok(r["scores"]["pass"]),
                           (f"rate error {_fmt(r['scores'].get('rate_err'))} kPa/yr" if r["case"]["task"] == "drift"
                            else f"residual {_fmt(r['scores'].get('residual_rms_kpa'))} kPa RMS")),
    "agent": lambda r: (r["case"]["prompt"], _ok(r["scores"]["success"]),
                        f"tools {', '.join(r['output']['tools']) or 'none'} · answer {json.dumps(r['output']['answer'])[:80]}"),
}
VIEWS["agent_llm"] = VIEWS["agent"]


def case_row(suite: str, r: dict) -> dict:
    if r.get("error"):
        label = r["case"].get("question") or r["case"].get("prompt") or r["case_id"]
        state, result = "error", str(r["error"])[:200]
    else:
        try:
            label, state, result = VIEWS[suite](r)
        except (KeyError, TypeError, ValueError) as exc:   # a view must never break the page
            label, state, result = r["case_id"], None, f"(no summary: {type(exc).__name__})"
    return {"suite": suite, "id": r["case_id"], "label": label, "status": state or "n/a", "result": result,
            "record": trim(to_jsonable({k: r.get(k) for k in ("case", "output", "scores", "error", "first_error",
                                                               "attempts", "wall_ms") if k in r}))}


def trim(value: Any) -> Any:
    """Keep the catalog small: long arrays and strings are cut, with a note of what was dropped."""
    if isinstance(value, dict):
        return {k: trim(v) for k, v in value.items()}
    if isinstance(value, list):
        out = [trim(v) for v in value[:MAX_LIST]]
        if len(value) > MAX_LIST:
            out.append(f"… {len(value) - MAX_LIST} more items in the run's JSONL")
        return out
    if isinstance(value, str) and len(value) > MAX_STR:
        return value[:MAX_STR] + f"… ({len(value) - MAX_STR} more characters)"
    return value


# ------------------------------------------------------------------ html pieces

def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def prose(text: str) -> str:
    """Escape, then render `code` spans."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(text))


def img(path: Path, alt: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<figure><img alt="{esc(alt)}" src="data:image/png;base64,{data}"><figcaption>{esc(alt)}</figcaption></figure>'


def table(rows: list[dict], limit: int = 60) -> str:
    if not rows:
        return "<p class=muted>none</p>"
    cols = list(rows[0])

    def cell(v):
        if isinstance(v, float):
            return "–" if not math.isfinite(v) else (f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}")
        if isinstance(v, (list, dict)):
            return esc(json.dumps(v)[:120])
        return esc(v)
    head = "".join(f"<th>{esc(c.replace('_', ' '))}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td>{cell(r.get(c))}</td>" for c in cols) + "</tr>" for r in rows[:limit])
    more = f"<p class=muted>{len(rows) - limit} more rows in summary.json</p>" if len(rows) > limit else ""
    return f"<div class=scroll><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}"


def status_chip(text: str) -> str:
    kind = "good" if text.startswith("meets") else "bad" if text else "none"
    clean = text.replace("**", "")
    return f'<span class="chip {kind}">{esc(clean)}</span>' if clean else ""


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def repo_url() -> str | None:
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    m = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+/[^/.]+)", url)
    return f"https://github.com/{m[1]}" if m else None


# ------------------------------------------------------------------ build

def build_site(run_dir: Path, out: Path | None = None) -> Path:
    run_dir = Path(run_dir)
    figdir = run_dir / "figures"
    header = json.loads((run_dir / "run.json").read_text()) if (run_dir / "run.json").exists() else {}
    head = git_head()
    repo = repo_url()
    src_link = (lambda rel: f"{repo}/blob/{head}/{rel}") if repo else (lambda rel: None)

    nav, sections, cases, card, prov_rows, envs = [], [], [], [], [], []
    for name, suite in SUITES.items():
        records = load_records(run_dir, name)
        if not records:
            continue
        prov_path = run_dir / "provenance" / f"{name}.json"
        prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
        summary = suite.summarize(records)
        figures = suite.figures(records, figdir)
        errors = sum(1 for r in records if r.get("error"))
        card.append((suite.title, summary.headline, errors, name, suite.axis))
        rows = [case_row(name, r) for r in records]
        cases += rows
        counts = {s: sum(1 for c in rows if c["status"] == s) for s in ("pass", "fail", "error", "n/a")}
        dataset_rel = str((Path("src/atlas_eval/datasets") / suite.dataset)).replace("atlas_eval/datasets/../../", "")
        link = src_link(dataset_rel)
        ctx = prov.get("context", {})
        prov_rows.append({"suite": name, "dataset": suite.dataset, "sha256": prov.get("dataset_sha256", "")[:16],
                          "cases": len(records), "errors": errors, "ran (UTC)": prov.get("ran_utc", "")[:19],
                          "commit": (prov.get("git", {}).get("commit") or "")[:10] + (" +local" if prov.get("git", {}).get("dirty") else ""),
                          "needs": suite.requires,
                          "context": ", ".join(f"{k}={v}" for k, v in ctx.items() if v not in (None, "") and
                                               (suite.requires == "live" or k not in ("endpoint", "model", "pace_s")))})
        if prov.get("environment"):
            envs.append(prov["environment"])
        metrics = "".join(
            f"<tr><td>{esc(m.name)}{('<div class=note>' + esc(m.note) + '</div>') if m.note else ''}</td>"
            f"<td class=num>{esc(fmt_metric(m))}</td><td class=num>{m.n}</td><td>{status_chip(status(m))}</td></tr>"
            for m in summary.metrics)
        tables = "".join(f"<details><summary>{esc(t.replace('_', ' '))}</summary>{table(rows_)}</details>"
                         for t, rows_ in summary.tables.items() if t != "confusion")
        notes = "".join(f"<li>{prose(n)}</li>" for n in summary.notes)
        nav.append(f'<a href="#suite-{name}">{esc(suite.title)}</a>')
        sections.append(f"""
<section id="suite-{name}" class=suite>
  <h2>{esc(suite.title)}</h2>
  <p class=meta><span>{esc(suite.capability)}</span> · <span>axis: {esc(suite.axis)}</span> ·
    <span>{len(records)} cases</span> · <span>needs: {esc(suite.requires)}</span> ·
    {'<a href="' + esc(link) + '">' if link else ''}<code>{esc(suite.dataset)}</code>{'</a>' if link else ''}</p>
  <p>{prose(suite.description)}</p>
  <div class=counts>{''.join(f'<span class="chip {k.replace("/", "")}">{v} {k}</span>' for k, v in counts.items() if v)}
    <button class=browse data-suite="{name}">Browse these {len(records)} cases →</button></div>
  <table class=metrics><thead><tr><th>Metric</th><th>Value [95% CI]</th><th>n</th><th>Status</th></tr></thead><tbody>{metrics}</tbody></table>
  {''.join(img(f, f.stem.replace('_', ' ')) for f in figures)}
  {f'<ul class=notes>{notes}</ul>' if notes else ''}
  {tables}
</section>""")

    scorecard = scorecard_figure([(t, m, e) for t, m, e, _, _ in card], figdir / "scorecard.png")
    score_rows = "".join(
        f'<tr><td><a href="#suite-{n}">{esc(t)}</a></td><td>{esc(axis)}</td><td>{esc(m.name)}</td>'
        f'<td class=num>{esc(fmt_metric(m))}</td><td class=num>{m.n}</td><td>{status_chip(status(m, e))}</td></tr>'
        for t, m, e, n, axis in card)

    run_env = header.get("environment") or (envs[0] if envs else None)
    env_note = "" if run_env else " (not recorded by this run; shown as of catalog build)"
    run_env = run_env or environment()
    from atlas_tasks.router import load_rules
    from atlas_tasks.tools import TOOL_SCHEMAS
    tools_rows = [{"tool": t["name"], "what it does": t["description"],
                   "arguments": ", ".join(f"{k}{'*' if k in t['inputSchema'].get('required', []) else ''}"
                                          for k in t["inputSchema"]["properties"])} for t in TOOL_SCHEMAS]
    rules = load_rules()
    route_rows = [{"task": t["task"], "priority": t["priority"], "handler": t["handler"]["kind"],
                   "answer": t["handler"]["answer"], "tools": ", ".join(t["handler"]["tools"])} for t in rules["tasks"]]
    judge_models = sorted({(r["record"].get("output") or {}).get("judge", {}).get("model")
                           for r in cases if r["suite"] == "answers" and (r["record"].get("output") or {}).get("judge")} - {None})
    answer_models = sorted({(r["record"].get("output") or {}).get("answer_model") for r in cases
                            if r["suite"] == "answers" and r["record"].get("output")} - {None})
    agent_adapters = sorted({(r["record"].get("output") or {}).get("adapter") for r in cases
                             if r["suite"] in ("agent", "agent_llm") and r["record"].get("output")} - {None})
    git = header.get("git", {})
    env_kv = [("Run", header.get("run_id", run_dir.name)), ("Run created (UTC)", header.get("created_utc", "")[:19]),
              ("Run started on commit", f"{git.get('commit', '')[:10]} on {git.get('branch', '')}"
               + (" with uncommitted changes" if git.get("dirty") else "")),
              ("Catalog built from commit", head[:10]),
              ("Python", run_env.get("python")), ("Platform", run_env.get("platform")),
              ("Libraries", ", ".join(f"{k} {v}" for k, v in (run_env.get("packages") or {}).items())),
              ("Node (runs the Worker's own JS)", run_env.get("node")), ("Claude CLI (judge, LLM agent)", run_env.get("claude_cli")),
              ("Live endpoint", "https://rca-atlas.quakehunt.workers.dev (POST /v1/answer)"),
              ("Answer models seen", ", ".join(answer_models) or "–"), ("Judge model", ", ".join(judge_models) or "–"),
              ("Agent adapters", ", ".join(agent_adapters) or "–")]
    env_html = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v if v not in (None, '') else '–')}</td></tr>" for k, v in env_kv)
    reproduce = """cd src
../.venv/bin/python -m atlas_eval build                       # regenerate synthetic datasets (deterministic)
../.venv/bin/python -m atlas_eval run --suites offline --out atlas_eval/results/&lt;run&gt;
../.venv/bin/python -m atlas_eval run --suites retrieval answers --out atlas_eval/results/&lt;run&gt;
../.venv/bin/python -m atlas_eval judge atlas_eval/results/&lt;run&gt;
../.venv/bin/python -m atlas_eval run --suites agent_llm --agent-model haiku --out atlas_eval/results/&lt;run&gt;
../.venv/bin/python -m atlas_eval site atlas_eval/results/&lt;run&gt;"""
    method = src_link("src/atlas_eval/EVALUATION_METHOD.md")
    suites_meta = {name: SUITES[name].title for name in {c["suite"] for c in cases}}
    data = json.dumps({"cases": cases, "suites": suites_meta}, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c")       # no "<" at all inside the script element, so no text can close or nest it
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page = TEMPLATE.format(
        title=esc(f"RCA Atlas evaluation — {header.get('run_id', run_dir.name)}"),
        run=esc(header.get("run_id", run_dir.name)), built=esc(built), n_cases=len(cases), n_suites=len(card),
        method=(f'<a href="{esc(method)}">method write-up</a>' if method else "method write-up (src/atlas_eval/EVALUATION_METHOD.md)"),
        nav="".join(nav), score_rows=score_rows, scorecard=img(scorecard, "Capability scorecard: headline metric per suite"),
        sections="".join(sections), env_rows=env_html, env_note=esc(env_note), prov=table(prov_rows),
        tools=table(tools_rows), routes=table(route_rows), reproduce=reproduce, data=data, css=CSS, js=JS)
    out = Path(out) if out else run_dir / "catalog.html"
    out.write_text(page, encoding="utf-8")
    return out


# ------------------------------------------------------------------ page

CSS = r"""
:root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--axis:#c3c2b7;--accent:#2a78d6;--good:#0ca30c;--goodtext:#006300;--bad:#d03b3b;--warn:#b07800;--ring:rgba(11,11,11,.10);--code:#f0efec}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--accent:#3987e5;--good:#0ca30c;--goodtext:#0ca30c;--bad:#e66767;--warn:#fab219;
--ring:rgba(255,255,255,.10);--code:#262624}figure img{background:#fcfcfb}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);color:var(--ink)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code,pre{font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--code);border-radius:4px}
code{padding:1px 4px}pre{padding:10px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:6px 0}
body{overflow-x:hidden}
nav{position:fixed;left:0;top:0;bottom:0;width:240px;overflow:auto;padding:20px 14px;border-right:1px solid var(--grid);background:var(--surface)}
nav h1{font-size:15px;margin:0 0 4px}nav .sub{color:var(--muted);font-size:12px;margin-bottom:14px}
nav a{display:block;padding:4px 8px;border-radius:6px;color:var(--ink2);font-size:13px}nav a:hover{background:var(--code);text-decoration:none}
nav .group{margin:14px 8px 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
main{margin-left:240px;padding:28px 36px 80px;max-width:1420px;min-width:0}
section{scroll-margin-top:16px;min-width:0}
section{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:20px 24px;margin:0 0 20px}
h2{font-size:18px;margin:0 0 6px}h3{font-size:14px;margin:18px 0 6px}
.meta{color:var(--ink2);font-size:12.5px;margin:0 0 10px}.muted{color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12px}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.scroll{overflow:auto;max-height:420px}.note{color:var(--muted);font-size:12px}
.metrics{margin:10px 0 6px}
figure{margin:14px 0}figure img{max-width:100%;border:1px solid var(--ring);border-radius:8px}figcaption{color:var(--muted);font-size:12px}
details{margin:8px 0}summary{cursor:pointer;color:var(--ink2);font-size:13px}
.chip{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;border:1px solid var(--ring);margin-right:6px;white-space:nowrap}
.chip.good,.chip.pass{color:var(--goodtext)}.chip.good::before,.chip.pass::before{content:"✓ "}
.chip.bad,.chip.fail{color:var(--bad)}.chip.bad::before,.chip.fail::before{content:"✗ "}
.chip.error{color:var(--warn)}.chip.error::before{content:"! "}.chip.na{color:var(--muted)}
.counts{display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin:6px 0}
button{font:inherit;font-size:13px;padding:5px 12px;border-radius:7px;border:1px solid var(--ring);background:var(--surface);color:var(--accent);cursor:pointer}
button:hover{background:var(--code)}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0 12px;position:sticky;top:0;background:var(--surface);padding:8px 0;z-index:1}
.filters input,.filters select{font:inherit;font-size:13px;padding:6px 10px;border-radius:7px;border:1px solid var(--axis);background:var(--surface);color:var(--ink)}
.filters input{flex:1;min-width:220px}.filters select{max-width:100%;min-width:0}
#cases{table-layout:fixed}#cases td,#cases th{overflow-wrap:anywhere}
#cases col.c-status{width:96px}#cases col.c-suite{width:150px}#cases col.c-id{width:170px}#cases col.c-result{width:32%}
#cases tbody tr.row{cursor:pointer}#cases tbody tr.row:hover{background:var(--code)}
#cases td.result{color:var(--ink2);font-size:12.5px}
tr.detail td{background:var(--page);padding:12px 16px}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.detail-grid>div{min-width:0}
.detail h4{margin:10px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.answer{white-space:pre-wrap;background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:10px 12px}
.kv th{width:250px}
pre{max-width:100%}
@media (max-width:900px){nav{position:static;width:auto;border-right:0;border-bottom:1px solid var(--grid)}main{margin-left:0;padding:12px}
section{padding:16px}.detail-grid{grid-template-columns:1fr}
section table:not(#cases){display:block;overflow-x:auto;white-space:nowrap}
#cases col.c-suite,#cases col.c-id,#cases td:nth-child(2),#cases th:nth-child(2),#cases td:nth-child(3),#cases th:nth-child(3){display:none}
#cases col.c-status{width:72px}#cases col.c-result{width:40%}}
"""

JS = r"""
const DATA = JSON.parse(document.getElementById('data').textContent);
const $ = (s, el = document) => el.querySelector(s);
const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids.filter(k => k != null)); return n; };
const suiteSel = $('#f-suite'), statusSel = $('#f-status'), q = $('#f-q'), tbody = $('#cases tbody'), shown = $('#shown');
for (const [k, v] of Object.entries(DATA.suites)) suiteSel.append(el('option', {value: k, textContent: v}));
let limit = 200;
const chip = s => el('span', {className: 'chip ' + s.replace('/', ''), textContent: s});
const pretty = v => el('pre', {textContent: JSON.stringify(v, null, 2)});
function safeLink(url, text) {
  try { const u = new URL(url); if (u.protocol === 'https:' || u.protocol === 'http:') return el('a', {href: u.href, textContent: text || u.href, target: '_blank', rel: 'noopener'}); } catch (e) {}
  return el('span', {textContent: text || url});
}
function detail(c) {
  const rec = c.record, out = rec.output || {}, left = el('div'), right = el('div');
  left.append(el('h4', {textContent: 'Case (input and expected truth)'}), pretty(rec.case));
  if (rec.error) left.append(el('h4', {textContent: 'Error'}), el('pre', {textContent: rec.error}));
  if (rec.first_error) left.append(el('h4', {textContent: 'First attempt'}), el('pre', {textContent: rec.first_error + ` (attempts: ${rec.attempts})`}));
  if (typeof out.answer === 'string') {
    right.append(el('h4', {textContent: `Answer · ${out.answer_model || ''}`}), el('div', {className: 'answer', textContent: out.answer}));
    if (out.judge) right.append(el('h4', {textContent: 'Judge'}), el('p', {textContent: `correct ${out.judge.correct ?? '–'}/2 · supported ${out.judge.supported ?? '–'} · abstained properly ${out.judge.abstained_properly ?? '–'} (${out.judge.model || ''})`}), el('p', {className: 'muted', textContent: out.judge.reason || ''}));
    if ((out.citations || []).length) { const ol = el('ol'); for (const s of out.citations) ol.append(el('li', {}, s.url ? safeLink(s.url, s.title || s.url) : el('span', {textContent: s.title || s.id}))); right.append(el('h4', {textContent: 'Sources'}), ol); }
    if ((out.hits || []).length) { const ul = el('ul'); for (const h of out.hits) ul.append(el('li', {}, el('b', {textContent: (h.title || '') + ': '}), el('span', {textContent: h.excerpt || ''}))); right.append(el('h4', {textContent: 'Evidence excerpts'}), ul); }
  }
  if (out.final_text) right.append(el('h4', {textContent: `Agent's final message · ${out.adapter}`}), el('div', {className: 'answer', textContent: out.final_text}));
  if (out.tools) right.append(el('h4', {textContent: 'Tool calls'}), el('p', {textContent: out.tools.join(' → ') || 'none'}));
  right.append(el('h4', {textContent: 'Scores'}), pretty(rec.scores || {}));
  const rest = Object.fromEntries(Object.entries(out).filter(([k]) => !['answer', 'judge', 'citations', 'hits', 'final_text'].includes(k)));
  right.append(el('details', {}, el('summary', {textContent: 'Full output'}), pretty(rest)));
  return el('div', {className: 'detail detail-grid'}, left, right);
}
function render() {
  const s = suiteSel.value, st = statusSel.value, term = q.value.trim().toLowerCase();
  const rows = DATA.cases.filter(c => (!s || c.suite === s) && (!st || c.status === st) &&
    (!term || (c.id + ' ' + c.label + ' ' + c.result).toLowerCase().includes(term)));
  tbody.replaceChildren();
  for (const c of rows.slice(0, limit)) {
    const tr = el('tr', {className: 'row'}, el('td', {}, chip(c.status)), el('td', {textContent: DATA.suites[c.suite]}),
      el('td', {}, el('code', {textContent: c.id})), el('td', {className: 'label', textContent: c.label}), el('td', {className: 'result', textContent: c.result}));
    tr.addEventListener('click', () => {
      const next = tr.nextElementSibling;
      if (next && next.classList.contains('detail')) { next.remove(); return; }
      tr.after(el('tr', {className: 'detail'}, el('td', {colSpan: 5}, detail(c))));
    });
    tbody.append(tr);
  }
  shown.textContent = `${Math.min(rows.length, limit)} of ${rows.length} cases shown` + (rows.length > limit ? ' ' : '');
  $('#more').hidden = rows.length <= limit;
}
$('#more').addEventListener('click', () => { limit += 400; render(); });
for (const x of [suiteSel, statusSel]) x.addEventListener('change', () => { limit = 200; render(); });
q.addEventListener('input', () => { limit = 200; render(); });
document.querySelectorAll('button.browse').forEach(b => b.addEventListener('click', () => {
  suiteSel.value = b.dataset.suite; statusSel.value = ''; q.value = ''; limit = 200; render(); $('#tasks').scrollIntoView();
}));
render();
// The task table and the figures settle after the browser has scrolled to any #anchor; scroll again once they have.
window.addEventListener('load', () => {
  if (!location.hash) return;
  const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (target) target.scrollIntoView({behavior: 'instant'});
});
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="layout">
<nav>
  <h1>RCA Atlas evaluation</h1>
  <div class="sub">run {run} · built {built}</div>
  <a href="#overview">Overview</a><a href="#tasks">All tasks ({n_cases})</a><a href="#environment">Environment</a>
  <div class="group">Suites</div>{nav}
</nav>
<main>
<section id="overview">
  <h2>Overview</h2>
  <p>{n_suites} suites and {n_cases} cases. Each headline is a point estimate with a 95 % interval
  (Wilson for proportions, case bootstrap otherwise); a suite with errored cases never shows as meeting its target.
  How the sets were built and scored: {method}.</p>
  <table><thead><tr><th>Capability</th><th>Axis</th><th>Headline metric</th><th class="num">Value [95% CI]</th><th class="num">n</th><th>Status</th></tr></thead>
  <tbody>{score_rows}</tbody></table>
  {scorecard}
</section>
<section id="tasks">
  <h2>All tasks</h2>
  <p class="meta">Every case of every suite: what it asks, its expected truth, what the system returned, and how it scored.
  Click a row for the full record.</p>
  <div class="filters">
    <input id="f-q" type="search" placeholder="Search questions, ids, results…" aria-label="Search">
    <select id="f-suite" aria-label="Suite"><option value="">All suites</option></select>
    <select id="f-status" aria-label="Status"><option value="">Any status</option><option>pass</option><option>fail</option><option>error</option><option>n/a</option></select>
    <span id="shown" class="muted"></span>
  </div>
  <div><table id="cases"><colgroup><col class="c-status"><col class="c-suite"><col class="c-id"><col class="c-task"><col class="c-result"></colgroup><thead><tr><th>Status</th><th>Suite</th><th>Case</th><th>Task</th><th>Result</th></tr></thead><tbody></tbody></table></div>
  <p><button id="more" hidden>Show more</button></p>
</section>
{sections}
<section id="environment">
  <h2>Environment</h2>
  <p class="meta">What this run executed on{env_note}.</p>
  <table class="kv"><tbody>{env_rows}</tbody></table>
  <h3>Datasets and run provenance</h3>{prov}
  <h3>Agent sandbox tools (MCP server <code>src/atlas_tasks/mcp_server.py</code>; * = required)</h3>{tools}
  <h3>Per-task routes (<code>src/atlas_tasks/router_rules.json</code>)</h3>{routes}
  <h3>Reproduce</h3><pre>{reproduce}</pre>
</section>
</main></div>
<script type="application/json" id="data">{data}</script>
<script>{js}</script>
</body></html>
"""
