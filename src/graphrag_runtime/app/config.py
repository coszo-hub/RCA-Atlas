from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key_sha256: frozenset[str]
    statement_timeout_ms: int = 4_000
    pool_min_size: int = 1
    pool_max_size: int = 10
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    @classmethod
    def from_env(cls) -> "Settings":
        keys = frozenset(value.strip().lower() for value in os.environ.get("GRAPHRAG_API_KEY_SHA256", "").split(",") if value.strip())
        if not keys:
            raise RuntimeError("GRAPHRAG_API_KEY_SHA256 must contain at least one SHA-256 digest")
        if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in keys):
            raise RuntimeError("GRAPHRAG_API_KEY_SHA256 contains an invalid digest")
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        timeout = min(15_000, max(250, int(os.environ.get("GRAPHRAG_STATEMENT_TIMEOUT_MS", "4000"))))
        pool_min = min(20, max(1, int(os.environ.get("GRAPHRAG_POOL_MIN", "1"))))
        pool_max = min(50, max(pool_min, int(os.environ.get("GRAPHRAG_POOL_MAX", "10"))))
        return cls(database_url, keys, timeout, pool_min, pool_max,
                   os.environ.get("GRAPHRAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"))
