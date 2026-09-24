"""Data routes: series, plots, waveform, files, chat."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import Query
from fastapi.responses import JSONResponse

from . import errors, thinning
from .app_support import call_toolkit

VAR_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,120}")
TTL = {"variables": 3600, "series": 300, "plots": 1800, "waveform": 300, "files": 300}


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
