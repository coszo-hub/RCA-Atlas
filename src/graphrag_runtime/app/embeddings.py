from __future__ import annotations

import os
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed_query(self, text: str) -> Sequence[float]: ...


class BGE384Provider:
    """Lazy FastEmbed BGE provider; cached deployments can run fully offline."""

    dimensions = 384

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._model = None

    def embed_query(self, text: str) -> list[float]:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:  # pragma: no cover - deployment configuration
                raise RuntimeError("install the 'local-embeddings' extra or inject an EmbeddingProvider") from error
            cache_dir = os.environ.get("GRAPHRAG_MODEL_CACHE") or None
            offline = os.environ.get("GRAPHRAG_EMBEDDING_OFFLINE", "").lower() in {"1", "true", "yes"}
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=cache_dir,
                                        local_files_only=offline)
        values = next(iter(self._model.query_embed(text)))
        result = [float(value) for value in values]
        if len(result) != self.dimensions:
            raise RuntimeError(f"embedding provider returned {len(result)} dimensions, expected 384")
        return result


def checked_embedding(provider: EmbeddingProvider, text: str) -> list[float]:
    values = [float(value) for value in provider.embed_query(text)]
    if provider.dimensions != 384 or len(values) != 384:
        raise ValueError("the public index requires 384-dimensional embeddings")
    return values
