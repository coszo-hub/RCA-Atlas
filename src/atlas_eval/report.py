"""Turn a run directory into report.md, figures, and summary.json."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import plotstyle as ps
from .runner import load_records
from .suites import SUITES
from .suites.base import Metric, to_jsonable


def fmt_metric(m: Metric) -> str:
    if m.value is None or not math.isfinite(m.value):
        return "n/a"
    if m.unit:
        digits = 2 if abs(m.value) >= 1 else 4 if abs(m.value) < 0.01 else 3
        ci = f" [{m.low:.{digits}g}, {m.high:.{digits}g}]" if math.isfinite(m.low) and math.isfinite(m.high) else ""
        return f"{m.value:.{digits}g} {m.unit}{ci}"
    ci = f" [{m.low:.0%}, {m.high:.0%}]" if math.isfinite(m.low) and math.isfinite(m.high) else ""
    return f"{m.value:.0%}{ci}" if m.value <= 1.0001 else f"{m.value:.3g}"


def status(m: Metric, errors: int = 0) -> str:
    if errors:
        return f"**{errors} case(s) errored**"   # a tool that throws must never look like a pass
    met = m.meets_target
    if met is None:
        return ""
    target = f"{m.target:.0%}" if not m.unit else f"{m.target:g} {m.unit}"
    return f"meets {target}" if met else f"**below {target}**"


def md_table(rows: list[dict], columns: list[str] | None = None, limit: int = 30) -> str:
    if not rows:
        return "_none_\n"
    columns = columns or list(rows[0])

    def cell(v):
        if isinstance(v, float):
            return "n/a" if not math.isfinite(v) else (f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}")
        if isinstance(v, (list, dict)):
            return json.dumps(v)[:80]
        return str(v).replace("|", "\\|").replace("\n", " ")[:160]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"\n_{len(rows) - limit} more rows in summary.json_")
    return "\n".join(lines) + "\n"


def scorecard_figure(entries: list[tuple[str, Metric, int]], path: Path) -> Path:
    """One row per capability: headline value, 95% interval, target tick, and a worded status."""
    entries = [(n, m, e) for n, m, e in entries if not m.unit and m.value is not None and math.isfinite(m.value)]
    fig, ax = ps.new(9.2, 0.42 * len(entries) + 1.3)
    y = np.arange(len(entries))[::-1]
    for yi, (name, m, errors) in zip(y, entries):
        lo = m.low if math.isfinite(m.low) else m.value
        hi = m.high if math.isfinite(m.high) else m.value
        ax.plot([lo, hi], [yi, yi], color=ps.SERIES[0], lw=2, solid_capstyle="round")
        ax.plot(m.value, yi, "o", color=ps.SERIES[0], ms=7, mec=ps.SURFACE, mew=1.5)
        if m.target is not None:
            ax.plot([m.target, m.target], [yi - 0.28, yi + 0.28], color=ps.INK_2, lw=1.2)
        met = False if errors else m.meets_target
        ax.text(1.10, yi, f"{m.value:.0%}", va="center", ha="right", fontsize=8, color=ps.INK,
                transform=ax.get_yaxis_transform())
        ax.text(1.12, yi, f"n={m.n}", va="center", fontsize=7.5, color=ps.MUTED, transform=ax.get_yaxis_transform())
        if met is not None:
            ax.text(1.25, yi, f"{errors} errored" if errors else "meets target" if met else "below target", va="center", fontsize=8,
                    color=ps.STATUS["good"] if met else ps.STATUS["critical"], transform=ax.get_yaxis_transform())
    ax.set_yticks(y, [n for n, _, _ in entries], fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Headline metric with 95% interval (vertical tick = target)")
    ax.set_title("RCA Atlas capability scorecard")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.subplots_adjust(right=0.74)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return path


def write_report(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    figdir = run_dir / "figures"
    header = json.loads((run_dir / "run.json").read_text()) if (run_dir / "run.json").exists() else {}
    sections, summary_json, card = [], {}, []
    for name, suite in SUITES.items():
        records = load_records(run_dir, name)
        if not records:
            continue
        prov_path = run_dir / "provenance" / f"{name}.json"
        prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
        s = suite.summarize(records)
        figs = suite.figures(records, figdir)
        summary_json[name] = s.to_dict() | {"provenance": prov}
        errors = [r for r in records if r.get("error")]
        card.append((suite.title, s.headline, suite, len(errors)))
        lines = [f"## {suite.title}\n",
                 f"**Capability.** {suite.capability}.  **Axis.** {suite.axis}.  **Cases.** {len(records)}"
                 f" ({len(errors)} errored).  **Dataset.** `{suite.dataset}` (sha256 `{prov.get('dataset_sha256', '')[:12]}`)\n",
                 f"{suite.description}\n",
                 "| Metric | Value [95% CI] | n | Target |", "|---|---|---|---|"]
        lines += [f"| {m.name}{' — ' + m.note if m.note else ''} | {fmt_metric(m)} | {m.n} | {status(m)} |" for m in s.metrics]
        lines.append("")
        for fig in figs:
            lines.append(f"![{fig.stem}](figures/{fig.name})\n")
        for note in s.notes:
            lines.append(f"- {note}")
        if s.notes:
            lines.append("")
        for tname, rows in s.tables.items():
            if tname in ("confusion",):
                continue
            lines.append(f"<details><summary>{tname.replace('_', ' ')}</summary>\n\n{md_table(rows)}\n</details>\n")
        if errors:
            lines.append(f"<details><summary>errors ({len(errors)})</summary>\n\n" +
                         md_table([{"case": r["case_id"], "error": r["error"]} for r in errors]) + "\n</details>\n")
        sections.append("\n".join(lines))
    scorecard = scorecard_figure([(t, m, e) for t, m, _, e in card], figdir / "scorecard.png")
    table = ["| Capability | Axis | Headline metric | Value [95% CI] | n | Status |", "|---|---|---|---|---|---|"]
    table += [f"| {t} | {suite.axis} | {m.name} | {fmt_metric(m)} | {m.n} | {status(m, e)} |" for t, m, suite, e in card]
    git = header.get("git", {})
    doc = [f"# RCA Atlas evaluation — {header.get('run_id', run_dir.name)}\n",
           f"Run created {header.get('created_utc', '?')} on commit `{git.get('commit', '?')[:10]}`"
           f"{' (uncommitted changes)' if git.get('dirty') else ''}, branch `{git.get('branch', '?')}`. "
           "Every value is a point estimate with a 95% interval (Wilson for proportions, case bootstrap otherwise). "
           "Method: `src/atlas_eval/EVALUATION_METHOD.md`.\n",
           "## Scorecard\n", "\n".join(table) + "\n", f"![scorecard](figures/{scorecard.name})\n", *sections]
    path = run_dir / "report.md"
    path.write_text("\n".join(doc))
    (run_dir / "summary.json").write_text(json.dumps(to_jsonable(summary_json), indent=2) + "\n")
    return path
