from __future__ import annotations

import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .embeddings import BGE384Provider, EmbeddingProvider, checked_embedding
from .models import (ContextRequest, ContextResponse, NeighborsRequest, NeighborsResponse,
                     SearchRequest, SearchResponse, ToolsRequest, ToolsResponse)
from .repository import PostgresRepository, Repository

LOGGER = logging.getLogger(__name__)


def create_app(*, settings: Settings | None = None, repository: Repository | None = None,
               embedding_provider: EmbeddingProvider | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    owns_repository = repository is None
    repo = repository or PostgresRepository(
        resolved.database_url, min_size=resolved.pool_min_size, max_size=resolved.pool_max_size,
        statement_timeout_ms=resolved.statement_timeout_ms,
        embedding_model=resolved.embedding_model,
    )
    embedder = embedding_provider or BGE384Provider(resolved.embedding_model)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_repository:
            repo.close()

    app = FastAPI(title="Graph-RAG Public API", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    static_root = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")
    app.state.repository = repo
    app.state.embedding_provider = embedder
    app.state.settings = resolved

    def authorize(x_api_key: Annotated[Optional[str], Header()] = None) -> None:
        presented = hashlib.sha256((x_api_key or "").encode("utf-8")).hexdigest()
        if x_api_key is None or not any(hmac.compare_digest(presented, key) for key in resolved.api_key_sha256):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")

    @app.get("/", include_in_schema=False)
    def atlas_workspace() -> FileResponse:
        """Serve the local evidence workspace without exposing credentials."""
        return FileResponse(static_root / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/health")
    def health() -> dict[str, str]:
        # No connection strings, versions, table names, or exception text leak here.
        if not repo.health():
            raise HTTPException(status_code=503, detail="service unavailable")
        return {"status": "ok"}

    @app.post("/v1/search", response_model=SearchResponse)
    def search(body: SearchRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        if body.lexical_weight + body.vector_weight <= 0:
            raise HTTPException(422, "at least one retrieval weight must be positive")
        try:
            vector = checked_embedding(embedder, body.query)
            hits = repo.search(body.query, vector, limit=body.limit,
                               lexical_weight=body.lexical_weight, vector_weight=body.vector_weight,
                               collection_ids=body.collection_ids)
            return {"query": body.query, "hits": hits}
        except HTTPException:
            raise
        except Exception:
            LOGGER.exception("search failed")
            raise HTTPException(503, "search temporarily unavailable") from None

    @app.post("/v1/neighbors", response_model=NeighborsResponse)
    def neighbors(body: NeighborsRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        try:
            return {"neighbors": repo.neighbors([seed.model_dump() for seed in body.seeds], hops=body.hops, limit=body.limit)}
        except Exception:
            LOGGER.exception("neighbor lookup failed")
            raise HTTPException(503, "neighbor lookup temporarily unavailable") from None

    @app.post("/v1/tools", response_model=ToolsResponse)
    def tools(body: ToolsRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        try:
            return {"query": body.query, "tool_hints": repo.route_tools(body.query, limit=body.limit)}
        except Exception:
            LOGGER.exception("tool routing failed")
            raise HTTPException(503, "tool routing temporarily unavailable") from None

    @app.post("/v1/context", response_model=ContextResponse)
    def context(body: ContextRequest, _: None = Depends(authorize)) -> dict[str, Any]:
        if body.lexical_weight + body.vector_weight <= 0:
            raise HTTPException(422, "at least one retrieval weight must be positive")
        try:
            vector = checked_embedding(embedder, body.query)
            hits = repo.search(body.query, vector, limit=body.limit,
                               lexical_weight=body.lexical_weight, vector_weight=body.vector_weight,
                               collection_ids=body.collection_ids)
            seed_nodes = []
            seen = set()
            for hit in hits:
                key = (hit["collection_id"], hit.get("metadata", {}).get("node_local_id"))
                if key[1] and key not in seen:
                    seed_nodes.append({"collection_id": key[0], "local_id": key[1]})
                    seen.add(key)
            seed_nodes = seed_nodes[:20]
            neighbors = repo.neighbors(seed_nodes, hops=body.graph_hops,
                                       limit=min(100, body.neighbors_per_seed * max(1, len(seed_nodes)))) \
                if seed_nodes and body.graph_hops else []
            tool_hints = repo.route_tools(body.query, limit=body.tool_limit) if body.tool_limit else []
            return {"query": body.query, "hits": hits, "neighbors": neighbors, "tool_hints": tool_hints}
        except Exception:
            LOGGER.exception("context lookup failed")
            raise HTTPException(503, "context temporarily unavailable") from None

    return app


app = None  # Use app.asgi:create_app under Gunicorn/Uvicorn, or app.factory:app below.
