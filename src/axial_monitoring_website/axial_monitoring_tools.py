"""Bounded public tools for OSU's live Axial monitoring pages.

This module intentionally fetches only an allow-listed set of publisher URLs.
Its image products are volatile monitoring displays, not corpus figures or
quality-controlled data.  Use OOI M2M for analysis-ready sensor data.
"""

from __future__ import annotations

import base64
import html
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable


BASE_URL = "https://axial.ceoas.oregonstate.edu/"
STATUS_URL = BASE_URL + "status/"
STREAMS = {
    "central_caldera": {"instrument": "BOTPT-A301-MJ03F", "site": "Central Caldera", "page": "mj03f.html", "prefix": "MJ03F"},
    "eastern_caldera": {"instrument": "BOTPT-A302-MJ03E", "site": "Eastern Caldera", "page": "mj03e.html", "prefix": "MJ03E"},
    "international_district": {"instrument": "BOTPT-A303-MJ03D", "site": "International District", "page": "mj03d.html", "prefix": "MJ03D"},
    "ashes": {"instrument": "BOTPT-A304-MJ03B", "site": "ASHES Hydrothermal Field", "page": "mj03b.html", "prefix": "MJ03B"},
}
PLOTS = {
    "bpr_7_days": "{prefix}7DaysDET.png",
    "bpr_6_months": "{prefix}Last6MonthsDET.png",
    "bpr_since_2015": "{prefix}25Apr2015onDET.png",
    "bpr_full_record": "{prefix}-AllDET.png",
    "lily_7_days": "{prefix}7DaysLILY.png",
    "lily_6_months": "{prefix}Last6MonthsLILY.png",
    "lily_since_2015": "{prefix}25Apr2015onLILY.png",
    "lily_full_record": "{prefix}AllLILY.png",
}
CAUTION = "Publisher labels these as pre-commissioned OOI data not through QA checks; this is a live visual product, not analysis-ready raw data."


def _error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", value))).strip()


class AxialMonitoringToolkit:
    def __init__(self, fetcher: Callable[[str], bytes] | None = None, now_fn: Callable[[], datetime] | None = None) -> None:
        self._fetcher = fetcher or self._http_fetch
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _http_fetch(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "RCA-Atlas/1.0 (public monitoring retrieval)"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def list_streams(self) -> dict:
        return {"ok": True, "streams": [{"stream": key, **value, "live_plot_page": BASE_URL + value["page"]} for key, value in STREAMS.items()], "raw_data_guidance": "For analysis or numerical values, use the OOI M2M tool rather than interpreting the plot image.", "caution": CAUTION}

    def get_plot(self, stream: str, product: str = "bpr_7_days") -> dict:
        stream_info = STREAMS.get(stream)
        template = PLOTS.get(product)
        if stream_info is None:
            return _error("unknown_stream", "Choose one of the published BOTPT streams.", available=sorted(STREAMS))
        if template is None:
            return _error("unknown_product", "Choose an allow-listed live plot product.", available=sorted(PLOTS))
        url = BASE_URL + "graphs/" + template.format(prefix=stream_info["prefix"])
        try:
            payload = self._fetcher(url)
        except Exception as exc:
            return _error("axial_monitoring_unavailable", str(exc), source_url=url)
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return _error("unexpected_response", "Publisher response was not a PNG plot.", source_url=url)
        return {"ok": True, "stream": stream, "instrument": stream_info["instrument"], "site": stream_info["site"], "product": product, "source_url": url, "retrieved_at": self._now_fn().astimezone(timezone.utc).isoformat(), "evidence_mode": "live", "byte_size": len(payload), "caution": CAUTION, "_mcp_image": {"mimeType": "image/png", "data": base64.b64encode(payload).decode("ascii")}}

    def current_status(self) -> dict:
        try:
            text = _plain_text(self._fetcher(STATUS_URL).decode("utf-8", errors="replace"))
        except Exception as exc:
            return _error("axial_monitoring_unavailable", str(exc), source_url=STATUS_URL)
        match = re.search(r"Has Axial Seamount erupted yet\?\s*(Yes|No)[,! .]*(?:not yet)?", text, re.I)
        status = match.group(1).casefold() if match else "unparsed"
        return {"ok": True, "eruption_status": status, "source_url": STATUS_URL, "retrieved_at": self._now_fn().astimezone(timezone.utc).isoformat(), "evidence_mode": "live", "caution": CAUTION, "interpretation": "This reports the publisher's current status-page text; it is not an independent eruption determination."}


TOOL_SCHEMAS = [
    {"name": "axial_monitoring_list_streams", "description": "List OSU's public live Axial BOTPT monitoring streams and their OOI data guidance.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "axial_monitoring_get_plot", "description": "Fetch one current public BOTPT pressure or LILY tilt plot from the OSU Axial monitoring site. Use OOI M2M for numerical analysis.", "inputSchema": {"type": "object", "required": ["stream"], "properties": {"stream": {"type": "string", "enum": sorted(STREAMS)}, "product": {"type": "string", "enum": sorted(PLOTS), "default": "bpr_7_days"}}}},
    {"name": "axial_monitoring_current_status", "description": "Read the current public OSU Axial eruption-status page, with retrieval timestamp and pre-QA caveat.", "inputSchema": {"type": "object", "properties": {}}},
]


def dispatch(toolkit: AxialMonitoringToolkit, name: str, arguments: dict) -> dict:
    handlers = {"axial_monitoring_list_streams": toolkit.list_streams, "axial_monitoring_get_plot": toolkit.get_plot, "axial_monitoring_current_status": toolkit.current_status}
    if name not in handlers:
        return _error("unknown_tool", name)
    try:
        return handlers[name](**arguments)
    except TypeError as exc:
        return _error("invalid_arguments", str(exc), tool=name)
