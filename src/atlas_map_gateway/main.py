"""uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787"""
from __future__ import annotations

import httpx

from . import errors, toolkits
from .app import Deps, create_app
from .bundle_index import BundleIndex
from .config import Settings, load_settings
from .erddap import ErddapClient


def make_chat(settings: Settings, http: httpx.Client):
    def chat(question: str) -> dict:
        try:
            resp = http.post(f"{settings.api_url.rstrip('/')}/v1/answer", headers={"X-API-Key": settings.api_key},
                             json={"query": question, "limit": 8, "max_output_tokens": 600})
        except httpx.TimeoutException:
            raise errors.UpstreamError("Atlas chat", "the answer took too long", 504) from None
        except httpx.HTTPError as exc:
            raise errors.UpstreamError("Atlas chat", f"chat service unreachable: {exc}") from None
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code != 200:
            detail = body.get("detail") if isinstance(body, dict) else None
            raise errors.UpstreamError("Atlas chat", str(detail or f"chat service returned HTTP {resp.status_code}"))
        if not isinstance(body, dict):
            raise errors.UpstreamError("Atlas chat", "chat service returned an unreadable answer")
        return {"answer": body.get("answer", ""), "model": body.get("answer_model"),
                "citations": [{"id": c.get("id"), "title": c.get("title"), "url": c.get("url") or ""}
                              for c in body.get("answer_citations", [])]}
    return chat


def build() -> "FastAPI":
    settings = load_settings()
    kits = toolkits.make(settings)
    return create_app(settings, Deps(
        index=BundleIndex.from_dir(settings.bundle_dir),
        erddap=ErddapClient(httpx.Client(timeout=settings.upstream_timeout)),
        chat=make_chat(settings, httpx.Client(timeout=settings.chat_timeout)),
        **kits))


def __getattr__(name):   # PEP 562: `atlas_map_gateway.main:app` builds on first access, so tests can import make_chat
    if name == "app":
        globals()["app"] = build()
        return globals()["app"]
    raise AttributeError(name)
