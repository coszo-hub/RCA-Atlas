from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .costs import Price, estimate_cost
from .schemas import AnswerRequest, EvidencePackage, ModelResponse


class Retriever(Protocol):
    def retrieve(self, question: dict[str, Any]) -> EvidencePackage: ...


class ToolExecutor(Protocol):
    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class QueryCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, namespace: str, key: dict[str, Any]) -> Path:
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: dict[str, Any]) -> dict[str, Any] | None:
        path = self._path(namespace, key)
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, namespace: str, key: dict[str, Any], value: dict[str, Any]) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n")


def evaluation_record(question: dict[str, Any], evidence: EvidencePackage, response: ModelResponse,
                      *, embedding_model: str, index_version: str, prompt_version: str,
                      automated_scores: dict[str, float] | None = None,
                      human_scores: dict[str, float] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0", "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "question_id": question["id"], "corpus_version": evidence.corpus_version,
        "graph_version": evidence.graph_version, "embedding_model": embedding_model,
        "index_version": index_version, "answer_provider": response.provider,
        "answer_model": response.model, "answer_model_exact_version": response.exact_model_version,
        "prompt_version": prompt_version, "evidence_package_id": evidence.package_id,
        "retrieved_chunk_ids": [item.stable_id for item in evidence.items if item.kind == "chunk"],
        "retrieved_figure_ids": [item.stable_id for item in evidence.items if item.kind == "figure"],
        "retrieved_graph_entities": list(evidence.graph_entities),
        "retrieved_graph_edges": list(evidence.graph_edges), "tool_calls": list(response.tool_calls),
        "tool_results": response.raw_metadata.get("tool_results", []), "answer": response.answer,
        "citations": list(response.citations), "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens, "cached_input_tokens": response.usage.cached_input_tokens,
        "latency_ms": response.latency_ms, "estimated_cost_usd": response.usage.estimated_cost_usd,
        "automated_scores": automated_scores or {}, "human_scores": human_scores or {},
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def run_frozen_answer_eval(questions: Iterable[dict[str, Any]], evidence_by_id: dict[str, EvidencePackage],
                           providers: Iterable[Any], output: Path, *, embedding_model: str,
                           index_version: str, price_by_model: dict[str, Price] | None = None) -> int:
    count = 0
    for question in questions:
        evidence = evidence_by_id[question["id"]]
        for provider in providers:
            request = AnswerRequest(question["id"], question["question"], evidence)
            response = provider.answer(request)
            price = (price_by_model or {}).get(response.model)
            if price:
                response = replace(response, usage=replace(
                    response.usage, estimated_cost_usd=estimate_cost(response.usage, price)))
            append_jsonl(output, evaluation_record(question, evidence, response,
                         embedding_model=embedding_model, index_version=index_version,
                         prompt_version=request.prompt_version))
            count += 1
    return count


def dry_run_estimate(questions: Iterable[dict[str, Any]], models: Iterable[str], prices: dict[str, Price],
                     *, evidence_tokens: int = 4_000, output_tokens: int = 800) -> dict[str, Any]:
    question_count = sum(1 for _ in questions)
    models_report = {}
    for model in models:
        if model not in prices:
            models_report[model] = {"requests": question_count, "estimated_cost_usd": None}
            continue
        from .schemas import Usage
        per_request = estimate_cost(Usage(evidence_tokens, output_tokens), prices[model])
        models_report[model] = {"requests": question_count, "estimated_cost_usd": round(per_request * question_count, 6)}
    return {"dry_run": True, "network_requests_sent": 0, "question_count": question_count, "models": models_report}
