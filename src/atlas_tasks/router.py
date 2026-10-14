"""Per-task priority routing: decide what kind of task a question is and who answers it.

The Worker today knows four routes (live Axial day counts, named-dataset
downloads, instrument inventories, and everything else as research). Questions
that need a computation — a clock correction, dv/v, a calibration — fall
through to the research prompt, which can only describe them. The router names
the task, the tools that must produce its numbers, the answer style, and the
corpus collections to favour. Its rules live in `router_rules.json` so the
Worker can share them.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).with_name("router_rules.json")


@dataclass(frozen=True)
class Route:
    task: str
    priority: int
    handler: dict
    collections: tuple[str, ...]
    matched: tuple[str, ...] = ()
    candidates: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=4)
def load_rules(path: str = str(RULES_PATH)) -> dict:
    rules = json.loads(Path(path).read_text())
    for task in rules["tasks"]:
        task["_all"] = [[re.compile(p, re.I) for p in group] for group in task["all"]]
        task["_none"] = [re.compile(p, re.I) for p in task.get("none", [])]
    return rules


def route(question: str, rules: dict | None = None) -> Route:
    rules = rules or load_rules()
    q = " ".join(str(question or "").split())
    matches = []
    for task in rules["tasks"]:
        hits = []
        for group in task["_all"]:
            found = [p.pattern for p in group if p.search(q)]
            if not found:
                break
            hits.extend(found)
        else:
            if not any(p.search(q) for p in task["_none"]):
                matches.append((task["priority"], len(hits), task, tuple(hits)))
    if not matches:
        return Route(rules["default"], 0, {"kind": "corpus", "tools": [], "answer": "research"}, ())
    matches.sort(key=lambda m: (m[0], m[1]), reverse=True)
    _, _, best, hits = matches[0]
    return Route(best["task"], best["priority"], best["handler"], tuple(best.get("collections", ())), hits,
                 tuple(m[2]["task"] for m in matches[1:]))


TASKS = tuple(t["task"] for t in load_rules()["tasks"]) + (load_rules()["default"],)
