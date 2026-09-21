from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceItem:
    stable_id: str
    kind: str
    text: str
    source_url: str | None = None
    locator: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidencePackage:
    package_id: str
    corpus_version: str
    graph_version: str
    query: str
    items: tuple[EvidenceItem, ...]
    graph_entities: tuple[str, ...] = ()
    graph_edges: tuple[str, ...] = ()
    retrieval_trace: dict[str, Any] = field(default_factory=dict)

    def prompt_text(self) -> str:
        blocks = []
        for item in self.items:
            citation = item.source_url or "local provenance record"
            locator = f" ({item.locator})" if item.locator else ""
            blocks.append(f"[{item.stable_id}] {item.text}\nSource: {citation}{locator}")
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class Budget:
    max_input_tokens: int = 32_000
    max_output_tokens: int = 2_000
    max_cost_usd: float = 1.0
    max_tool_calls: int = 3
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class AnswerRequest:
    question_id: str
    question: str
    evidence: EvidencePackage
    prompt_version: str = "rca-answer-v1"
    budget: Budget = field(default_factory=Budget)
    tools: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    exact_model_version: str
    answer: str
    citations: tuple[str, ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
