"""Gateway app. Every upstream call goes through call_toolkit or the ERDDAP client, the limiter, and the cache."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import errors, routes_data
from .app_support import call_toolkit
from .bundle_index import BundleIndex
from .cache import HostLimiter, TTLCache
from .config import Settings

STATUS_TTL = 120


@dataclass
class Deps:
    index: BundleIndex
    nereus: Any = None
    qaqc: Any = None
    pi: Any = None
    earthscope: Any = None
    erddap: Any = None
    chat: Callable[[str], dict] | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))


def not_found(source: str, message: str) -> JSONResponse:
    return JSONResponse(errors.body(source, message), status_code=404)


def create_app(settings: Settings, deps: Deps) -> FastAPI:
    app = FastAPI(title="Atlas gateway", docs_url=None, redoc_url=None)
    errors.install(app)
    cache = TTLCache()
    limiter = HostLimiter(settings.per_host_limit, settings.upstream_timeout)
    app.state.settings, app.state.deps, app.state.cache, app.state.limiter = settings, deps, cache, limiter

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/status/{refdes}")
    def status(refdes: str):
        if not deps.index.has_refdes(refdes):
            return not_found("atlas", "unknown sensor")

        def fetch():
            with limiter.slot("Nereus"):
                res = call_toolkit("Nereus", lambda: deps.nereus.instrument_status(refdes))
            if not isinstance(res.get("instruments"), list):
                raise errors.UpstreamError("Nereus", "unexpected response shape")
            match = next((i for i in res["instruments"] if i.get("designator") == refdes), None)
            if match is None:
                return None
            data = ((match.get("latestDataStatusConnection") or {}).get("status")) or None
            return {"refdes": refdes, "status": match.get("operationalStatusCode"),
                    "data": {k: data.get(k) for k in ("code", "checkedAt", "delay")} if data else None,
                    "evidenceMode": res.get("evidence_mode"), "source": "Nereus", "sourceUrl": res.get("source_url")}

        result = cache.get_or_set(f"status:{refdes}", STATUS_TTL, fetch)
        return result if result else not_found("Nereus", "Nereus does not track this sensor")

    routes_data.register(app, settings, deps, cache, limiter)
    return app
