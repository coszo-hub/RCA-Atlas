"""Gateway app. Every upstream call goes through call_toolkit or the ERDDAP client, the limiter, and the cache."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import errors, routes_data
from .app_support import call_toolkit
from .bundle_index import BundleIndex
from .cache import HostLimiter, TTLCache
from .config import Settings

STATUS_TTL = 120
FALLBACK_TTL = 1800   # data age changes slowly: ERDDAP refreshes daily, QA/QC plots daily or weekly
ERDDAP_LIVE_DAYS = 3  # a sensor Nereus does not track is operating when ERDDAP has readings this recent
# Nereus reports "live", "live_cache" (its own 60 s disk cache of a live answer) or "snapshot_fallback".
EVIDENCE_MODES = {"live": "live", "live_cache": "live", "snapshot_fallback": "snapshot"}


def head_last_modified(url: str, timeout: float = 10.0) -> str | None:
    """When a QA/QC plot was last regenerated (its Last-Modified header), as ISO 8601 UTC."""
    import urllib.request
    from email.utils import parsedate_to_datetime
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "rca-atlas-gateway"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            value = resp.headers.get("Last-Modified")
    except OSError as exc:
        raise errors.UpstreamError("QA/QC", f"QA/QC plot request failed: {exc}") from None
    return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


@dataclass
class Deps:
    index: BundleIndex
    nereus: Any = None
    qaqc: Any = None
    pi: Any = None
    earthscope: Any = None
    earthscope_root: Path | None = None   # only request dirs under here are deleted after decoding
    erddap: Any = None
    chat: Callable[[str], dict] | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))
    qaqc_modified: Callable[[str], str | None] = head_last_modified


def not_found(source: str, message: str) -> JSONResponse:
    return JSONResponse(errors.body(source, message), status_code=404)


def create_app(settings: Settings, deps: Deps, on_shutdown: Callable[[], None] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if on_shutdown:
                on_shutdown()

    app = FastAPI(title="Atlas gateway", docs_url=None, redoc_url=None, lifespan=lifespan)
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
                    "evidenceMode": EVIDENCE_MODES.get(res.get("evidence_mode"), res.get("evidence_mode")), "source": "Nereus", "sourceUrl": res.get("source_url")}

        result = cache.get_or_set(f"status:{refdes}", STATUS_TTL, fetch)
        if result:
            return result
        # Nereus does not track every sensor (none of CE04OSBP, for one). The data sources the map already reads still
        # say how recent its data are: ERDDAP's newest reading, else when its QA/QC day plot was last regenerated.
        # Recent ERDDAP readings count as operating; otherwise status stays null and the data's age and basis are given.
        fallback = cache.get_or_set(f"status-fallback:{refdes}", FALLBACK_TTL, lambda: data_age(refdes))
        return fallback if fallback else not_found("Nereus", "Nereus does not track this sensor")

    def data_age(refdes: str) -> dict | None:
        ds = deps.index.erddap_dataset(refdes)
        if ds and deps.erddap is not None:
            def fetch_vars():
                with limiter.slot("ERDDAP"):
                    return deps.erddap.variables(ds)
            try:
                end = cache.get_or_set(f"vars:{ds}", 3600, fetch_vars)["coverage"]["end"]   # the series route's key
            except errors.UpstreamError:
                end = None
            if end:
                # Readings within the last three days (ERDDAP refreshes about daily) count as operating.
                try:
                    recent = deps.now() - datetime.fromisoformat(end.replace("Z", "+00:00")) <= timedelta(days=ERDDAP_LIVE_DAYS)
                except ValueError:
                    recent = False
                return {"refdes": refdes, "status": "OPERATIONAL" if recent else None, "evidenceMode": "data_age",
                        "basis": "erddap", "latestAt": end, "source": "OOI ERDDAP",
                        "sourceUrl": f"https://erddap.dataexplorer.oceanobservatories.org/erddap/tabledap/{ds}.html"}
        if deps.qaqc is not None:
            try:
                with limiter.slot("QA/QC"):
                    res = call_toolkit("QA/QC", lambda: deps.qaqc.search_plots(reference_designator=refdes, time_span="day", limit=5))
                plot = next((p for p in res.get("plots", []) if p.get("reference_designator") == refdes), None)
                if plot:
                    with limiter.slot("QA/QC"):
                        modified = deps.qaqc_modified(plot["url"])
                    if modified:
                        return {"refdes": refdes, "status": None, "evidenceMode": "data_age", "basis": "qaqc",
                                "latestAt": modified, "source": "RCA QA/QC", "sourceUrl": plot["url"]}
            except errors.UpstreamError:
                return None
        return None

    routes_data.register(app, settings, deps, cache, limiter)
    return app
