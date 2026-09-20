#!/usr/bin/env python3
"""Bounded public EarthScope FDSN tools for future agent use.

The adapter targets the current service.earthscope.org endpoints.  It retrieves
open station metadata and waveform data without credentials, limits waveform
requests to one station and (by default) 24 hours, and stores downloaded files
under runtime_data/EarthScope rather than the Graph-RAG corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


UTC = timezone.utc
SERVICE_ROOT = "https://service.earthscope.org/fdsnws"
STATION_ENDPOINT = f"{SERVICE_ROOT}/station/1/query"
DATASELECT_ENDPOINT = f"{SERVICE_ROOT}/dataselect/1/query"
AVAILABILITY_ENDPOINT = f"{SERVICE_ROOT}/availability/1/query"
OFFICIAL_SOURCES = [
    {
        "name": "EarthScope FDSN web services",
        "url": "https://service.earthscope.org/fdsnws/",
        "role": "official service index for station metadata and waveform data",
    },
    {
        "name": "EarthScope dataselect documentation",
        "url": "https://service.earthscope.org/fdsnws/dataselect/docs/1/help/",
        "role": "official query syntax, MiniSEED delivery, redirect, request grouping, restricted-data, and real-time guidance",
    },
    {
        "name": "EarthScope station documentation",
        "url": "https://service.earthscope.org/fdsnws/station/1/",
        "role": "official StationXML and text metadata query interface",
    },
    {
        "name": "EarthScope availability transition notice",
        "url": "https://www.earthscope.org/news/fdsnws-availability-web-service-outage-and-changes/",
        "role": "official notice that the legacy availability service may return HTTP 410 during the 2026 cloud transition",
    },
]

CODE_RE = re.compile(r"^[A-Za-z0-9*?,_-]{1,120}$")
EXACT_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
CHANNEL_RE = re.compile(r"^[A-Za-z0-9*?,_-]{1,160}$")
LOCATION_RE = re.compile(r"^(?:--|[A-Za-z0-9*?,_-]{0,120})$")
REQUEST_ID_RE = re.compile(r"^earthscope-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


class EarthScopeError(RuntimeError):
    pass


class EarthScopeFDSNToolkit:
    def __init__(self, runtime_root: str | Path | None = None,
                 http_get: Callable[..., tuple[int, dict[str, str], bytes, str]] | None = None) -> None:
        project = Path(__file__).resolve().parents[2]
        self.runtime_root = Path(runtime_root or os.getenv("EARTHSCOPE_RUNTIME_ROOT", project / "runtime_data" / "EarthScope")).resolve()
        self.max_request_hours = max(0.01, float(os.getenv("EARTHSCOPE_MAX_REQUEST_HOURS", "24")))
        self.max_download_bytes = max(1, int(os.getenv("EARTHSCOPE_MAX_DOWNLOAD_BYTES", str(512 * 1024 ** 2))))
        self.timeout_seconds = max(1, int(os.getenv("EARTHSCOPE_TIMEOUT_SECONDS", "120")))
        self._http_get_override = http_get

    @staticmethod
    def _approved_url(url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        approved = host == "service.earthscope.org" or host.endswith(".earthscope.org") or host == "service.iris.edu"
        if parsed.scheme != "https" or not approved or parsed.username or parsed.password:
            raise ValueError("URL is outside the approved EarthScope FDSN HTTPS hosts")
        return url

    @staticmethod
    def _code(value: str, label: str, *, exact: bool = False) -> str:
        token = str(value).strip()
        pattern = EXACT_RE if exact else CODE_RE
        if not pattern.fullmatch(token):
            raise ValueError(f"Invalid {label}")
        return token.upper()

    @staticmethod
    def _channel(value: str) -> str:
        token = str(value).strip().upper()
        if not CHANNEL_RE.fullmatch(token):
            raise ValueError("Invalid channel selector")
        return token

    @staticmethod
    def _location(value: str | None) -> str:
        token = "--" if value is None or value == "" else str(value).strip().upper()
        if not LOCATION_RE.fullmatch(token):
            raise ValueError("Invalid location selector")
        return token

    @staticmethod
    def _datetime(value: str, label: str) -> datetime:
        token = str(value).strip().replace(" ", "T")
        if token.endswith("Z"):
            token = token[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(token)
        except ValueError as exc:
            raise ValueError(f"Invalid {label}; use ISO-8601 UTC") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _api_time(value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _http(self, url: str, params: dict[str, Any], max_bytes: int) -> tuple[int, dict[str, str], bytes, str]:
        self._approved_url(url)
        if self._http_get_override:
            return self._http_get_override(url=url, params=params, max_bytes=max_bytes)
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({key: str(value) for key, value in params.items()})
        final_url = urlunparse(parsed._replace(query=urlencode(query)))
        request = Request(final_url, headers={"User-Agent": "RCN-Agent-EarthScope-FDSN/1.0", "Accept": "*/*"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final = response.geturl()
                self._approved_url(final)
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise EarthScopeError(f"Response exceeds {max_bytes} byte limit")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise EarthScopeError(f"Response exceeds {max_bytes} byte limit")
                return int(response.status), dict(response.headers.items()), body, final
        except HTTPError as exc:
            body = exc.read(min(max_bytes, 256 * 1024))
            return int(exc.code), dict(exc.headers.items()) if exc.headers else {}, body, exc.geturl()
        except URLError as exc:
            raise EarthScopeError(f"EarthScope request failed: {exc.reason}") from exc

    def status(self) -> dict:
        return {
            "ok": True,
            "public_data_credentials_required": False,
            "restricted_data_supported": False,
            "service_root": SERVICE_ROOT,
            "runtime_root": str(self.runtime_root),
            "limits": {"max_request_hours": self.max_request_hours, "max_download_bytes": self.max_download_bytes},
            "real_time_guidance": "Use EarthScope SeedLink for continuous real-time streaming; these FDSN tools are for bounded historical or near-real-time requests.",
            "availability_guidance": "The legacy availability service may return HTTP 410 during EarthScope's 2026 cloud transition; waveform and station queries do not depend on it.",
            "official_sources": OFFICIAL_SOURCES,
        }

    def _selection(self, network: str, station: str, location: str | None, channel: str,
                   begin: str, end: str, *, exact_station: bool) -> dict:
        net = self._code(network, "network", exact=exact_station)
        sta = self._code(station, "station", exact=exact_station)
        loc = self._location(location)
        cha = self._channel(channel)
        start, stop = self._datetime(begin, "begin"), self._datetime(end, "end")
        if stop <= start:
            raise ValueError("end must be after begin")
        return {
            "network": net, "station": sta, "location": loc, "channel": cha,
            "starttime": self._api_time(start), "endtime": self._api_time(stop),
            "duration_hours": (stop - start).total_seconds() / 3600,
        }

    def plan_waveform(self, network: str, station: str, channel: str, begin: str, end: str,
                      location: str | None = "--") -> dict:
        selection = self._selection(network, station, location, channel, begin, end, exact_station=True)
        if selection["duration_hours"] > self.max_request_hours:
            raise ValueError(f"Waveform request spans {selection['duration_hours']:.3f} hours; configured maximum is {self.max_request_hours}")
        params = {
            "net": selection["network"], "sta": selection["station"],
            "loc": selection["location"], "cha": selection["channel"],
            "starttime": selection["starttime"], "endtime": selection["endtime"],
            "format": "miniseed", "nodata": 404,
        }
        return {"ok": True, "live_request_executed": False, "endpoint": DATASELECT_ENDPOINT,
                "parameters": params, **selection,
                "guidance": "One exact station and at most 24 hours by default, following EarthScope service guidance."}

    @staticmethod
    def _parse_pipe_text(body: bytes, limit: int) -> tuple[list[dict], bool]:
        lines = body.decode("utf-8", errors="replace").splitlines()
        header: list[str] | None = None
        rows: list[dict] = []
        truncated = False
        for line in lines:
            if not line.strip():
                continue
            if line.startswith("#"):
                fields = line.lstrip("#").split("|")
                if len(fields) > 1:
                    header = [field.strip() for field in fields]
                continue
            values = line.split("|")
            row = dict(zip(header, values)) if header else {"raw": line}
            rows.append(row)
            if len(rows) >= limit:
                truncated = len(lines) > len(rows)
                break
        return rows, truncated

    def search_channels(self, network: str, station: str = "*", location: str | None = "*",
                        channel: str = "*", begin: str | None = None, end: str | None = None,
                        level: str = "channel", limit: int = 500) -> dict:
        if level not in {"network", "station", "channel"}:
            raise ValueError("level must be network, station, or channel")
        params: dict[str, Any] = {
            "net": self._code(network, "network"), "sta": self._code(station, "station"),
            "loc": self._location(location), "cha": self._channel(channel),
            "level": level, "format": "text", "nodata": 404,
        }
        if begin:
            params["starttime"] = self._api_time(self._datetime(begin, "begin"))
        if end:
            params["endtime"] = self._api_time(self._datetime(end, "end"))
        if begin and end and self._datetime(end, "end") <= self._datetime(begin, "begin"):
            raise ValueError("end must be after begin")
        status, headers, body, final = self._http(STATION_ENDPOINT, params, 20 * 1024 * 1024)
        if status == 404:
            return {"ok": True, "count": 0, "records": [], "nodata": True, "retrieved_at_utc": _now()}
        if status < 200 or status >= 300:
            return _error("earthscope_http_error", f"EarthScope station service returned HTTP {status}", endpoint=final)
        limit = max(1, min(int(limit), 5000))
        records, truncated = self._parse_pipe_text(body, limit)
        return {"ok": True, "count": len(records), "records": records, "truncated": truncated,
                "content_type": headers.get("Content-Type"), "source_url": final, "retrieved_at_utc": _now()}

    def _request_dir(self, request_id: str) -> Path:
        if not REQUEST_ID_RE.fullmatch(request_id):
            raise ValueError("Invalid EarthScope request ID")
        root = (self.runtime_root / "requests").resolve()
        target = (root / request_id).resolve()
        if target.parent != root:
            raise ValueError("Request path escaped runtime root")
        return target

    def _new_request_id(self) -> str:
        return "earthscope-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]

    def _persist(self, request_id: str, filename: str, body: bytes, metadata: dict) -> dict:
        directory = self._request_dir(request_id)
        directory.mkdir(parents=True, exist_ok=True)
        target = (directory / filename).resolve()
        if target.parent != directory:
            raise ValueError("Output path escaped request directory")
        target.write_bytes(body)
        record = {
            "schema_version": "1.0", "local_request_id": request_id,
            "retrieved_at_utc": _now(), "file": str(target), "filename": filename,
            "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest(), **metadata,
        }
        fd, tmp_name = tempfile.mkstemp(prefix="manifest-", suffix=".json", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, indent=2, sort_keys=True); stream.write("\n")
            os.replace(tmp_name, directory / "manifest.json")
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return record

    def download_waveform(self, network: str, station: str, channel: str, begin: str, end: str,
                          location: str | None = "--") -> dict:
        plan = self.plan_waveform(network, station, channel, begin, end, location)
        status, headers, body, final = self._http(DATASELECT_ENDPOINT, plan["parameters"], self.max_download_bytes)
        if status == 404:
            return _error("no_data", "EarthScope returned no waveform data for the requested selection", http_status=404)
        if status < 200 or status >= 300:
            return _error("earthscope_http_error", f"EarthScope dataselect returned HTTP {status}", endpoint=final)
        request_id = self._new_request_id()
        stamp = plan["starttime"].replace("-", "").replace(":", "").replace(".000Z", "Z")
        filename_channel = re.sub(r"[^A-Z0-9_-]+", "_", plan["channel"]).strip("_") or "channels"
        filename_location = re.sub(r"[^A-Z0-9_-]+", "_", plan["location"]).strip("_") or "blank"
        filename = f"{plan['network']}.{plan['station']}.{filename_location}.{filename_channel}.{stamp}.mseed"
        record = self._persist(request_id, filename, body, {
            "kind": "MiniSEED waveform", "source_url": final,
            "content_type": headers.get("Content-Type"),
            "selection": {key: plan[key] for key in ("network", "station", "location", "channel", "starttime", "endtime", "duration_hours")},
        })
        return {"ok": True, **record}

    def download_stationxml(self, network: str, station: str, channel: str = "*",
                            location: str | None = "*", begin: str | None = None,
                            end: str | None = None, level: str = "response") -> dict:
        net, sta = self._code(network, "network", exact=True), self._code(station, "station", exact=True)
        if level not in {"station", "channel", "response"}:
            raise ValueError("level must be station, channel, or response")
        params: dict[str, Any] = {"net": net, "sta": sta, "loc": self._location(location),
                                  "cha": self._channel(channel), "level": level,
                                  "format": "xml", "nodata": 404}
        if begin:
            params["starttime"] = self._api_time(self._datetime(begin, "begin"))
        if end:
            params["endtime"] = self._api_time(self._datetime(end, "end"))
        if begin and end and self._datetime(end, "end") <= self._datetime(begin, "begin"):
            raise ValueError("end must be after begin")
        status, headers, body, final = self._http(STATION_ENDPOINT, params, 100 * 1024 * 1024)
        if status == 404:
            return _error("no_metadata", "EarthScope returned no station metadata for the requested selection", http_status=404)
        if status < 200 or status >= 300:
            return _error("earthscope_http_error", f"EarthScope station service returned HTTP {status}", endpoint=final)
        request_id = self._new_request_id()
        filename = f"{net}.{sta}.station.xml"
        record = self._persist(request_id, filename, body, {"kind": "FDSN StationXML", "source_url": final,
                               "content_type": headers.get("Content-Type"), "selection": params})
        return {"ok": True, **record}

    def query_availability(self, network: str, station: str, channel: str, begin: str, end: str,
                           location: str | None = "*", limit: int = 1000) -> dict:
        selection = self._selection(network, station, location, channel, begin, end, exact_station=False)
        params = {"net": selection["network"], "sta": selection["station"], "loc": selection["location"],
                  "cha": selection["channel"], "starttime": selection["starttime"],
                  "endtime": selection["endtime"], "format": "text", "nodata": 404}
        status, _, body, final = self._http(AVAILABILITY_ENDPOINT, params, 20 * 1024 * 1024)
        if status == 410:
            return _error("service_unavailable", "EarthScope availability service returned HTTP 410 during its cloud transition; this does not prevent station or waveform requests", http_status=410, endpoint=final)
        if status == 404:
            return {"ok": True, "count": 0, "records": [], "nodata": True, "retrieved_at_utc": _now()}
        if status < 200 or status >= 300:
            return _error("earthscope_http_error", f"EarthScope availability service returned HTTP {status}", endpoint=final)
        limit = max(1, min(int(limit), 5000))
        records, truncated = self._parse_pipe_text(body, limit)
        return {"ok": True, "count": len(records), "records": records, "truncated": truncated,
                "source_url": final, "retrieved_at_utc": _now()}


EARTHSCOPE_TOOL_SCHEMAS = [
    {"name": "earthscope_fdsn_status", "description": "Describe the configured public EarthScope FDSN endpoints, local runtime storage, request limits, and current availability-service caveat without making a network call.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "earthscope_search_channels", "description": "Search current EarthScope station, station-epoch, or channel metadata as bounded structured text records.", "inputSchema": {"type": "object", "required": ["network"], "properties": {"network": {"type": "string"}, "station": {"type": "string", "default": "*"}, "location": {"type": "string", "default": "*"}, "channel": {"type": "string", "default": "*"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}, "level": {"type": "string", "enum": ["network", "station", "channel"], "default": "channel"}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 500}}}},
    {"name": "earthscope_plan_waveform", "description": "Validate and preview a public EarthScope MiniSEED request for one exact station and a bounded time interval without making a network call.", "inputSchema": {"type": "object", "required": ["network", "station", "channel", "begin", "end"], "properties": {"network": {"type": "string"}, "station": {"type": "string"}, "location": {"type": "string", "default": "--"}, "channel": {"type": "string"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}}}},
    {"name": "earthscope_download_waveform", "description": "Download one bounded public EarthScope waveform selection as MiniSEED into runtime_data/EarthScope, with a manifest, byte count, source URL, and SHA-256.", "inputSchema": {"type": "object", "required": ["network", "station", "channel", "begin", "end"], "properties": {"network": {"type": "string"}, "station": {"type": "string"}, "location": {"type": "string", "default": "--"}, "channel": {"type": "string"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}}}},
    {"name": "earthscope_download_stationxml", "description": "Download current public FDSN StationXML for one exact EarthScope network and station into runtime storage with source and hash provenance.", "inputSchema": {"type": "object", "required": ["network", "station"], "properties": {"network": {"type": "string"}, "station": {"type": "string"}, "location": {"type": "string", "default": "*"}, "channel": {"type": "string", "default": "*"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}, "level": {"type": "string", "enum": ["station", "channel", "response"], "default": "response"}}}},
    {"name": "earthscope_query_availability", "description": "Query EarthScope coverage metadata when its availability service is operating; return a clear HTTP 410 transition status otherwise.", "inputSchema": {"type": "object", "required": ["network", "station", "channel", "begin", "end"], "properties": {"network": {"type": "string"}, "station": {"type": "string"}, "location": {"type": "string", "default": "*"}, "channel": {"type": "string"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 1000}}}},
]


def dispatch_earthscope(toolkit: EarthScopeFDSNToolkit, name: str, arguments: dict) -> dict:
    calls = {
        "earthscope_fdsn_status": lambda: toolkit.status(),
        "earthscope_search_channels": lambda: toolkit.search_channels(**arguments),
        "earthscope_plan_waveform": lambda: toolkit.plan_waveform(**arguments),
        "earthscope_download_waveform": lambda: toolkit.download_waveform(**arguments),
        "earthscope_download_stationxml": lambda: toolkit.download_stationxml(**arguments),
        "earthscope_query_availability": lambda: toolkit.query_availability(**arguments),
    }
    if name not in calls:
        return _error("unknown_tool", name)
    try:
        return calls[name]()
    except Exception as exc:
        return _error(type(exc).__name__, str(exc))
