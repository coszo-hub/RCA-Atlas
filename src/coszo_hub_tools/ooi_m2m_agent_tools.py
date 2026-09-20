#!/usr/bin/env python3
"""Small, bounded OOI M2M tools intended for agent use.

This is an independent standard-library adapter informed by the public API
workflows demonstrated by OOINet (GPL-3.0) and ooi-harvester (MIT).  It does
not import either project.  Source versions and licenses are recorded in
OOI_M2M_SOURCES.md and preserved under source_material.

Credentials are read only from OOI_USERNAME and OOI_TOKEN.  They are used in
an HTTP Basic Authorization header for ooinet.oceanobservatories.org and are
never written to request state or returned by a tool.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


UTC = timezone.utc
API_ROOT = "https://ooinet.oceanobservatories.org/api/m2m"
SENSOR_ENDPOINT = f"{API_ROOT}/12576/sensor/inv"
VOCAB_ENDPOINT = f"{API_ROOT}/12586/vocab/inv"
DEPLOYMENT_ENDPOINT = f"{API_ROOT}/12587/events/deployment/inv"
SOURCE_REFERENCES = [
    {
        "name": "OOINet",
        "url": "https://github.com/reedan88/OOINet",
        "commit": "2168c825d832cbb913f138b59fd8f2a82dc36dfc",
        "license": "GPL-3.0",
        "role": "reference for compact discovery, vocabulary, deployment, stream, request, catalog, and download workflows",
    },
    {
        "name": "ooi-harvester",
        "url": "https://github.com/ooi-data/ooi-harvester",
        "commit": "f4d4e467624006ea315bc823595e7951de368d1f",
        "license": "MIT",
        "role": "reference for request estimates, asynchronous status, catalog parsing, and durable pipeline state",
    },
]

REFDES_RE = re.compile(r"^[A-Z0-9]{8}-[A-Z0-9]+-[A-Z0-9]{2,3}-[A-Z0-9]+$")
COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
REQUEST_ID_RE = re.compile(r"^ooi-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")
ALLOWED_DOWNLOAD_SUFFIXES = {".nc", ".json", ".txt", ".csv", ".xml"}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


class M2MError(RuntimeError):
    pass


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


class OOIM2MToolkit:
    """Credential-aware OOI discovery, request, status, and download client."""

    def __init__(
        self,
        runtime_root: str | Path | None = None,
        instrument_inventory: str | Path | None = None,
        username: str | None = None,
        token: str | None = None,
        http_get: Callable[..., tuple[int, dict[str, str], bytes, str]] | None = None,
    ) -> None:
        project = Path(__file__).resolve().parents[2]
        self.runtime_root = Path(runtime_root or os.getenv("OOI_M2M_RUNTIME_ROOT", project / "runtime_data" / "OOIM2M")).resolve()
        self.instrument_inventory = Path(instrument_inventory or os.getenv("OOI_INSTRUMENT_INVENTORY", project / "data" / "Instruments" / "instruments.jsonl")).resolve()
        self.username = username if username is not None else os.getenv("OOI_USERNAME")
        self.token = token if token is not None else os.getenv("OOI_TOKEN")
        self.max_request_days = max(1, int(os.getenv("OOI_M2M_MAX_REQUEST_DAYS", "31")))
        self.max_download_bytes = max(1, int(os.getenv("OOI_M2M_MAX_DOWNLOAD_BYTES", str(2 * 1024 ** 3))))
        self.timeout_seconds = max(1, int(os.getenv("OOI_M2M_TIMEOUT_SECONDS", "30")))
        self._http_get_override = http_get

    @property
    def credentials_ready(self) -> bool:
        return bool(self.username and self.token)

    @staticmethod
    def split_refdes(reference_designator: str) -> tuple[str, str, str]:
        refdes = str(reference_designator).strip().upper()
        if not REFDES_RE.fullmatch(refdes):
            raise ValueError("Invalid OOI reference designator; expected ARRAY-NODE-PORT-INSTRUMENT")
        array, node, instrument = refdes.split("-", 2)
        return array, node, instrument

    @staticmethod
    def _component(value: str, label: str) -> str:
        token = str(value).strip()
        if not COMPONENT_RE.fullmatch(token) or token in {".", ".."}:
            raise ValueError(f"Invalid {label}")
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

    @staticmethod
    def _approved_url(url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not (host == "oceanobservatories.org" or host.endswith(".oceanobservatories.org")):
            raise ValueError("OOI URL is outside the approved HTTPS domain")
        if parsed.username or parsed.password:
            raise ValueError("Credentials are not permitted in URLs")
        return url

    def _http(self, url: str, params: dict[str, Any] | None = None, authenticated: bool = False,
              max_bytes: int = 20 * 1024 * 1024) -> tuple[int, dict[str, str], bytes, str]:
        self._approved_url(url)
        if authenticated and not self.credentials_ready:
            raise M2MError("OOI_USERNAME and OOI_TOKEN are required for this live API call")
        if self._http_get_override:
            return self._http_get_override(url=url, params=params or {}, authenticated=authenticated, max_bytes=max_bytes)
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if params:
            query.update({k: str(v) for k, v in params.items()})
        final_url = urlunparse(parsed._replace(query=urlencode(query)))
        headers = {"User-Agent": "RCN-Agent-OOI-M2M/1.0", "Accept": "application/json, text/html, application/xml, */*"}
        if authenticated:
            raw = f"{self.username}:{self.token}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        request = Request(final_url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final = response.geturl()
                self._approved_url(final)
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise M2MError(f"Response exceeds {max_bytes} byte limit")
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise M2MError(f"Response exceeds {max_bytes} byte limit")
                return int(response.status), dict(response.headers.items()), data, final
        except HTTPError as exc:
            data = exc.read(min(max_bytes, 256 * 1024))
            return int(exc.code), dict(exc.headers.items()) if exc.headers else {}, data, exc.geturl()
        except URLError as exc:
            raise M2MError(f"OOI network request failed: {exc.reason}") from exc

    def _json(self, url: str, params: dict[str, Any] | None = None, authenticated: bool = True) -> Any:
        status, _, body, _ = self._http(url, params=params, authenticated=authenticated)
        if status < 200 or status >= 300:
            raise M2MError(f"OOI API returned HTTP {status}")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise M2MError("OOI API response was not valid JSON") from exc

    def status(self) -> dict:
        return {
            "ok": True,
            "credentials": {"OOI_USERNAME": bool(self.username), "OOI_TOKEN": bool(self.token)},
            "ready_for_live_api": self.credentials_ready,
            "credential_values_exposed": False,
            "runtime_root": str(self.runtime_root),
            "instrument_inventory": str(self.instrument_inventory),
            "instrument_inventory_exists": self.instrument_inventory.exists(),
            "limits": {"max_request_days": self.max_request_days, "max_download_bytes": self.max_download_bytes},
            "capabilities": ["local instrument search", "live instrument discovery", "vocabulary", "deployments", "methods and streams", "request estimate or submission", "async status", "result listing", "bounded downloads"],
            "source_references": SOURCE_REFERENCES,
        }

    def search_instruments(self, query: str | None = None, array: str | None = None,
                           node: str | None = None, instrument: str | None = None,
                           source: str = "local", limit: int = 100) -> dict:
        limit = max(1, min(int(limit), 500))
        source = source.casefold()
        if source not in {"local", "live"}:
            return _error("invalid_source", "source must be local or live")
        if source == "local":
            if not self.instrument_inventory.exists():
                return _error("missing_inventory", "Local instrument inventory was not found", path=str(self.instrument_inventory))
            terms = [str(x).casefold() for x in (query, array, node, instrument) if x]
            matches = []
            with self.instrument_inventory.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    refdes = str(row.get("canonical_id") or "").upper()
                    if not REFDES_RE.fullmatch(refdes):
                        continue
                    haystack = json.dumps(row, ensure_ascii=False).casefold()
                    if all(term in haystack for term in terms):
                        matches.append({k: row.get(k) for k in ("canonical_id", "name", "instrument_type", "location", "site", "node", "instrument_code", "projects", "latitude", "longitude", "depth_m")})
                        if len(matches) >= limit:
                            break
            return {"ok": True, "source": "local Graph-RAG instrument inventory", "count": len(matches), "instruments": matches}

        if not array:
            return _error("array_required", "Live discovery requires an array code to bound API traversal; use local search for broad discovery")
        array_code = self._component(array.upper(), "array")
        node_filter = self._component(node.upper(), "node") if node else None
        instrument_filter = self._component(instrument.upper(), "instrument") if instrument else None
        nodes = [node_filter] if node_filter else list(self._json(f"{SENSOR_ENDPOINT}/{array_code}"))
        found: list[dict] = []
        requests_used = 1
        for node_code in nodes[:100]:
            instruments = [instrument_filter] if instrument_filter else list(self._json(f"{SENSOR_ENDPOINT}/{array_code}/{node_code}"))
            requests_used += 1
            for instrument_code in instruments:
                refdes = f"{array_code}-{node_code}-{instrument_code}".upper()
                if REFDES_RE.fullmatch(refdes) and (not query or query.casefold() in refdes.casefold()):
                    found.append({"canonical_id": refdes, "site": array_code, "node": node_code, "instrument_code": instrument_code})
                    if len(found) >= limit:
                        return {"ok": True, "source": "live OOI M2M inventory", "count": len(found), "requests_used": requests_used, "instruments": found, "truncated": True}
        return {"ok": True, "source": "live OOI M2M inventory", "count": len(found), "requests_used": requests_used, "instruments": found, "truncated": False}

    def vocabulary(self, reference_designator: str) -> dict:
        array, node, instrument = self.split_refdes(reference_designator)
        data = self._json(f"{VOCAB_ENDPOINT}/{array}/{node}/{instrument}")
        return {"ok": True, "reference_designator": f"{array}-{node}-{instrument}", "vocabulary": data}

    def deployments(self, reference_designator: str, deployment: int | None = None, limit: int = 100) -> dict:
        array, node, instrument = self.split_refdes(reference_designator)
        dep = str(int(deployment)) if deployment is not None else "-1"
        data = self._json(f"{DEPLOYMENT_ENDPOINT}/{array}/{node}/{instrument}/{dep}")
        rows = data if isinstance(data, list) else [data]
        limit = max(1, min(int(limit), 500))
        return {"ok": True, "reference_designator": f"{array}-{node}-{instrument}", "deployment": deployment, "count": min(len(rows), limit), "deployments": rows[:limit], "truncated": len(rows) > limit}

    def list_streams(self, reference_designator: str, method: str | None = None, limit: int = 500) -> dict:
        array, node, instrument = self.split_refdes(reference_designator)
        base = f"{SENSOR_ENDPOINT}/{array}/{node}/{instrument}"
        methods = [self._component(method, "method")] if method else list(self._json(base))
        rows: list[dict] = []
        limit = max(1, min(int(limit), 2000))
        for item in methods:
            method_name = self._component(str(item), "method")
            if "bad" in method_name.casefold():
                continue
            streams = self._json(f"{base}/{method_name}")
            for stream in streams if isinstance(streams, list) else []:
                rows.append({"reference_designator": f"{array}-{node}-{instrument}", "method": method_name, "stream": str(stream)})
                if len(rows) >= limit:
                    return {"ok": True, "count": len(rows), "streams": rows, "truncated": True}
        return {"ok": True, "count": len(rows), "streams": rows, "truncated": False}

    def _plan(self, reference_designator: str, method: str, stream: str, begin: str, end: str,
              include_provenance: bool = True, include_annotations: bool = True,
              estimate_only: bool = True) -> dict:
        array, node, instrument = self.split_refdes(reference_designator)
        method_name = self._component(method, "method")
        stream_name = self._component(stream, "stream")
        begin_dt, end_dt = self._datetime(begin, "begin"), self._datetime(end, "end")
        if end_dt <= begin_dt:
            raise ValueError("end must be after begin")
        duration_days = (end_dt - begin_dt).total_seconds() / 86400
        if duration_days > self.max_request_days:
            raise ValueError(f"Request spans {duration_days:.3f} days; configured maximum is {self.max_request_days}")
        endpoint = f"{SENSOR_ENDPOINT}/{array}/{node}/{instrument}/{method_name}/{stream_name}"
        params = {
            "beginDT": self._api_time(begin_dt), "endDT": self._api_time(end_dt),
            "format": "application/netcdf", "include_provenance": str(bool(include_provenance)).lower(),
            "include_annotations": str(bool(include_annotations)).lower(),
            "estimate_only": str(bool(estimate_only)).lower(), "require_deployment": "true",
        }
        return {"reference_designator": f"{array}-{node}-{instrument}", "method": method_name,
                "stream": stream_name, "begin": params["beginDT"], "end": params["endDT"],
                "duration_days": duration_days, "endpoint": endpoint, "parameters": params,
                "estimate_only": bool(estimate_only)}

    def plan_request(self, **arguments: Any) -> dict:
        plan = self._plan(**arguments)
        return {"ok": True, "live_request_executed": False, "credentials_ready": self.credentials_ready, **plan}

    def _request_dir(self, request_id: str) -> Path:
        if not REQUEST_ID_RE.fullmatch(request_id):
            raise ValueError("Invalid local request ID")
        target = (self.runtime_root / "requests" / request_id).resolve()
        root = (self.runtime_root / "requests").resolve()
        if target.parent != root:
            raise ValueError("Request path escaped runtime root")
        return target

    def _write_state(self, state: dict) -> None:
        directory = self._request_dir(state["local_request_id"])
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="request-", suffix=".json", dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(tmp_name, directory / "request.json")
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _read_state(self, request_id: str) -> dict:
        path = self._request_dir(request_id) / "request.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown local request ID: {request_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def request_data(self, **arguments: Any) -> dict:
        plan = self._plan(**arguments)
        response = self._json(plan["endpoint"], params=plan["parameters"], authenticated=True)
        if not isinstance(response, dict):
            return _error("unexpected_response", "OOI request response was not an object")
        urls = [str(x) for x in response.get("allURLs", []) if isinstance(x, str)]
        thredds = next((u for u in urls if "thredds" in u.casefold()), None)
        download = next((u for u in urls if "async_results" in u.casefold() or "download" in u.casefold()), None)
        for url in (thredds, download):
            if url:
                self._approved_url(url)
        local_id = "ooi-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        status_urls = []
        if download:
            status_urls = [download.rstrip("/") + "/status.txt", download.rstrip("/") + "/status.json"]
        state = {
            "schema_version": "1.0", "local_request_id": local_id,
            "ooi_request_uuid": response.get("requestUUID"), "created_at_utc": _now(),
            "updated_at_utc": _now(), "state": "estimated" if plan["estimate_only"] else "submitted",
            "request": {k: plan[k] for k in ("reference_designator", "method", "stream", "begin", "end", "duration_days", "estimate_only")},
            "thredds_catalog": thredds, "download_catalog": download, "status_urls": status_urls,
            "size_calculation_bytes": response.get("sizeCalculation"),
            "time_calculation_seconds": response.get("timeCalculation"),
            "response_message": response.get("message"), "files": [],
        }
        self._write_state(state)
        return {"ok": True, **state, "state_file": str(self._request_dir(local_id) / "request.json"), "credentials_stored": False}

    def request_status(self, request_id: str) -> dict:
        state = self._read_state(request_id)
        checks = []
        complete = False
        for url in state.get("status_urls", []):
            status, headers, body, final = self._http(url, authenticated=False, max_bytes=1024 * 1024)
            checks.append({"url": final, "http_status": status, "content_type": headers.get("Content-Type"), "body_preview": body.decode("utf-8", errors="replace")[:2000]})
            if status == 200:
                complete = True
                break
        state["updated_at_utc"] = _now()
        state["state"] = "complete" if complete else state.get("state", "submitted")
        state["last_status_checks"] = checks
        self._write_state(state)
        return {"ok": True, "local_request_id": request_id, "state": state["state"], "complete": complete, "checks": checks}

    def _catalog_files(self, state: dict) -> list[dict]:
        results: dict[str, dict] = {}
        direct = state.get("download_catalog")
        if direct:
            status, _, body, final = self._http(direct, authenticated=False)
            if 200 <= status < 300:
                parser = _Links(); parser.feed(body.decode("utf-8", errors="replace"))
                for href in parser.links:
                    url = urljoin(final.rstrip("/") + "/", href)
                    suffix = Path(urlparse(url).path).suffix.casefold()
                    if suffix in ALLOWED_DOWNLOAD_SUFFIXES:
                        self._approved_url(url)
                        name = Path(urlparse(url).path).name
                        results[url] = {"name": name, "url": url, "suffix": suffix, "source": "async_download_index"}
        thredds = state.get("thredds_catalog")
        if thredds:
            xml_url = thredds[:-5] + ".xml" if thredds.endswith(".html") else thredds
            status, _, body, final = self._http(xml_url, authenticated=False)
            if 200 <= status < 300:
                try:
                    root = ElementTree.fromstring(body)
                    origin = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
                    for element in root.iter():
                        path = element.attrib.get("urlPath")
                        if not path:
                            continue
                        suffix = Path(path).suffix.casefold()
                        if suffix in ALLOWED_DOWNLOAD_SUFFIXES:
                            url = origin + "/thredds/fileServer/" + path.lstrip("/")
                            self._approved_url(url)
                            results.setdefault(url, {"name": Path(path).name, "url": url, "suffix": suffix, "source": "thredds_catalog"})
                except ElementTree.ParseError:
                    pass
        return sorted(results.values(), key=lambda row: (row["name"], row["url"]))

    def list_result_files(self, request_id: str, suffixes: list[str] | None = None, limit: int = 1000) -> dict:
        state = self._read_state(request_id)
        files = self._catalog_files(state)
        requested = {s.casefold() if str(s).startswith(".") else "." + str(s).casefold() for s in (suffixes or [".nc", ".json", ".txt"])}
        files = [row for row in files if row["suffix"] in requested]
        limit = max(1, min(int(limit), 5000))
        return {"ok": True, "local_request_id": request_id, "count": min(len(files), limit), "files": files[:limit], "truncated": len(files) > limit}

    def download_results(self, request_id: str, suffixes: list[str] | None = None,
                         max_files: int = 100, max_total_bytes: int | None = None) -> dict:
        state = self._read_state(request_id)
        listed = self.list_result_files(request_id, suffixes=suffixes, limit=max_files)
        files = listed["files"]
        byte_limit = min(self.max_download_bytes, int(max_total_bytes or self.max_download_bytes))
        if byte_limit < 1:
            raise ValueError("max_total_bytes must be positive")
        destination = self._request_dir(request_id) / "files"
        destination.mkdir(parents=True, exist_ok=True)
        downloaded, total = [], 0
        for item in files:
            remaining = byte_limit - total
            if remaining <= 0:
                break
            status, _, body, final = self._http(item["url"], authenticated=False, max_bytes=remaining)
            if status < 200 or status >= 300:
                downloaded.append({**item, "downloaded": False, "http_status": status})
                continue
            safe_name = Path(urlparse(final).path).name
            if not safe_name or safe_name in {".", ".."}:
                continue
            target = (destination / safe_name).resolve()
            if target.parent != destination.resolve():
                raise ValueError("Download filename escaped request directory")
            target.write_bytes(body)
            total += len(body)
            downloaded.append({"name": safe_name, "url": final, "downloaded": True, "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest(), "path": str(target)})
        state["updated_at_utc"] = _now()
        state["files"] = downloaded
        self._write_state(state)
        return {"ok": True, "local_request_id": request_id, "download_directory": str(destination), "downloaded_count": sum(bool(x.get("downloaded")) for x in downloaded), "total_bytes": total, "byte_limit": byte_limit, "files": downloaded}


OOI_M2M_TOOL_SCHEMAS = [
    {"name": "ooi_m2m_status", "description": "Report whether OOI M2M credentials and local instrument inventory are configured, without exposing secret values or making a network call.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "ooi_m2m_search_instruments", "description": "Search the local RCA/COSZO instrument inventory without credentials, or perform bounded live OOI inventory discovery when credentials are available.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "array": {"type": "string"}, "node": {"type": "string"}, "instrument": {"type": "string"}, "source": {"type": "string", "enum": ["local", "live"], "default": "local"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}}}},
    {"name": "ooi_m2m_vocabulary", "description": "Retrieve current human-readable OOI vocabulary metadata for any valid instrument reference designator.", "inputSchema": {"type": "object", "required": ["reference_designator"], "properties": {"reference_designator": {"type": "string"}}}},
    {"name": "ooi_m2m_deployments", "description": "Retrieve current OOI deployment and asset-event metadata for an instrument, optionally for one deployment number.", "inputSchema": {"type": "object", "required": ["reference_designator"], "properties": {"reference_designator": {"type": "string"}, "deployment": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}}}},
    {"name": "ooi_m2m_list_streams", "description": "List current OOI delivery methods and data streams for any valid instrument reference designator.", "inputSchema": {"type": "object", "required": ["reference_designator"], "properties": {"reference_designator": {"type": "string"}, "method": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 500}}}},
    {"name": "ooi_m2m_plan_request", "description": "Validate and preview a bounded OOI NetCDF request. This tool never contacts OOI and is useful before an estimate or submission.", "inputSchema": {"type": "object", "required": ["reference_designator", "method", "stream", "begin", "end"], "properties": {"reference_designator": {"type": "string"}, "method": {"type": "string"}, "stream": {"type": "string"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}, "include_provenance": {"type": "boolean", "default": True}, "include_annotations": {"type": "boolean", "default": True}, "estimate_only": {"type": "boolean", "default": True}}}},
    {"name": "ooi_m2m_request_data", "description": "Send a bounded OOI M2M NetCDF estimate or asynchronous data request and persist non-secret request state under runtime_data/OOIM2M.", "inputSchema": {"type": "object", "required": ["reference_designator", "method", "stream", "begin", "end"], "properties": {"reference_designator": {"type": "string"}, "method": {"type": "string"}, "stream": {"type": "string"}, "begin": {"type": "string", "format": "date-time"}, "end": {"type": "string", "format": "date-time"}, "include_provenance": {"type": "boolean", "default": True}, "include_annotations": {"type": "boolean", "default": True}, "estimate_only": {"type": "boolean", "default": True}}}},
    {"name": "ooi_m2m_request_status", "description": "Check status.txt/status.json for a previously persisted OOI request and update its local state.", "inputSchema": {"type": "object", "required": ["request_id"], "properties": {"request_id": {"type": "string"}}}},
    {"name": "ooi_m2m_list_result_files", "description": "List NetCDF, provenance, annotation, and related files exposed by an OOI request catalog without downloading them.", "inputSchema": {"type": "object", "required": ["request_id"], "properties": {"request_id": {"type": "string"}, "suffixes": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 1000}}}},
    {"name": "ooi_m2m_download_results", "description": "Download a bounded selection of files for a persisted OOI request into its runtime directory, recording byte counts and SHA-256 hashes.", "inputSchema": {"type": "object", "required": ["request_id"], "properties": {"request_id": {"type": "string"}, "suffixes": {"type": "array", "items": {"type": "string"}}, "max_files": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}, "max_total_bytes": {"type": "integer", "minimum": 1}}}},
]


def dispatch_ooi_m2m(toolkit: OOIM2MToolkit, name: str, arguments: dict) -> dict:
    calls = {
        "ooi_m2m_status": lambda: toolkit.status(),
        "ooi_m2m_search_instruments": lambda: toolkit.search_instruments(**arguments),
        "ooi_m2m_vocabulary": lambda: toolkit.vocabulary(**arguments),
        "ooi_m2m_deployments": lambda: toolkit.deployments(**arguments),
        "ooi_m2m_list_streams": lambda: toolkit.list_streams(**arguments),
        "ooi_m2m_plan_request": lambda: toolkit.plan_request(**arguments),
        "ooi_m2m_request_data": lambda: toolkit.request_data(**arguments),
        "ooi_m2m_request_status": lambda: toolkit.request_status(**arguments),
        "ooi_m2m_list_result_files": lambda: toolkit.list_result_files(**arguments),
        "ooi_m2m_download_results": lambda: toolkit.download_results(**arguments),
    }
    if name not in calls:
        return _error("unknown_tool", name)
    try:
        return calls[name]()
    except Exception as exc:
        return _error(type(exc).__name__, str(exc))
