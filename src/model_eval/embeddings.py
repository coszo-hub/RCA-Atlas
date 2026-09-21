from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from .providers import Transport, json_transport


@dataclass(frozen=True)
class IndexSpec:
    name: str
    model: str
    provider: str
    dimension: int
    content_types: tuple[str, ...]
    version: str
    status: str = "candidate"
    api_key_env: str | None = None
    base_url: str | None = None


class EmbeddingProvider(Protocol):
    model: str
    dimension: int
    def embed(self, values: Sequence[str], *, input_type: str) -> list[list[float]]: ...


class HTTPEmbeddingProvider:
    """Provider-neutral adapter for OpenAI-compatible, Voyage, Cohere, Jina, and Gemini embeddings."""

    def __init__(self, spec: IndexSpec, *, transport: Transport = json_transport) -> None:
        self.spec, self.transport = spec, transport
        self.model, self.dimension = spec.model, spec.dimension

    def embed(self, values: Sequence[str], *, input_type: str) -> list[list[float]]:
        if not self.spec.base_url:
            raise RuntimeError(f"index {self.spec.name} has no remote endpoint")
        key = os.environ.get(self.spec.api_key_env or "")
        if self.spec.api_key_env and not key:
            raise RuntimeError(f"{self.spec.api_key_env} is required")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        url = self.spec.base_url.rstrip("/")
        provider = self.spec.provider
        if provider == "google":
            payload = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": text}]},
                                      "taskType": "RETRIEVAL_DOCUMENT" if input_type == "document" else "RETRIEVAL_QUERY",
                                      "outputDimensionality": self.dimension} for text in values]}
            raw = self.transport(f"{url}/models/{self.model}:batchEmbedContents?key={key}", {}, payload, 60.0)
            vectors = [row.get("values", []) for row in raw.get("embeddings", [])]
        elif provider == "cohere":
            payload = {"model": self.model, "texts": list(values),
                       "input_type": "search_document" if input_type == "document" else "search_query",
                       "embedding_types": ["float"]}
            raw = self.transport(f"{url}/embed", headers, payload, 60.0)
            vectors = raw.get("embeddings", {}).get("float", [])
        else:
            payload = {"model": self.model, "input": list(values), "dimensions": self.dimension}
            if provider == "voyage":
                payload["input_type"] = input_type
            raw = self.transport(f"{url}/embeddings", headers, payload, 60.0)
            vectors = [row.get("embedding", []) for row in raw.get("data", [])]
        if len(vectors) != len(values) or any(len(row) != self.dimension for row in vectors):
            raise RuntimeError(f"{self.spec.name} returned an invalid embedding shape")
        return [[float(value) for value in row] for row in vectors]


class ContentHashEmbeddingCache:
    """Filesystem cache keyed by index version, input type, and content hash."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, spec: IndexSpec, text: str, input_type: str) -> Path:
        digest = hashlib.sha256(f"{spec.version}\0{input_type}\0{text}".encode()).hexdigest()
        return self.root / spec.name / digest[:2] / f"{digest}.json"

    def get(self, spec: IndexSpec, text: str, input_type: str) -> list[float] | None:
        path = self._path(spec, text, input_type)
        return json.loads(path.read_text())["embedding"] if path.exists() else None

    def put(self, spec: IndexSpec, text: str, input_type: str, embedding: Sequence[float]) -> None:
        path = self._path(spec, text, input_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                    "index_version": spec.version, "embedding": list(embedding)}) + "\n")


def load_index_specs(path: Path) -> dict[str, IndexSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {row["name"]: IndexSpec(**{**row, "content_types": tuple(row["content_types"])}) for row in raw["indexes"]}
