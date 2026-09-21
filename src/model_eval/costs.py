from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .schemas import Usage


@dataclass(frozen=True)
class Price:
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float = 0.0


def estimate_cost(usage: Usage, price: Price) -> float:
    uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
    return (uncached * price.input_per_million + usage.cached_input_tokens * price.cached_input_per_million
            + usage.output_tokens * price.output_per_million) / 1_000_000


def load_prices(path: Path) -> dict[str, Price]:
    raw = json.loads(path.read_text())
    return {key: Price(**value) for key, value in raw["models"].items()}


def cost_report(records: Iterable[dict]) -> dict:
    by_model: dict[str, dict[str, float | int]] = {}
    total = 0.0
    for record in records:
        model = record.get("answer_model", "unknown")
        cost = float(record.get("estimated_cost_usd", 0.0))
        total += cost
        row = by_model.setdefault(model, {"runs": 0, "estimated_cost_usd": 0.0})
        row["runs"] = int(row["runs"]) + 1
        row["estimated_cost_usd"] = float(row["estimated_cost_usd"]) + cost
    return {"total_estimated_cost_usd": round(total, 8), "by_model": by_model}
