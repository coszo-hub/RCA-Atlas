from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


VISUAL_TERMS = re.compile(r"\b(figure|chart|plot|map|diagram|image|scan|histogram|visual)\b", re.I)
LITERATURE_TERMS = re.compile(r"\b(papers?|publications?|literature|citations?|doi|authors?|study|studies|full[ -]?text)\b", re.I)
IDENTIFIER_TERMS = re.compile(r"\b[A-Z]{2,}[A-Z0-9-]*\d[A-Z0-9-]*\b")


def route_query(query: str) -> tuple[str, ...]:
    routes = ["text", "keyword", "graph"]
    if VISUAL_TERMS.search(query):
        routes.append("visual")
    if LITERATURE_TERMS.search(query):
        routes.append("scientific")
    if IDENTIFIER_TERMS.search(query) and "keyword" not in routes:
        routes.append("keyword")
    return tuple(routes)


@dataclass(frozen=True)
class RankedCandidate:
    stable_id: str
    rank: int
    source: str
    payload: dict[str, Any]


def reciprocal_rank_fusion(result_sets: Sequence[Iterable[RankedCandidate]], *, k: int = 60,
                           source_weights: dict[str, float] | None = None) -> list[tuple[str, float, dict[str, Any]]]:
    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}
    weights = source_weights or {}
    for result_set in result_sets:
        for item in result_set:
            scores[item.stable_id] = scores.get(item.stable_id, 0.0) + weights.get(item.source, 1.0) / (k + item.rank)
            payloads.setdefault(item.stable_id, item.payload)
    return [(stable_id, score, payloads[stable_id]) for stable_id, score in
            sorted(scores.items(), key=lambda row: (-row[1], row[0]))]


def graph_expand(seed_ids: Sequence[str], adjacency: dict[str, Sequence[tuple[str, str]]], *, hops: int = 1,
                 limit: int = 100) -> list[tuple[str, str, str, int]]:
    seen, frontier, output = set(seed_ids), list(seed_ids), []
    for depth in range(1, min(max(hops, 0), 3) + 1):
        next_frontier = []
        for source in frontier:
            for predicate, target in adjacency.get(source, ()):
                if target in seen:
                    continue
                seen.add(target)
                output.append((source, predicate, target, depth))
                next_frontier.append(target)
                if len(output) >= limit:
                    return output
        frontier = next_frontier
    return output
