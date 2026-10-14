"""RCA Atlas evaluation CLI.

    python -m atlas_eval list
    python -m atlas_eval build                       # regenerate the synthetic datasets (deterministic)
    python -m atlas_eval run --suites offline        # every suite that needs no network
    python -m atlas_eval run --suites retrieval answers --pace 6
    python -m atlas_eval run --suites agent --agent claude --agent-model haiku
    python -m atlas_eval judge results/<run>         # LLM judge for the answers suite
    python -m atlas_eval report results/<run>        # report.md, figures, summary.json, catalog.html
    python -m atlas_eval site results/<run>          # just the HTML catalog of every task, output, and result
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .suites import OFFLINE, SUITES

RESULTS = Path(__file__).resolve().parent / "results"


def main() -> int:
    p = argparse.ArgumentParser(prog="atlas_eval", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    b = sub.add_parser("build")
    b.add_argument("--suites", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("--suites", nargs="+", default=["offline"], help="suite names, 'offline', or 'all'")
    r.add_argument("--out", type=Path)
    r.add_argument("--limit", type=int)
    r.add_argument("--endpoint", default="https://rca-atlas.quakehunt.workers.dev")
    r.add_argument("--model", help="Worker answer model (default: the Worker's auto route)")
    r.add_argument("--pace", type=float, default=6.0, help="seconds between LLM answer requests")
    r.add_argument("--agent", choices=["oracle", "claude"], default="oracle")
    r.add_argument("--agent-model", default="haiku")
    rt = sub.add_parser("retry", help="re-run errored cases of one suite in a saved run")
    rt.add_argument("run_dir", type=Path)
    rt.add_argument("suite")
    rt.add_argument("--pace", type=float, default=20.0)
    rt.add_argument("--endpoint", default="https://rca-atlas.quakehunt.workers.dev")
    j = sub.add_parser("judge")
    j.add_argument("run_dir", type=Path)
    j.add_argument("--model", default="haiku")
    rep = sub.add_parser("report")
    rep.add_argument("run_dir", type=Path)
    st = sub.add_parser("site", help="write a self-contained HTML catalog of a run")
    st.add_argument("run_dir", type=Path)
    st.add_argument("--out", type=Path)
    args = p.parse_args()

    if args.cmd == "list":
        for name, s in SUITES.items():
            print(f"{name:16s} {s.requires:8s} {s.axis:15s} {s.title}")
        return 0
    if args.cmd == "build":
        from .runner import build_datasets
        for name, n in build_datasets(args.suites).items():
            print(f"{name}: {n} cases")
        return 0
    if args.cmd == "run":
        from .runner import run
        names = []
        for item in args.suites:
            names += OFFLINE if item == "offline" else list(SUITES) if item == "all" else [item]
        out = args.out or RESULTS / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ctx = {"endpoint": args.endpoint, "model": args.model, "pace_s": args.pace, "agent": args.agent,
               "agent_model": args.agent_model}
        run(names, out, ctx, args.limit)
        print(out)
        return 0
    if args.cmd == "retry":
        from .runner import retry_errors
        retry_errors(args.run_dir, args.suite, {"endpoint": args.endpoint, "pace_s": args.pace})
        return 0
    if args.cmd == "judge":
        from .judge import judge_run
        judge_run(args.run_dir, args.model)
        return 0
    if args.cmd == "report":
        from .report import write_report
        from .site import build_site
        print(write_report(args.run_dir))
        print(build_site(args.run_dir))
        return 0
    if args.cmd == "site":
        from .site import build_site
        print(build_site(args.run_dir, args.out))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
