"""Data routes: series, plots, waveform, files, chat."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from coszo_hub_tools.pi_portal_agent_tools import PI_DATASETS

from . import errors, seismic, thinning
from .app_support import call_toolkit

VAR_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,120}")
TTL = {"variables": 3600, "series": 300, "plots": 1800, "waveform": 300, "files": 300}
MAX_FILE_ENTRIES = 200


class ChatBody(BaseModel):
    # Module level, not inside register(): with `from __future__ import annotations` FastAPI resolves the
    # annotation from module globals, and a function-local model would be read as a query parameter.
    question: str = Field(min_length=2, max_length=1000)


def _bad(message: str) -> JSONResponse:
    return JSONResponse(errors.body("atlas", message), status_code=422)


def _missing(source: str, message: str) -> JSONResponse:
    return JSONResponse(errors.body(source, message), status_code=404)


def _parse_time(value: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _toolkit_endpoint_id(instrument_key: str, url: str) -> str:
    """The bundle carries corpus endpoint ids; PIPortalToolkit.browse wants its own registry id. Match on the URL."""
    for endpoint in PI_DATASETS.get(instrument_key, {}).get("endpoints", []):
        if endpoint["url"] == url:
            return endpoint["endpoint_id"]
    raise errors.UpstreamError("PI portal", "this endpoint is not in the PI portal registry")


CHANNEL_RE = re.compile(r"[A-Z0-9]{3}")
UPSTREAM_TRUNCATED = ("This folder has more than 5,000 entries; the newest may be missing. "
                      "Open the folder on the PI portal to see everything.")


def _entry(raw: dict) -> dict:
    """The toolkit's listing entry as the website reads it. `path` is relative to the endpoint root."""
    return {"name": raw.get("name"), "kind": raw.get("kind"), "path": raw.get("relative_path"),
            "url": raw.get("url"), "date": raw.get("observation_date") or None}


def _newest_first(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: (e["date"] or "", e["path"] or ""), reverse=True)


def register(app, settings, deps, cache, limiter) -> None:
    @app.get("/series/{refdes}/variables")
    def series_variables(refdes: str):
        ds = deps.index.erddap_dataset(refdes)
        if not ds:
            return _missing("atlas", "no public data feed for this sensor")

        def fetch():
            with limiter.slot("ERDDAP"):
                return deps.erddap.variables(ds)
        return cache.get_or_set(f"vars:{ds}", TTL["variables"], fetch)

    @app.get("/series/{refdes}")
    def series(refdes: str, var: str = Query(...), start: str = Query(...), end: str = Query(...)):
        ds = deps.index.erddap_dataset(refdes)
        if not ds:
            return _missing("atlas", "no public data feed for this sensor")
        if not VAR_RE.fullmatch(var):
            return _bad("invalid variable name")
        t0, t1 = _parse_time(start), _parse_time(end)
        if not t0 or not t1 or t1 <= t0:
            return _bad("start and end must be ISO times with end after start")
        if t1 - t0 > timedelta(days=settings.max_series_days):
            return _bad(f"ranges are limited to {settings.max_series_days} days per request")

        def fetch():
            with limiter.slot("ERDDAP"):
                raw = deps.erddap.series(ds, var, t0, t1)
            times, values = thinning.minmax(raw["times"], raw["values"], settings.max_points)
            return {"refdes": refdes, "var": var, "units": raw["units"],
                    "points": [[t, v] for t, v in zip(times, values)], "rawCount": len(raw["times"]),
                    "downloadUrl": deps.erddap.csv_url(ds, var, t0, t1),
                    "message": None if raw["times"] else "No readings in this range."}
        return cache.get_or_set(f"series:{ds}:{var}:{t0.isoformat()}:{t1.isoformat()}", TTL["series"], fetch)

    @app.get("/plots/{refdes}")
    def plots(refdes: str):
        if not deps.index.has_refdes(refdes):
            return _missing("atlas", "unknown sensor")

        def fetch():
            with limiter.slot("QA/QC"):
                res = call_toolkit("QA/QC", lambda: deps.qaqc.search_plots(reference_designator=refdes, limit=200))
            return {"refdes": refdes, "plots": [
                {"variable": p["variable"], "timeSpan": p["time_span"], "overlay": p["overlay"],
                 "dataRange": p["data_range"], "depth": p.get("depth_or_profile", ""), "url": p["url"]}
                for p in res.get("plots", []) if p.get("reference_designator") == refdes]}
        return cache.get_or_set(f"plots:{refdes}", TTL["plots"], fetch)

    @app.get("/files/{instrument_key}")
    def files(instrument_key: str, path: str = "", endpoint: str | None = None):
        if not deps.index.has_pi(instrument_key):
            return _missing("atlas", "unknown PI instrument")
        toolkit_endpoint = None
        if endpoint is not None:
            url = deps.index.pi_endpoint_url(instrument_key, endpoint)
            if url is None:
                return _missing("atlas", "unknown endpoint for this PI instrument")
            toolkit_endpoint = _toolkit_endpoint_id(instrument_key, url)
        elif deps.index.pi_endpoint_count(instrument_key) > 1:
            return _bad("this instrument has several data endpoints; pass endpoint")

        def fetch():
            with limiter.slot("PI portal"):
                res = call_toolkit("PI portal", lambda: deps.pi.browse(instrument_key, toolkit_endpoint, path, 5000))
            entries = _newest_first([_entry(e) for e in res.get("entries", [])])
            # The toolkit keeps the first 5000 entries in listing order, before this sort; say so rather than
            # pretend the list is the newest.
            upstream_truncated = bool(res.get("truncated"))
            return {"instrumentKey": instrument_key, "endpointLabel": res.get("endpoint_label"),
                    "path": res.get("relative_path", path), "sourceUrl": res.get("source_url"),
                    "entries": entries[:MAX_FILE_ENTRIES],
                    "truncated": upstream_truncated or len(entries) > MAX_FILE_ENTRIES,
                    "message": UPSTREAM_TRUNCATED if upstream_truncated else None}
        return cache.get_or_set(f"files:{instrument_key}:{endpoint}:{path}", TTL["files"], fetch)

    @app.get("/waveform/{station_id}")
    def waveform(station_id: str, minutes: int = 10, channel: str | None = None):
        m = re.fullmatch(r"([A-Z0-9]{1,2})\.([A-Z0-9]{1,5})", station_id)
        if not m:
            return _bad("station must look like NET.STA")
        net, sta = m.groups()
        known = deps.index.station(net, sta)
        if known is None:
            return _missing("atlas", "unknown seismic station")
        if not 1 <= minutes <= settings.max_waveform_minutes:
            return _bad(f"minutes must be between 1 and {settings.max_waveform_minutes}")
        if channel is not None and not CHANNEL_RE.fullmatch(channel):
            return _bad("channel must be three letters or digits, like HHZ")   # the toolkit would accept wildcards
        cha = channel or known.get("channel") or "HHZ"
        end = deps.now().replace(second=0, microsecond=0) - timedelta(minutes=2)
        begin = end - timedelta(minutes=minutes)
        b, e = begin.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")

        def fetch():
            with limiter.slot("EarthScope"):
                try:
                    res = call_toolkit("EarthScope", lambda: deps.earthscope.download_waveform(net, sta, cha, b, e, "--"))
                except errors.UpstreamError as exc:
                    if "no waveform data" in exc.message.lower():
                        return {"station": station_id, "channel": cha, "rate": None, "points": [], "rawCount": 0,
                                "sourceUrl": None, "message": "No recording in this window."}
                    raise
            file = Path(res["file"])
            try:
                d = seismic.decode(file)
            finally:
                seismic.discard_request_dir(file, deps.earthscope_root)
            times = [d["startMs"] + i * 1000.0 / d["rate"] for i in range(len(d["samples"]))] if d["rate"] else []
            tt, vv = thinning.minmax(times, d["samples"], settings.max_points)
            return {"station": station_id, "channel": cha, "rate": d["rate"],
                    "points": [[int(t), v] for t, v in zip(tt, vv)], "rawCount": len(d["samples"]),
                    "sourceUrl": res.get("source_url"), "message": None if d["samples"] else "No recording in this window."}
        return cache.get_or_set(f"wave:{station_id}:{cha}:{b}:{e}", TTL["waveform"], fetch)

    @app.post("/chat")
    def chat(body: ChatBody):
        question = body.question.strip()
        if len(question) < 2:
            return _bad("ask a question")
        with limiter.slot("Atlas chat"):
            return deps.chat(question)
