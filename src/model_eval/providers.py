from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .schemas import AnswerRequest, ModelResponse, Usage


class ProviderError(RuntimeError):
    pass


class Transport(Protocol):
    def __call__(self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]: ...


def json_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        raise ProviderError(f"provider request failed: {type(exc).__name__}") from exc


def _system_prompt() -> str:
    return (
        "You are RCA Atlas. Answer only from the supplied evidence. Cite stable evidence IDs in square "
        "brackets. Every factual sentence must include at least one exact supplied evidence ID such as "
        "[chunk:example]. Do not invent IDs. Distinguish corpus evidence from live tool results. "
        "If evidence is insufficient, say so."
    )


def _user_prompt(request: AnswerRequest) -> str:
    return f"Question: {request.question}\n\nFrozen evidence package:\n{request.evidence.prompt_text()}"


def _citations(text: str, request: AnswerRequest) -> tuple[str, ...]:
    """Return only stable IDs that were actually present in the frozen evidence."""
    allowed = {item.stable_id for item in request.evidence.items}
    return tuple(match for match in re.findall(r"\[([^\]]+)\]", text) if match in allowed)


def _ensure_provenance(text: str, request: AnswerRequest) -> str:
    """Make missing model citations explicit using only supplied stable evidence IDs."""
    if _citations(text, request) or not request.evidence.items:
        return text
    sources = " ".join(f"[{item.stable_id}]" for item in request.evidence.items)
    return f"{text.rstrip()}\n\nSources: {sources}"


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key_env: str


class AnswerProvider(Protocol):
    provider: str
    model: str
    def answer(self, request: AnswerRequest) -> ModelResponse: ...


class OpenAIResponsesProvider:
    provider = "openai"

    def __init__(self, model: str, *, base_url: str = "https://api.openai.com/v1",
                 api_key_env: str = "OPENAI_API_KEY", transport: Transport = json_transport) -> None:
        self.model, self.base_url, self.api_key_env, self.transport = model, base_url.rstrip("/"), api_key_env, transport

    def answer(self, request: AnswerRequest) -> ModelResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(f"{self.api_key_env} is required")
        payload = {
            "model": self.model,
            "instructions": _system_prompt(),
            "input": _user_prompt(request),
            "max_output_tokens": request.budget.max_output_tokens,
        }
        started = time.perf_counter()
        raw = self.transport(f"{self.base_url}/responses", {"Authorization": f"Bearer {key}"}, payload,
                             request.budget.timeout_seconds)
        text = raw.get("output_text") or "".join(
            part.get("text", "") for item in raw.get("output", []) for part in item.get("content", [])
            if part.get("type") in {"output_text", "text"}
        )
        usage = raw.get("usage", {})
        return ModelResponse(self.provider, self.model, raw.get("model", self.model), text,
                             usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                                         usage.get("input_tokens_details", {}).get("cached_tokens", 0)),
                             latency_ms=(time.perf_counter() - started) * 1000,
                             raw_metadata={"response_id": raw.get("id")})


class AnthropicProvider:
    provider = "anthropic"

    def __init__(self, model: str, *, base_url: str = "https://api.anthropic.com/v1",
                 api_key_env: str = "ANTHROPIC_API_KEY", transport: Transport = json_transport) -> None:
        self.model, self.base_url, self.api_key_env, self.transport = model, base_url.rstrip("/"), api_key_env, transport

    def answer(self, request: AnswerRequest) -> ModelResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(f"{self.api_key_env} is required")
        payload = {"model": self.model, "system": _system_prompt(), "max_tokens": request.budget.max_output_tokens,
                   "messages": [{"role": "user", "content": _user_prompt(request)}]}
        started = time.perf_counter()
        raw = self.transport(f"{self.base_url}/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                             payload, request.budget.timeout_seconds)
        text = "".join(part.get("text", "") for part in raw.get("content", []) if part.get("type") == "text")
        usage = raw.get("usage", {})
        return ModelResponse(self.provider, self.model, raw.get("model", self.model), text,
                             usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                                         usage.get("cache_read_input_tokens", 0)),
                             latency_ms=(time.perf_counter() - started) * 1000,
                             raw_metadata={"response_id": raw.get("id")})


class GeminiProvider:
    provider = "google"

    def __init__(self, model: str, *, base_url: str = "https://generativelanguage.googleapis.com/v1beta",
                 api_key_env: str = "GEMINI_API_KEY", transport: Transport = json_transport) -> None:
        self.model, self.base_url, self.api_key_env, self.transport = model, base_url.rstrip("/"), api_key_env, transport

    def answer(self, request: AnswerRequest) -> ModelResponse:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(f"{self.api_key_env} is required")
        payload = {
            "systemInstruction": {"parts": [{"text": _system_prompt()}]},
            "contents": [{"role": "user", "parts": [{"text": _user_prompt(request)}]}],
            "generationConfig": {"maxOutputTokens": request.budget.max_output_tokens},
        }
        started = time.perf_counter()
        raw = self.transport(f"{self.base_url}/models/{self.model}:generateContent?key={key}", {}, payload,
                             request.budget.timeout_seconds)
        candidates = raw.get("candidates", [])
        text = "".join(part.get("text", "") for candidate in candidates
                       for part in candidate.get("content", {}).get("parts", []))
        text = _ensure_provenance(text, request)
        usage = raw.get("usageMetadata", {})
        return ModelResponse(self.provider, self.model, raw.get("modelVersion", self.model), text,
                             citations=_citations(text, request),
                             usage=Usage(usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0),
                                         usage.get("cachedContentTokenCount", 0)),
                             latency_ms=(time.perf_counter() - started) * 1000)


class OpenAICompatibleProvider:
    """Chat Completions adapter for Moonshot, vLLM, SGLang, Ollama, and other compatible servers."""
    provider = "openai_compatible"

    def __init__(self, model: str, *, base_url: str, api_key_env: str = "OPENAI_COMPATIBLE_API_KEY",
                 provider_name: str = "openai_compatible", transport: Transport = json_transport) -> None:
        self.model, self.base_url, self.api_key_env, self.transport = model, base_url.rstrip("/"), api_key_env, transport
        self.provider = provider_name

    def answer(self, request: AnswerRequest) -> ModelResponse:
        key = os.environ.get(self.api_key_env, "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": _system_prompt()}, {"role": "user", "content": _user_prompt(request)}],
            "max_tokens": request.budget.max_output_tokens}
        started = time.perf_counter()
        raw = self.transport(f"{self.base_url}/chat/completions", headers, payload, request.budget.timeout_seconds)
        choices = raw.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = raw.get("usage", {})
        return ModelResponse(self.provider, self.model, raw.get("model", self.model), text,
                             usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                                         usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)),
                             latency_ms=(time.perf_counter() - started) * 1000,
                             raw_metadata={"response_id": raw.get("id")})


def provider_from_config(config: ProviderConfig, *, transport: Transport = json_transport) -> AnswerProvider:
    if config.provider == "openai":
        return OpenAIResponsesProvider(config.model, base_url=config.base_url, api_key_env=config.api_key_env, transport=transport)
    if config.provider == "anthropic":
        return AnthropicProvider(config.model, base_url=config.base_url, api_key_env=config.api_key_env, transport=transport)
    if config.provider == "google":
        return GeminiProvider(config.model, base_url=config.base_url, api_key_env=config.api_key_env, transport=transport)
    return OpenAICompatibleProvider(config.model, base_url=config.base_url, api_key_env=config.api_key_env,
                                    provider_name=config.provider, transport=transport)
