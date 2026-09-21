"""Bounded Gemini synthesis over a frozen Graph-RAG evidence package."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any


class AnsweringError(RuntimeError):
    pass


def _evidence_text(hits: list[dict[str, Any]], neighbors: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    blocks: list[str] = []
    citations: list[dict[str, str]] = []
    for hit in hits[:8]:
        citation = (hit.get("citations") or [{}])[0]
        source_id = citation.get("source_id") or hit["chunk_id"]
        title = citation.get("title") or hit.get("title") or source_id
        url = citation.get("url") or ""
        blocks.append(f"[{hit['chunk_id']}] {hit.get('title', '')}\n{hit.get('text', '')[:2400]}\nSource: {title} | {url}")
        citations.append({"id": hit["chunk_id"], "title": title, "url": url})
    if neighbors:
        graph = "\n".join(f"{item['predicate']}: {item['name']}" for item in neighbors[:30])
        blocks.append(f"Graph relationships:\n{graph}")
    return "\n\n".join(blocks)[:18_000], citations


class GeminiAnswerer:
    def __init__(self, api_key: str, *, model: str = "gemini-2.5-flash", timeout_seconds: float = 45.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def answer(self, question: str, hits: list[dict[str, Any]], neighbors: list[dict[str, Any]],
               max_output_tokens: int) -> dict[str, Any]:
        evidence, citations = _evidence_text(hits, neighbors)
        payload = {
            "systemInstruction": {"parts": [{"text": (
                "You are RCA Atlas. Answer only from the frozen evidence. Cite chunk IDs in square brackets. "
                "Do not claim current/live facts unless evidence explicitly contains a live tool result. "
                "If the user asks for current retrieval, analysis, plotting, or an exact current count, explain the "
                "appropriate tool is required rather than inventing a result.")} ]},
            "contents": [{"role": "user", "parts": [{"text": f"Question: {question}\n\nEvidence:\n{evidence}"}]}],
            "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.15},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode())
        except (urllib.error.URLError, ValueError) as error:
            raise AnsweringError(f"Gemini request failed: {type(error).__name__}") from error
        text = "".join(part.get("text", "") for candidate in raw.get("candidates", [])
                       for part in candidate.get("content", {}).get("parts", []))
        referenced = set(re.findall(r"\[([^\]]+)\]", text))
        selected = [item for item in citations if item["id"] in referenced]
        if not selected and citations:
            selected = citations[:3]
            text = f"{text.rstrip()}\n\nSources: " + " ".join(f"[{item['id']}]" for item in selected)
        usage = raw.get("usageMetadata", {})
        return {"answer": text, "citations": selected, "model": raw.get("modelVersion", self.model),
                "input_tokens": usage.get("promptTokenCount", 0), "output_tokens": usage.get("candidatesTokenCount", 0),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
