from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .schemas import AnswerRequest, EvidencePackage, ModelResponse


LIVE_ACTION = re.compile(r"\b(retrieve|download|plot|generate|current|status|today|yesterday|analy[sz]e|deeper evidence)\b", re.I)


class Retriever(Protocol):
    def retrieve(self, question: str) -> EvidencePackage: ...


class ToolRouter(Protocol):
    def recommend(self, question: str, evidence: EvidencePackage) -> list[dict[str, Any]]: ...
    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class GraphRAGOrchestrator:
    retriever: Retriever
    answer_provider: Any
    tool_router: ToolRouter | None = None

    def answer(self, question_id: str, question: str) -> ModelResponse:
        evidence = self.retriever.retrieve(question)
        tools: tuple[dict[str, Any], ...] = ()
        if self.tool_router and LIVE_ACTION.search(question):
            tools = tuple(self.tool_router.recommend(question, evidence))
        return self.answer_provider.answer(AnswerRequest(question_id, question, evidence, tools=tools))
