from __future__ import annotations

import argparse
import json
from pathlib import Path

from .costs import cost_report, load_prices
from .embeddings import load_index_specs
from .runner import dry_run_estimate


ROOT = Path(__file__).resolve().parent


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="RCA Atlas Model Lab")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--dataset", type=Path, default=ROOT / "datasets/rca_eval_v1.jsonl")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--dataset", type=Path, default=ROOT / "datasets/rca_eval_v1.jsonl")
    dry.add_argument("--models", nargs="+", default=["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
    report = sub.add_parser("cost-report")
    report.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        rows = read_jsonl(args.dataset)
        ids = [row["id"] for row in rows]
        if len(rows) < 50 or len(ids) != len(set(ids)):
            raise SystemExit("dataset must have at least 50 unique question IDs")
        indexes = load_index_specs(ROOT / "config/embedding_indexes.json")
        print(json.dumps({"questions": len(rows), "categories": sorted({r["category"] for r in rows}),
                          "indexes": len(indexes)}, indent=2))
        return 0
    if args.command == "dry-run":
        rows = read_jsonl(args.dataset)
        prices = load_prices(ROOT / "config/prices.json")
        print(json.dumps(dry_run_estimate(rows, args.models, prices), indent=2))
        return 0
    rows = read_jsonl(args.results)
    print(json.dumps(cost_report(rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
