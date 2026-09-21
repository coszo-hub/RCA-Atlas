from __future__ import annotations

import math
from typing import Sequence


def recall_at(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return len(set(retrieved[:k]) & relevant) / len(relevant) if relevant else 1.0


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    return next((1.0 / rank for rank, item in enumerate(retrieved, 1) if item in relevant), 0.0)


def ndcg_at(retrieved: Sequence[str], judgments: dict[str, float], k: int) -> float:
    def dcg(values: Sequence[float]) -> float:
        return sum((2 ** value - 1) / math.log2(index + 2) for index, value in enumerate(values))
    actual = dcg([judgments.get(item, 0.0) for item in retrieved[:k]])
    ideal = dcg(sorted(judgments.values(), reverse=True)[:k])
    return actual / ideal if ideal else 1.0


def retrieval_scores(retrieved: Sequence[str], relevant: set[str], judgments: dict[str, float] | None = None) -> dict[str, float]:
    return {"recall_at_5": recall_at(retrieved, relevant, 5), "recall_at_10": recall_at(retrieved, relevant, 10),
            "mrr": reciprocal_rank(retrieved, relevant), "ndcg_at_10": ndcg_at(retrieved, judgments or {}, 10)}
