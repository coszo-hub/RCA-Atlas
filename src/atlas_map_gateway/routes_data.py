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

# ERDDAP names run long: OOI fluorometers' CDOM variable is 158 characters.
VAR_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,254}")
TTL = {"variables": 3600, "series": 300, "plots": 1800, "waveform": 300, "files": 300}
MAX_FILE_ENTRIES = 200
SPAN_ORDER = ["day", "week", "month", "year", "deploy"]   # QA/QC plot spans, shortest first
# EarthScope's archive can trail real time by over an hour (83 minutes for every OO station on 2026-10-21), so an
# empty recent window is usually latency, not a silent station. Probe this far back, in minutes, for the newest data.
ARCHIVE_LAG_PROBES = (15, 30, 60, 90, 120, 180, 240, 360, 480, 720, 1080, 1440)
# EarthScope can stall one sample rate while others flow: on 2026-10-21 the OO network's 200 and 40 samples/s
# channels (HHZ, EHZ, HDH, BHZ, SHZ) stopped at 16:05 UTC while MHZ (8/s) and LHZ, LDH (1/s) stayed current. A
# channel this far behind gives way to a current lower-rate one of the same sensor and component.
STALE_MINUTES = 60
LOWER_BANDS = {"H": "BML", "E": "SML", "B": "ML", "S": "ML", "M": "L"}   # SEED band codes, fastest first


# Waveform filters the map offers, in Hz. 3-20: small local earthquakes, above the ocean microseism (about 0.1-1
# Hz); needs 50 samples/s. 1-3: their low-frequency end, which 8 samples/s MHZ can hold; on 2026-10-21 it showed
# 10 of 28 events detected at 3-20 Hz on HHZ, against 4 in the raw MHZ trace.
BANDPASS_PRESETS = {"3-20": (3.0, 20.0), "1-3": (1.0, 3.0)}


def lower_rate_channels(channel: str) -> list[str]:
    """HHZ -> BHZ, MHZ, LHZ; EHZ -> SHZ, MHZ, LHZ; HDH -> BDH, MDH, LDH."""
    return [band + channel[1:] for band in LOWER_BANDS.get(channel[:1], "")]


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
            latest = None
            if not raw["times"]:
                # An empty window often means this measurement stopped before the dataset's other columns did,
                # so say where its newest reading is and let the chart move there.
                def newest():
                    with limiter.slot("ERDDAP"):
                        return deps.erddap.latest(ds, var)
                latest = cache.get_or_set(f"latest:{ds}:{var}", TTL["series"], newest)
            times, values = thinning.minmax(raw["times"], raw["values"], settings.max_points)
            return {"refdes": refdes, "var": var, "units": raw["units"],
                    "points": [[t, v] for t, v in zip(times, values)], "rawCount": len(raw["times"]),
                    "downloadUrl": deps.erddap.csv_url(ds, var, t0, t1), "latest": latest,
                    "message": None if raw["times"] else "No readings in this range."}
        return cache.get_or_set(f"series:{ds}:{var}:{t0.isoformat()}:{t1.isoformat()}", TTL["series"], fetch)

    @app.get("/plots/{refdes}")
    def plots(refdes: str, variable: str | None = None, span: str | None = None):
        """One instrument's QA/QC plots for one variable and time span, with the variables and spans it has.

        All of its plots are read (an ADCP has 735, a profiler CTD over 4,000), not the first 200, which hid most
        variables; only the chosen variable and span are returned. A seismometer's plots are filed under its OOI
        OBS reference designator, which only its QA/QC route names."""
        if not (deps.index.has_refdes(refdes) or deps.index.has_qaqc(refdes)):
            return _missing("atlas", "unknown sensor")
        if variable is not None and not VAR_RE.fullmatch(variable):
            return _bad("invalid variable name")
        if span is not None and not re.fullmatch(r"[a-z]{1,12}", span):
            return _bad("invalid time span")

        def fetch():
            with limiter.slot("QA/QC"):
                rows = call_toolkit("QA/QC", lambda: {"ok": True, "plots": deps.qaqc.plots_for(refdes)})["plots"]
            return [{"variable": p["variable"], "timeSpan": p["time_span"], "overlay": p["overlay"],
                     "dataRange": p["data_range"], "depth": p.get("depth_or_profile", ""), "url": p["url"]} for p in rows]
        everything = cache.get_or_set(f"plots:{refdes}", TTL["plots"], fetch)
        variables = sorted({p["variable"] for p in everything})
        v = variable if variable in variables else (variables[0] if variables else None)
        spans = sorted({p["timeSpan"] for p in everything if p["variable"] == v},
                       key=lambda x: (SPAN_ORDER.index(x) if x in SPAN_ORDER else len(SPAN_ORDER), x))
        sp = span if span in spans else ("day" if "day" in spans else (spans[0] if spans else None))
        chosen = [p for p in everything if p["variable"] == v and p["timeSpan"] == sp]
        chosen.sort(key=lambda p: (p["depth"], p["overlay"] != "none", p["overlay"], p["dataRange"]))
        return {"refdes": refdes, "variables": variables, "variable": v, "spans": spans, "span": sp,
                "plots": chosen, "total": len(everything)}

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
    def waveform(station_id: str, minutes: int = 10, channel: str | None = None, bandpass: str | None = None):
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
        # Named presets only: each band is its own cached download and filter run, so arbitrary corners would let a
        # caller bypass the cache and multiply EarthScope requests.
        band = None
        if bandpass is not None:
            band = BANDPASS_PRESETS.get(bandpass)
            if band is None:
                return _bad(f"bandpass must be one of: {', '.join(BANDPASS_PRESETS)}")
        cha = channel or known.get("channel") or "HHZ"
        end = deps.now().replace(second=0, microsecond=0) - timedelta(minutes=2)

        def download(window_end: datetime, window_minutes: int, ch: str = cha, band: tuple | None = None) -> dict | None:
            b = (window_end - timedelta(minutes=window_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
            e = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

            def fetch():
                with limiter.slot("EarthScope"):
                    try:
                        res = call_toolkit("EarthScope", lambda: deps.earthscope.download_waveform(net, sta, ch, b, e, "--"))
                    except errors.UpstreamError as exc:
                        if "no waveform data" in exc.message.lower():
                            return None
                        raise
                file = Path(res["file"])
                try:
                    d = seismic.decode(file)
                finally:
                    seismic.discard_request_dir(file, deps.earthscope_root)
                if not d["samples"] or not d["rate"]:
                    return None
                samples, applied, note = d["samples"], None, None
                if band:
                    # Filtered on the full-rate samples, before thinning. The high corner stays under 80% of Nyquist;
                    # a channel too slow for the band is shown raw and says so, rather than as a misleading filter.
                    # Below 1.5x the low corner, what survives is a sliver, not the band asked for (8 samples/s
                    # would leave 3-3.2 Hz of 3-20 Hz), so that too is shown raw.
                    top = 0.4 * d["rate"]
                    if min(band[1], top) < 1.5 * band[0]:
                        note = (f"A {band[0]:g}–{band[1]:g} Hz bandpass needs {2.5 * band[1]:g} samples/s or more; "
                                f"{ch} has {d['rate']:g}, so this is unfiltered.")
                    else:
                        applied = {"low": band[0], "high": min(band[1], round(top, 2))}
                        samples = seismic.bandpass(samples, d["rate"], applied["low"], applied["high"])
                times = [d["startMs"] + i * 1000.0 / d["rate"] for i in range(len(samples))]
                tt, vv = thinning.minmax(times, samples, settings.max_points)
                return {"rate": d["rate"], "points": [[int(t), round(v, 3) if band else v] for t, v in zip(tt, vv)],
                        "rawCount": len(samples), "endMs": int(times[-1]), "sourceUrl": res.get("source_url"),
                        "bandpass": applied, "filterNote": note}
            key = f"wave:{station_id}:{ch}:{b}:{e}" + (f":{band[0]:g}-{band[1]:g}" if band else "")
            return cache.get_or_set(key, TTL["waveform"], fetch)

        def archive_lag() -> int | None:
            # One-minute probes keep the search cheap; the first window holding data bounds the archive's delay.
            return next((lag for lag in ARCHIVE_LAG_PROBES if download(end - timedelta(minutes=lag), 1)), None)

        data, lag, probed = download(end, minutes, cha, band), 0, False
        # Probing costs up to eight more EarthScope calls, so it runs only for channels the map itself shows for
        # this station; a caller cycling arbitrary channel codes gets one call per window, as before.
        if data is None and cha in known.get("channels", ()):
            probed = True
            lag = cache.get_or_set(f"wave-lag:{station_id}:{cha}:{end.isoformat()}", TTL["waveform"], archive_lag)
            data = download(end - timedelta(minutes=lag), minutes, cha, band) if lag else None
        # A stalled or missing channel gives way to a current lower-rate one, only for channels the map shows. A
        # 1 sample/s record spans minutes, so its newest minute may not have arrived: look back up to the stale limit.
        # One-minute probes find the channel, the outcome is cached like the archive lag, and only then is the
        # requested window downloaded, once: at most 12 small probes per station and minute, never 12 full windows.
        def fallback():
            for alt in lower_rate_channels(cha):
                for back in (0, 15, 30, STALE_MINUTES):
                    if download(end - timedelta(minutes=back), 1, alt):
                        return [alt, back]
            return None

        if probed and (data is None or lag >= STALE_MINUTES):
            found = cache.get_or_set(f"wave-fallback:{station_id}:{cha}:{end.isoformat()}", TTL["waveform"], fallback)
            if found:
                alt, back = found
                alt_data = download(end - timedelta(minutes=back), minutes, alt, band)
                if alt_data:
                    return {"station": station_id, "channel": alt, "requestedChannel": cha, **alt_data,
                            "requestedDelayMinutes": lag if data else None, "message": None}
        if data is None:
            return {"station": station_id, "channel": cha, "rate": None, "points": [], "rawCount": 0, "endMs": None,
                    "sourceUrl": None,
                    "message": f"No recording in the last {ARCHIVE_LAG_PROBES[-1] // 60} hours." if probed else "No recording in this window."}
        return {"station": station_id, "channel": cha, **data, "message": None}

    @app.get("/waveform/{station_id}/health")
    def waveform_health(station_id: str, channel: str | None = None):
        """A narrow, honest station-health signal: can EarthScope serve a recent waveform?

        This is deliberately not an OOI/Nereus operational status.  EarthScope
        station records do not carry an OOI reference designator, but a recent
        non-empty waveform is useful evidence that their public stream works.
        """
        data = waveform(station_id, minutes=1, channel=channel)
        if isinstance(data, JSONResponse):
            return data
        now = deps.now()
        return {"station": data["station"], "channel": data["channel"], "requestedChannel": data.get("requestedChannel"),
                "rate": data.get("rate"), "recording": bool(data["points"]), "checkedAt": now.isoformat(),
                "latestMs": data["endMs"],
                "delayMinutes": round((now.timestamp() * 1000 - data["endMs"]) / 60_000) if data["endMs"] else None,
                "message": data["message"]}

    @app.post("/chat")
    def chat(body: ChatBody):
        question = body.question.strip()
        if len(question) < 2:
            return _bad("ask a question")
        with limiter.slot("Atlas chat"):
            return deps.chat(question)
