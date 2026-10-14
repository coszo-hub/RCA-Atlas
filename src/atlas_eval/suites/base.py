"""Common shape of an evaluation suite.

A suite owns one frozen dataset file (cases as JSONL), knows how to run one
case against a target, how to score one output against its case, and how to
summarise scored cases into metrics with confidence intervals.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DATASETS = Path(__file__).resolve().parent.parent / "datasets"


@dataclass
class Metric:
    name: str
    value: float
    low: float = math.nan
    high: float = math.nan
    n: int = 0
    unit: str = ""                 # "" for proportions in [0, 1]; otherwise a physical unit
    higher_is_better: bool = True
    target: float | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def meets_target(self) -> bool | None:
        if self.target is None or not math.isfinite(self.value):
            return None
        return self.value >= self.target if self.higher_is_better else self.value <= self.target


@dataclass
class Summary:
    headline: Metric
    metrics: list[Metric]
    tables: dict[str, list[dict]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"headline": self.headline.to_dict(), "metrics": [m.to_dict() for m in self.metrics],
                "tables": self.tables, "notes": self.notes}


class Suite:
    name = ""
    title = ""
    capability = ""                 # what the system does, in the user's words
    axis = ""                       # accuracy | detection | routing | retrieval | answer quality | robustness
    dataset = ""                    # file name under datasets/
    requires = "offline"            # offline | live
    description = ""

    def build_cases(self) -> list[dict]:
        """Generate the frozen case list (synthetic suites); hand-written suites return []."""
        return []

    def cases(self) -> list[dict]:
        path = DATASETS / self.dataset
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def dataset_sha256(self) -> str:
        return hashlib.sha256((DATASETS / self.dataset).read_bytes()).hexdigest()

    def run_case(self, case: dict, ctx: dict[str, Any]) -> dict:
        raise NotImplementedError

    def score_case(self, case: dict, output: dict) -> dict:
        raise NotImplementedError

    def summarize(self, records: list[dict]) -> Summary:
        raise NotImplementedError

    def figures(self, records: list[dict], outdir: Path) -> list[Path]:
        return []


def to_jsonable(value: Any) -> Any:
    """NumPy scalars and arrays become plain JSON; non-finite floats become null."""
    import numpy as np
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(to_jsonable(r), sort_keys=True) + "\n" for r in rows))


def ok_records(records: list[dict]) -> list[dict]:
    return [r for r in records if not r.get("error")]
