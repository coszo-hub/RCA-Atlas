"""Chunks that belong to the full-text retrieval layer although their collection is searched by default.

RCA Information (Arcada) carries 18 papers in full text, several hundred chunks that could fill a literature
answer's evidence. Each such paper keeps one chunk in the main search, its first (preferring a copy with a URL), so
it can still be found; its other chunks join the layer, which the search leaves out unless asked for a paper's
passages. A layer chunk carries the keys the Worker names the paper by: its DOI and its document ID.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

LAYER = "fulltext"


def doi_key(value: Any) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", str(value or "").strip().lower())


def arcada_layer(records: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """chunk_id -> paper keys, for the Arcada paper chunks that move to the layer."""
    papers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r.get("source_row_type") == "paper":
            papers[doi_key(r.get("doi")) or str(r.get("title") or "").strip().lower()].append(r)
    layer: dict[str, list[str]] = {}
    for key, rows in papers.items():
        if len(rows) < 2:
            continue
        keep = min(rows, key=lambda r: (not r.get("source_url"), int(r.get("position") or 0), str(r["chunk_id"])))
        for r in rows:
            if r is not keep:
                layer[str(r["chunk_id"])] = [k for k in (doi_key(r.get("doi")), str(r.get("parent_id") or "")) if k]
    return layer


def assign(collection_id: str, records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return arcada_layer(records) if collection_id == "arcada" else {}
