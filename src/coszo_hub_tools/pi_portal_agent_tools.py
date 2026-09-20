#!/usr/bin/env python3
"""Bounded tools for the public UW RCA Principal Investigator data portal.

The portal is an unauthenticated directory tree at piweb.ooirsn.uw.edu.  This
adapter exposes an audited static registry, bounded directory discovery, and
bounded downloads.  It never accepts arbitrary hosts or output directories.
Downloaded files and provenance manifests live under runtime_data/PIPortal;
they are runtime evidence, not Graph-RAG corpus input.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import posixpath
import re
import tempfile
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


UTC = timezone.utc
PORTAL_HOST = "piweb.ooirsn.uw.edu"
PORTAL_ROOT = f"http://{PORTAL_HOST}/"
REQUEST_ID_RE = re.compile(r"^piportal-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$")
DATE_PATTERNS = (
    re.compile(r"(?<!\d)(20\d{2})[-_/]([01]\d)[-_/]([0-3]\d)(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})([01]\d)([0-3]\d)(?:T|_|-)?(?!\d)"),
)


def _endpoint(endpoint_id: str, label: str, url: str, formats: list[str], role: str = "science data") -> dict:
    return {"endpoint_id": endpoint_id, "label": label, "url": url, "formats": formats, "role": role}


# Ten audited RCA PI datasets.  Subcollections are endpoints rather than
# separate instruments so the registry can answer every known download route.
PI_INSTRUMENTS: dict[str, dict[str, Any]] = {
    "PI-OVRSRA101": {
        "name": "MARUM Southern Hydrate Ridge Overview Scanning Sonar",
        "aliases": ["OVRSRA101", "MARUM overview sonar", "scanning sonar"],
        "site": "Southern Hydrate Ridge Summit",
        "ooi_site": "RS01SUM2", "node": "MJ01B", "depth_m": 780,
        "formats": [".wc"], "path_pattern": "{YYYY}/{MM}/{timestamp}/data/",
        "endpoints": [_endpoint("marum-ovrsra101", "OVRSRA101 raw sonar", f"{PORTAL_ROOT}marum/data/OVRSRA101/", [".wc"])],
    },
    "PI-QNTSRA101": {
        "name": "MARUM Southern Hydrate Ridge Quantification Rotary Sonar",
        "aliases": ["QNTSRA101", "MARUM quantification sonar", "rotary sonar"],
        "site": "Southern Hydrate Ridge Summit",
        "ooi_site": "RS01SUM2", "node": "MJ01B", "depth_m": 780,
        "formats": [".smb"], "path_pattern": "{YYYY}/{MM}/",
        "endpoints": [_endpoint("marum-qntsra101", "QNTSRA101 raw sonar", f"{PORTAL_ROOT}marum/data/QNTSRA101/", [".smb"])],
    },
    "PI-CAMPIA101": {
        "name": "MARUM Camera System",
        "aliases": ["CAMPIA101", "MARUM camera", "Summit-A camera"],
        "site": "Summit-A vent, Southern Hydrate Ridge",
        "ooi_site": "RS01SUM2", "node": "MJ01B", "depth_m": 780,
        "formats": [".jpg", ".mp4", ".csv", ".log"], "path_pattern": "Stills/{YY}/ or Videos/{YY}/",
        "endpoints": [
            _endpoint("camera-stills", "CAMPIA101 still images", f"{PORTAL_ROOT}marum/data/CAMPIA101/Stills/", [".jpg"]),
            _endpoint("camera-videos", "CAMPIA101 videos", f"{PORTAL_ROOT}marum/data/CAMPIA101/Videos/", [".mp4"]),
            _endpoint("camera-initial-stills", "CAMPIA101 initial still images", f"{PORTAL_ROOT}marum/data/CAMPIA101/InitialStills/", [".jpg"]),
            _endpoint("camera-initial-videos", "CAMPIA101 initial videos", f"{PORTAL_ROOT}marum/data/CAMPIA101/InitialVideos/", [".mp4"]),
            _endpoint("camera-metadata", "CAMPIA101 preparation, debug, and log files", f"{PORTAL_ROOT}marum/data/CAMPIA101/", [".csv", ".txt", ".log"], "engineering and metadata"),
        ],
    },
    "PI-CTDPFA110": {
        "name": "MARUM CTD-DO Instrument",
        "aliases": ["CTDPFA110", "MARUM CTD", "CTD-DO"],
        "site": "Southern Hydrate Ridge Summit",
        "ooi_site": "RS01SUM2", "node": "MJ01B", "depth_m": 780,
        "formats": [".dat"], "path_pattern": "{YYYY}/{MM}/{YYYY-MM-DD}.dat",
        "endpoints": [_endpoint("marum-ctdpfa110", "CTDPFA110 daily data", f"{PORTAL_ROOT}marum/data/CTDPFA110/", [".dat"])],
    },
    "PI-COVIS": {
        "name": "Cabled Observatory Vent Imaging Sonar",
        "aliases": ["COVIS", "COVISA301", "vent imaging sonar"],
        "site": "ASHES Hydrothermal Field, Axial Seamount",
        "ooi_site": "RS03ASHS", "node": "MJ03B", "depth_m": 1545,
        "formats": [".tar.gz", ".mat"], "path_pattern": "survey archive files",
        "endpoints": [
            _endpoint("covis-raw", "COVIS raw survey archives", f"{PORTAL_ROOT}covis/data/COVIS/", [".tar.gz", ".mat"], "raw science data"),
            _endpoint("covis-browse", "COVIS browse products", f"{PORTAL_ROOT}covis/data/BROWSE/", ["browse products"], "quick-look and browse products"),
            _endpoint("covis-engineering", "COVIS engineering data", f"{PORTAL_ROOT}covis/data/COVIS-ENG/", ["engineering data"], "engineering records"),
            _endpoint("covis-processed", "COVIS processed products", f"{PORTAL_ROOT}covis/processed/", ["processed products", ".pdf"], "processed science data and documentation"),
        ],
    },
    "PI-DAS-OPTASENSE-SILIXA": {
        "name": "2021 RCA Distributed Acoustic and Temperature Sensing experiment",
        "aliases": ["DAS", "OptaSense", "Silixa", "DTS", "2021 community experiment"],
        "site": "RCA north and south backbone cables",
        "ooi_site": None, "node": None, "depth_m": None,
        "formats": [".h5", ".xml", "vendor DAS formats"], "path_pattern": "provider/fiber or cable/date hierarchy",
        "endpoints": [
            _endpoint("das-optasense-north-receive", "OptaSense north cable receive fiber", f"{PORTAL_ROOT}das/data/Optasense/NorthCable/ReceiveFiber/", [".h5"]),
            _endpoint("das-optasense-north-transmit", "OptaSense north cable transmit fiber", f"{PORTAL_ROOT}das/data/Optasense/NorthCable/TransmitFiber/", [".h5"]),
            _endpoint("das-optasense-south-receive", "OptaSense south cable receive fiber", f"{PORTAL_ROOT}das/data/Optasense/SouthCable/ReceiveFiber/", [".h5"]),
            _endpoint("das-optasense-south-transmit", "OptaSense south cable transmit fiber", f"{PORTAL_ROOT}das/data/Optasense/SouthCable/TransmitFiber/", [".h5"]),
            _endpoint("das-silixa-das", "Silixa DAS", f"{PORTAL_ROOT}das/data/Silixa/DAS/", ["vendor DAS formats"]),
            _endpoint("das-silixa-dts", "Silixa DTS", f"{PORTAL_ROOT}das/data/Silixa/DTS/", [".xml"]),
        ],
    },
    "PI-DAS24": {
        "name": "2024 RCA Distributed Acoustic Sensing experiment",
        "aliases": ["DAS24", "2024 DAS", "dphi"],
        "site": "RCA south cable, shore to first repeater",
        "ooi_site": None, "node": None, "depth_m": None,
        "formats": [".hdf5"], "path_pattern": "{YYYYMMDD}/dphi/",
        "endpoints": [_endpoint("das24", "DAS24 dphi files", f"{PORTAL_ROOT}das24/data/", [".hdf5"])],
    },
    "PI-DAS25": {
        "name": "2025–2026 RCA Distributed Acoustic Sensing experiment",
        "aliases": ["DAS25", "2025 DAS", "2026 DAS", "MultiDAS", "OptoDAS"],
        "site": "RCA north and south backbone cables",
        "ooi_site": None, "node": None, "depth_m": None,
        "formats": ["HDF5", "raw binary"], "path_pattern": "{YYYY}/{MM}/{DD}/{cable}/",
        "endpoints": [
            _endpoint("das25-multidas", "DAS25 MultiDAS", f"{PORTAL_ROOT}das25/data/MultiDAS/", ["proprietary raw binary"]),
            _endpoint("das25-optodas", "DAS25 OptoDAS", f"{PORTAL_ROOT}das25/data/OptoDAS/", ["HDF5"]),
        ],
    },
    "PI-SCPRAA301": {
        "name": "Self-Calibrating Pressure Recorder",
        "aliases": ["SCPRAA301", "SCPRAAA301", "SCPR"],
        "site": "Central Caldera, Axial Seamount",
        "ooi_site": "RS03CCAL", "node": "MJ03F", "depth_m": 1535,
        "formats": ["PI pressure data"], "path_pattern": "collection/year hierarchy",
        "endpoints": [
            _endpoint("scpr-data", "SCPR combined data", f"{PORTAL_ROOT}scpr/data/SCPR_Data/", ["PI pressure data"]),
            _endpoint("scpr-aa301", "SCPRAA301 data", f"{PORTAL_ROOT}scpr/data/SCPRAA301/", ["PI pressure data"]),
            _endpoint("scpr-paro1", "SCPRAA301 PARO1", f"{PORTAL_ROOT}scpr/data/SCPRAA301_PARO1/", ["PI pressure data"]),
            _endpoint("scpr-paro2", "SCPRAA301 PARO2", f"{PORTAL_ROOT}scpr/data/SCPRAA301_PARO2/", ["PI pressure data"]),
            _endpoint("scpr-internal", "SCPRAA301 SCPR", f"{PORTAL_ROOT}scpr/data/SCPRAA301_SCPR/", ["PI pressure data"]),
        ],
    },
    "PI-A0ABPA301": {
        "name": "A-0-A Calibrated Pressure Instrument",
        "aliases": ["A0ABPA301", "A-0-A", "calibrated pressure instrument"],
        "site": "Central Caldera, Axial Seamount",
        "ooi_site": "RS03CCAL", "node": "MJ03F", "depth_m": 1530,
        "formats": [".dat", "command and engineering text"], "path_pattern": "{YYYY}/{MM}/ daily files",
        "endpoints": [
            _endpoint("a0a-data", "A0A science data", f"{PORTAL_ROOT}a0a/data/A0ABPA301_data/", [".dat"]),
            _endpoint("a0a-commands", "A0A command records", f"{PORTAL_ROOT}a0a/data/A0ABPA301_commands/", ["command text"], "command records"),
            _endpoint("a0a-engineering", "A0A engineering files", f"{PORTAL_ROOT}a0a/data/eng/", ["engineering text"], "engineering records"),
            _endpoint("a0a-processed-ascii", "A0A processed ASCII", f"{PORTAL_ROOT}a0a/processed/ASCII/", ["ASCII"], "processed science data"),
            _endpoint("a0a-processed-netcdf", "A0A processed NetCDF", f"{PORTAL_ROOT}a0a/processed/NetCDF/", [".nc"], "processed science data"),
        ],
    },
}

# Fields used directly by the PI Graph-RAG builder.  Keeping this enrichment
# beside the audited registry makes the corpus and live tool share one source
# of truth for identifiers and endpoints.
_GRAPH_METADATA = {
    "PI-OVRSRA101": {
        "official_url": "https://oceanobservatories.org/pi-instrument/marum-southern-hydrate-ridge-overview-sonar-ovrsra101/",
        "existing_instrument_ids": ["INSTRUMENT-5d7ed7b890f1dcaead"],
        "observed_layout": "year/month/timestamp/data directories containing .wc files",
        "caveats": ["Raw sonar format requires a suitable scientific decoder."],
    },
    "PI-QNTSRA101": {
        "official_url": "https://oceanobservatories.org/pi-instrument/marum-quantification-sonar-southern-hydrate-ridge/",
        "existing_instrument_ids": ["INSTRUMENT-833ab5c6a5f416bce0"],
        "observed_layout": "year/month directories containing .smb files",
        "caveats": ["Raw sonar format requires a suitable scientific decoder."],
    },
    "PI-CAMPIA101": {
        "official_url": "https://oceanobservatories.org/pi-instrument/marum-camera-system-campia101/",
        "existing_instrument_ids": ["INSTRUMENT-1b4f79a7318105f747"],
        "observed_layout": "Stills and Videos trees plus CSV, debug, and log material",
        "caveats": ["Large media collections should be filtered by date before download."],
    },
    "PI-CTDPFA110": {
        "official_url": "https://oceanobservatories.org/pi-instrument/marum-ctd-do-instrument-ctdpfa110/",
        "existing_instrument_ids": ["INSTRUMENT-cef8e76ca878e26b97"],
        "observed_layout": "year/month directories containing daily .dat files",
        "caveats": ["Daily PI .dat files are distinct from OOI M2M-delivered core instrument products."],
    },
    "PI-COVIS": {
        "official_url": "https://oceanobservatories.org/pi-instrument/cabled-array-vent-imaging-sonar-covis/",
        "existing_instrument_ids": ["INSTRUMENT-b1d858e0c31845d23e"],
        "observed_layout": "survey .tar.gz archives, with MATLAB products inside archives",
        "caveats": ["The live directory index is large; use filename or date filters before downloading archives."],
    },
    "PI-DAS-OPTASENSE-SILIXA": {
        "official_url": "https://oceanobservatories.org/pi-instrument/rapid-a-community-test-of-distributed-acoustic-sensing-on-the-ocean-observatories-initiative-regional-cabled-array/",
        "existing_instrument_ids": ["INSTRUMENT-e49ff2e8088de867de", "INSTRUMENT-981a1c15a947d3b1a1"],
        "observed_layout": "OptaSense north/south receive/transmit fiber trees and Silixa DAS/DTS cable trees",
        "caveats": ["Provider formats differ; some DAS files are proprietary while observed DTS files are XML."],
    },
    "PI-DAS24": {
        "official_url": "https://oceanobservatories.org/pi-instrument/rapid-multiplexed-distributed-acoustic-sensing-das-at-the-ocean-observatory-initiative-ooi-regional-cabled-array-rca/",
        "existing_instrument_ids": ["INSTRUMENT-bf860ab80551b1f3c9"],
        "observed_layout": "YYYYMMDD/dphi directories containing ten-second .hdf5 files",
        "caveats": ["Individual days contain thousands of files; constrain discovery and download requests."],
    },
    "PI-DAS25": {
        "official_url": "https://oceanobservatories.org/pi-instrument/multi-span-distributed-fiber-sensing-on-the-ocean-observatories-initiative-regional-cabled-array/",
        "existing_instrument_ids": ["INSTRUMENT-8f08939e9167bac57c"],
        "observed_layout": "MultiDAS and OptoDAS year/month/day trees split by north/south cable and spacing",
        "caveats": ["The collection is growing and includes both HDF5 and raw binary products."],
    },
    "PI-SCPRAA301": {
        "official_url": "https://oceanobservatories.org/pi-instrument/self-calibrating-pressure-recorder/",
        "existing_instrument_ids": ["INSTRUMENT-b1b4a4d854850f827d"],
        "observed_layout": "combined, instrument, PARO1, PARO2, and internal SCPR collection trees",
        "caveats": ["Official material uses both SCPRAA301 and SCPRAAA301 spellings."],
    },
    "PI-A0ABPA301": {
        "official_url": "https://oceanobservatories.org/pi-instrument/a-0-a-calibrated-pressure-instrument/",
        "existing_instrument_ids": ["INSTRUMENT-532da1331eb8530830"],
        "observed_layout": "science data by year/month plus separate command and engineering trees",
        "caveats": ["Science, command, and engineering endpoints have different roles and should remain distinguishable."],
    },
}

_ENDPOINT_PATTERNS = {
    "camera-stills": "{YY}/.../*.jpg", "camera-videos": "{YY}/.../*.mp4",
    "camera-initial-stills": "initial still-image hierarchy", "camera-initial-videos": "initial video hierarchy",
    "camera-metadata": "Prepare.csv, debug.txt, StackTrace.log",
    "covis-raw": "flat survey archive listing (*.tar.gz)", "covis-browse": "{YYYY}/ quick-look products",
    "covis-engineering": "{YYYY}/ engineering records", "covis-processed": "processed product and documentation hierarchy",
    "das-optasense-north-receive": "NorthCable/ReceiveFiber timestamped *.h5",
    "das-optasense-north-transmit": "NorthCable/TransmitFiber timestamped *.h5",
    "das-optasense-south-receive": "SouthCable/ReceiveFiber timestamped *.h5",
    "das-optasense-south-transmit": "SouthCable/TransmitFiber timestamped *.h5",
    "das-silixa-das": "North65km/ and South90km/ DAS trees",
    "das-silixa-dts": "Fiber001on65km/ and Fiber002on90km/ DTS trees",
    "a0a-data": "{YYYY}/{MM}/ daily *.dat", "a0a-commands": "instrument command records",
    "a0a-engineering": "engineering hierarchy", "a0a-processed-ascii": "processed ASCII hierarchy",
    "a0a-processed-netcdf": "processed NetCDF hierarchy",
}

for _instrument_key, _instrument in PI_INSTRUMENTS.items():
    _instrument["canonical_id"] = _instrument_key
    _instrument["instrument_key"] = _instrument_key
    _instrument["location"] = _instrument["site"]
    _instrument["portal_status"] = "public directory observed reachable over HTTP during the 2026-09 audit"
    _instrument.update(_GRAPH_METADATA[_instrument_key])
    for _item in _instrument["endpoints"]:
        _item["id"] = _item["endpoint_id"]
        _item["base_url"] = _item["url"]
        _item["path_pattern"] = _ENDPOINT_PATTERNS.get(_item["endpoint_id"], _instrument["path_pattern"])
        _item["kind"] = _item["role"]

# Backward-compatible internal name.  Consumers should import PI_INSTRUMENTS.
PI_DATASETS = PI_INSTRUMENTS


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


class PIPortalError(RuntimeError):
    pass


class _DirectoryLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []


class PIPortalToolkit:
    """Audited PI registry plus constrained directory browsing and downloads."""

    def __init__(self, runtime_root: str | Path | None = None,
                 http_get: Callable[..., tuple[int, dict[str, str], bytes, str]] | None = None) -> None:
        project = Path(__file__).resolve().parents[2]
        self.runtime_root = Path(runtime_root or os.getenv("PI_PORTAL_RUNTIME_ROOT", project / "runtime_data" / "PIPortal")).resolve()
        self.timeout_seconds = max(1, int(os.getenv("PI_PORTAL_TIMEOUT_SECONDS", "60")))
        self.max_index_bytes = max(1024, int(os.getenv("PI_PORTAL_MAX_INDEX_BYTES", str(10 * 1024 ** 2))))
        self.max_download_bytes = max(1, int(os.getenv("PI_PORTAL_MAX_DOWNLOAD_BYTES", str(512 * 1024 ** 2))))
        self.max_download_files = max(1, int(os.getenv("PI_PORTAL_MAX_DOWNLOAD_FILES", "10")))
        self.max_retries = max(0, min(int(os.getenv("PI_PORTAL_MAX_RETRIES", "2")), 5))
        self.retry_backoff_seconds = max(0.0, float(os.getenv("PI_PORTAL_RETRY_BACKOFF_SECONDS", "0.5")))
        self._http_get_override = http_get

    @staticmethod
    def _approved_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").casefold() != PORTAL_HOST:
            raise ValueError("URL is outside the exact approved PI portal host")
        if parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            raise ValueError("Credentials and nonstandard ports are not permitted in PI portal URLs")
        if parsed.query or parsed.fragment:
            raise ValueError("Query strings and fragments are not permitted in PI portal URLs")
        return url

    @staticmethod
    def _dataset(instrument_id: str) -> tuple[str, dict[str, Any]]:
        token = str(instrument_id).strip().upper()
        if token in PI_DATASETS:
            return token, PI_DATASETS[token]
        for key, value in PI_DATASETS.items():
            aliases = [str(item).upper() for item in value.get("aliases", [])]
            if token in aliases:
                return key, value
        raise ValueError("Unknown PI instrument or dataset ID")

    @classmethod
    def _endpoint_for(cls, instrument_id: str, endpoint_id: str | None) -> tuple[str, dict[str, Any], dict[str, Any]]:
        key, dataset = cls._dataset(instrument_id)
        endpoints = dataset["endpoints"]
        if endpoint_id is None:
            if len(endpoints) != 1:
                raise ValueError("endpoint_id is required because this dataset has multiple download endpoints")
            return key, dataset, endpoints[0]
        endpoint_token = str(endpoint_id).strip().casefold()
        for endpoint in endpoints:
            if endpoint["endpoint_id"].casefold() == endpoint_token:
                return key, dataset, endpoint
        raise ValueError("Unknown endpoint_id for this PI dataset")

    @classmethod
    def _resolved_url(cls, base_url: str, relative_path: str = "", *, directory: bool = False) -> tuple[str, str]:
        cls._approved_url(base_url)
        raw = str(relative_path or "").replace("\\", "/")
        for _ in range(3):
            decoded = unquote(raw)
            if decoded == raw:
                break
            raw = decoded
        parsed_relative = urlparse(raw)
        if parsed_relative.scheme or parsed_relative.netloc or parsed_relative.query or parsed_relative.fragment:
            raise ValueError("relative_path must be a plain path within the selected endpoint")
        path_parts = raw.split("/")
        if path_parts and path_parts[-1] == "":
            path_parts.pop()
        if raw.startswith("/") or any(part in {"", ".", ".."} for part in path_parts):
            # Empty overall input and one trailing slash are allowed; ambiguous
            # internal separators and traversal segments are not.
            if raw:
                raise ValueError("relative_path contains an absolute, empty, or traversal segment")
        normalized = posixpath.normpath(raw) if raw else ""
        if normalized in {".", ".."} or normalized.startswith("../"):
            raise ValueError("relative_path escaped the selected endpoint")
        if directory and normalized and not normalized.endswith("/"):
            normalized += "/"
        target = urljoin(base_url, quote(normalized, safe="/-_.~()"))
        cls._approved_url(target)
        base = urlparse(base_url)
        resolved = urlparse(target)
        base_path = base.path if base.path.endswith("/") else base.path + "/"
        if resolved.scheme != base.scheme or resolved.path != base_path.rstrip("/") and not resolved.path.startswith(base_path):
            raise ValueError("Resolved URL escaped the selected PI endpoint")
        return target, normalized

    def _http_once(self, url: str, max_bytes: int) -> tuple[int, dict[str, str], bytes, str]:
        self._approved_url(url)
        if self._http_get_override:
            status, headers, body, final = self._http_get_override(url=url, max_bytes=max_bytes)
            self._approved_url(final)
            if len(body) > max_bytes:
                raise PIPortalError(f"Response exceeds {max_bytes} byte limit")
            return status, headers, body, final
        request = Request(url, headers={"User-Agent": "RCN-Agent-PI-Portal/1.0", "Accept": "text/html, application/octet-stream, */*"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final = response.geturl()
                self._approved_url(final)
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise PIPortalError(f"Response exceeds {max_bytes} byte limit")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise PIPortalError(f"Response exceeds {max_bytes} byte limit")
                return int(response.status), dict(response.headers.items()), body, final
        except HTTPError as exc:
            body = exc.read(min(max_bytes, 256 * 1024))
            final = exc.geturl()
            self._approved_url(final)
            return int(exc.code), dict(exc.headers.items()) if exc.headers else {}, body, final
        except URLError as exc:
            raise PIPortalError(f"PI portal request failed: {exc.reason}") from exc

    def _http(self, url: str, max_bytes: int) -> tuple[int, dict[str, str], bytes, str]:
        """GET with short retries for transient connection failures and 5xx."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._http_once(url, max_bytes)
                if result[0] < 500 or attempt >= self.max_retries:
                    return result
                last_error = PIPortalError(f"PI portal returned transient HTTP {result[0]}")
            except (URLError, PIPortalError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
            if self.retry_backoff_seconds:
                time.sleep(self.retry_backoff_seconds * (2 ** attempt))
        raise PIPortalError(str(last_error or "PI portal request failed"))

    @staticmethod
    def _date_from_path(path: str) -> str | None:
        for pattern in DATE_PATTERNS:
            match = pattern.search(path)
            if match:
                try:
                    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=UTC).date().isoformat()
                except ValueError:
                    return None
        return None

    @classmethod
    def _parse_listing(cls, body: bytes, directory_url: str, base_url: str) -> list[dict[str, Any]]:
        parser = _DirectoryLinks()
        parser.feed(body.decode("utf-8", errors="replace"))
        base_path = urlparse(base_url).path
        if not base_path.endswith("/"):
            base_path += "/"
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for href, label in parser.links:
            if not href or href.startswith(("?", "#")):
                continue
            try:
                candidate = urljoin(directory_url, href)
                cls._approved_url(candidate)
            except ValueError:
                continue
            parsed = urlparse(candidate)
            if not parsed.path.startswith(base_path) or parsed.path.rstrip("/") == urlparse(directory_url).path.rstrip("/"):
                continue
            relative = unquote(parsed.path[len(base_path):])
            if not relative or relative.startswith("../") or "/../" in relative:
                continue
            is_directory = href.endswith("/") or parsed.path.endswith("/")
            relative = relative.rstrip("/") + ("/" if is_directory else "")
            if relative in seen:
                continue
            seen.add(relative)
            entries.append({
                "name": unquote(label).strip().rstrip("/") or Path(relative.rstrip("/")).name,
                "relative_path": relative,
                "kind": "directory" if is_directory else "file",
                "url": candidate,
                "observation_date": cls._date_from_path(relative),
            })
        return entries

    def status(self) -> dict:
        return {
            "ok": True,
            "portal": PORTAL_ROOT,
            "credentials_required": False,
            "credential_values_accepted": False,
            "transport_note": "The audited portal currently responds over public HTTP. HTTPS may be used only if the same exact host supports it.",
            "dataset_count": len(PI_DATASETS),
            "endpoint_count": sum(len(item["endpoints"]) for item in PI_DATASETS.values()),
            "runtime_root": str(self.runtime_root),
            "limits": {
                "max_index_bytes": self.max_index_bytes,
                "max_download_files": self.max_download_files,
                "max_download_bytes": self.max_download_bytes,
                "timeout_seconds": self.timeout_seconds,
                "max_retries": self.max_retries,
                "retry_backoff_seconds": self.retry_backoff_seconds,
            },
            "workflow": "Answer availability from the Graph-RAG corpus first; use these live tools to browse or download current portal files.",
        }

    def list_instruments(self, query: str | None = None) -> dict:
        needle = str(query or "").casefold().strip()
        instruments = []
        for instrument_id, dataset in PI_DATASETS.items():
            record = {"instrument_id": instrument_id, **dataset}
            if needle and needle not in json.dumps(record, ensure_ascii=False).casefold():
                continue
            record["download_locations"] = [endpoint["url"] for endpoint in dataset["endpoints"]]
            instruments.append(record)
        return {"ok": True, "count": len(instruments), "instruments": instruments, "source": "audited PI portal registry", "live_request_executed": False}

    def browse(self, instrument_id: str, endpoint_id: str | None = None,
               relative_path: str = "", limit: int = 500) -> dict:
        key, dataset, endpoint = self._endpoint_for(instrument_id, endpoint_id)
        directory_url, normalized = self._resolved_url(endpoint["url"], relative_path, directory=True)
        status, headers, body, final = self._http(directory_url, self.max_index_bytes)
        if status == 404:
            return _error("directory_not_found", "PI portal directory was not found", source_url=final)
        if status < 200 or status >= 300:
            return _error("pi_portal_http_error", f"PI portal returned HTTP {status}", source_url=final)
        maximum = max(1, min(int(limit), 5000))
        all_entries = self._parse_listing(body, final, endpoint["url"])
        entries = all_entries[:maximum]
        return {
            "ok": True, "instrument_id": key, "instrument_name": dataset["name"],
            "endpoint_id": endpoint["endpoint_id"], "endpoint_label": endpoint["label"],
            "relative_path": normalized, "source_url": final,
            "content_type": headers.get("Content-Type"), "retrieved_at_utc": _now(),
            "count": len(entries), "truncated": len(all_entries) > maximum, "entries": entries,
        }

    def find_files(self, instrument_id: str, endpoint_id: str | None = None,
                   relative_path: str = "", pattern: str | None = None,
                   extensions: list[str] | None = None, start: str | None = None,
                   end: str | None = None, max_depth: int = 3,
                   max_directories: int = 100, max_files: int = 1000) -> dict:
        key, dataset, endpoint = self._endpoint_for(instrument_id, endpoint_id)
        if endpoint["endpoint_id"] == "covis-raw" and not relative_path and not any((pattern, extensions, start, end)):
            raise ValueError("COVIS raw is a large flat archive index; provide a filename pattern, extension, or date bound")
        _, start_path = self._resolved_url(endpoint["url"], relative_path, directory=True)
        depth_limit = max(0, min(int(max_depth), 10))
        directory_limit = max(1, min(int(max_directories), 1000))
        file_limit = max(1, min(int(max_files), 10000))
        suffixes = None
        if extensions:
            suffixes = tuple(item.casefold() if str(item).startswith(".") else "." + str(item).casefold() for item in extensions)
        if start and not re.fullmatch(r"20\d{2}-[01]\d-[0-3]\d", start):
            raise ValueError("start must be YYYY-MM-DD")
        if end and not re.fullmatch(r"20\d{2}-[01]\d-[0-3]\d", end):
            raise ValueError("end must be YYYY-MM-DD")
        if start and end and end < start:
            raise ValueError("end must be on or after start")
        queue: deque[tuple[str, int]] = deque([(start_path, 0)])
        visited: set[str] = set()
        files: list[dict[str, Any]] = []
        truncated = False
        while queue:
            directory, depth = queue.popleft()
            if directory in visited:
                continue
            if len(visited) >= directory_limit:
                truncated = True
                break
            visited.add(directory)
            result = self.browse(key, endpoint["endpoint_id"], directory, limit=5000)
            if not result.get("ok"):
                return result
            for entry in result["entries"]:
                if entry["kind"] == "directory":
                    if depth < depth_limit:
                        queue.append((entry["relative_path"], depth + 1))
                    continue
                rel = entry["relative_path"]
                filename = posixpath.basename(rel)
                if pattern and not fnmatch.fnmatch(filename.casefold(), pattern.casefold()):
                    continue
                if suffixes and not filename.casefold().endswith(suffixes):
                    continue
                day = entry.get("observation_date")
                if (start or end) and not day:
                    continue
                if start and day and day < start:
                    continue
                if end and day and day > end:
                    continue
                files.append(entry)
                if len(files) >= file_limit:
                    truncated = True
                    break
            if truncated:
                break
        return {
            "ok": True, "instrument_id": key, "instrument_name": dataset["name"],
            "endpoint_id": endpoint["endpoint_id"], "source_url": endpoint["url"],
            "searched_relative_path": start_path, "directories_visited": len(visited),
            "count": len(files), "truncated": truncated, "files": files,
            "retrieved_at_utc": _now(),
        }

    def plan_download(self, instrument_id: str, relative_paths: list[str], endpoint_id: str | None = None) -> dict:
        key, dataset, endpoint = self._endpoint_for(instrument_id, endpoint_id)
        if not isinstance(relative_paths, list) or not relative_paths:
            raise ValueError("relative_paths must contain at least one file")
        if len(relative_paths) > self.max_download_files:
            raise ValueError(f"At most {self.max_download_files} files may be downloaded in one request")
        files = []
        seen: set[str] = set()
        for value in relative_paths:
            url, normalized = self._resolved_url(endpoint["url"], str(value), directory=False)
            if not normalized or normalized.endswith("/"):
                raise ValueError("Every relative_paths entry must identify a file")
            if normalized in seen:
                continue
            seen.add(normalized)
            files.append({"relative_path": normalized, "source_url": url})
        return {
            "ok": True, "live_request_executed": False,
            "instrument_id": key, "instrument_name": dataset["name"],
            "endpoint_id": endpoint["endpoint_id"], "endpoint_url": endpoint["url"],
            "file_count": len(files), "files": files,
            "limits": {"max_files": self.max_download_files, "max_total_bytes": self.max_download_bytes},
        }

    def _new_request_id(self) -> str:
        return "piportal-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]

    def _request_dir(self, request_id: str) -> Path:
        if not REQUEST_ID_RE.fullmatch(request_id):
            raise ValueError("Invalid PI portal request ID")
        root = (self.runtime_root / "requests").resolve()
        target = (root / request_id).resolve()
        if target.parent != root:
            raise ValueError("PI portal request path escaped the runtime root")
        return target

    @staticmethod
    def _write_json_atomic(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="manifest-", suffix=".json", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def download_files(self, instrument_id: str, relative_paths: list[str], endpoint_id: str | None = None) -> dict:
        plan = self.plan_download(instrument_id, relative_paths, endpoint_id)
        request_id = self._new_request_id()
        request_dir = self._request_dir(request_id)
        file_dir = (request_dir / "files").resolve()
        file_dir.mkdir(parents=True, exist_ok=False)
        downloaded: list[dict[str, Any]] = []
        total_bytes = 0
        try:
            for item in plan["files"]:
                remaining = self.max_download_bytes - total_bytes
                if remaining <= 0:
                    raise PIPortalError(f"Download exceeds configured {self.max_download_bytes} byte total limit")
                status, headers, body, final = self._http(item["source_url"], remaining)
                if status == 404:
                    raise PIPortalError(f"PI portal file was not found: {item['relative_path']}")
                if status < 200 or status >= 300:
                    raise PIPortalError(f"PI portal returned HTTP {status} for {item['relative_path']}")
                total_bytes += len(body)
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", posixpath.basename(item["relative_path"])) or "download.bin"
                prefix = hashlib.sha256(item["relative_path"].encode("utf-8")).hexdigest()[:12]
                target = (file_dir / f"{prefix}-{safe_name}").resolve()
                if target.parent != file_dir:
                    raise ValueError("Download path escaped request directory")
                target.write_bytes(body)
                downloaded.append({
                    "relative_path": item["relative_path"], "source_url": final,
                    "file": str(target), "filename": target.name,
                    "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                    "content_type": headers.get("Content-Type"),
                })
        except Exception as exc:
            failure_manifest = {
                "schema_version": "1.0", "status": "failed", "local_request_id": request_id,
                "retrieved_at_utc": _now(), "instrument_id": plan["instrument_id"],
                "instrument_name": plan["instrument_name"], "endpoint_id": plan["endpoint_id"],
                "endpoint_url": plan["endpoint_url"], "credential_used": False,
                "file_count": len(downloaded), "total_bytes": total_bytes, "files": downloaded,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            manifest_path = request_dir / "manifest.json"
            self._write_json_atomic(manifest_path, failure_manifest)
            return _error(type(exc).__name__, str(exc), local_request_id=request_id,
                          manifest=str(manifest_path), files_downloaded=downloaded)
        manifest = {
            "schema_version": "1.0", "status": "complete", "local_request_id": request_id,
            "retrieved_at_utc": _now(), "instrument_id": plan["instrument_id"],
            "instrument_name": plan["instrument_name"], "endpoint_id": plan["endpoint_id"],
            "endpoint_url": plan["endpoint_url"], "credential_used": False,
            "file_count": len(downloaded), "total_bytes": total_bytes, "files": downloaded,
        }
        manifest_path = request_dir / "manifest.json"
        self._write_json_atomic(manifest_path, manifest)
        return {"ok": True, **manifest, "manifest": str(manifest_path)}


PI_PORTAL_TOOL_SCHEMAS = [
    {"name": "pi_portal_status", "description": "Report public UW RCA PI portal readiness, exact-host security policy, audited dataset count, runtime location, and download limits. No credentials are used.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pi_portal_list_instruments", "description": "List the ten audited RCA PI datasets and every known public PI portal download location. Use the Graph-RAG corpus first for availability answers.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "pi_portal_browse", "description": "Browse one bounded directory under an audited RCA PI dataset endpoint on piweb.ooirsn.uw.edu.", "inputSchema": {"type": "object", "required": ["instrument_id"], "properties": {"instrument_id": {"type": "string", "enum": list(PI_DATASETS)}, "endpoint_id": {"type": "string"}, "relative_path": {"type": "string", "default": ""}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000, "default": 500}}}},
    {"name": "pi_portal_find_files", "description": "Recursively find current files within one audited PI endpoint using bounded depth, directory, and result limits; optionally filter filename, extension, and dates encoded in paths.", "inputSchema": {"type": "object", "required": ["instrument_id"], "properties": {"instrument_id": {"type": "string", "enum": list(PI_DATASETS)}, "endpoint_id": {"type": "string"}, "relative_path": {"type": "string", "default": ""}, "pattern": {"type": "string"}, "extensions": {"type": "array", "items": {"type": "string"}}, "start": {"type": "string", "format": "date"}, "end": {"type": "string", "format": "date"}, "max_depth": {"type": "integer", "minimum": 0, "maximum": 10, "default": 3}, "max_directories": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}, "max_files": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1000}}}},
    {"name": "pi_portal_plan_download", "description": "Validate PI portal file paths and show exact source URLs and limits without making a network request or writing files.", "inputSchema": {"type": "object", "required": ["instrument_id", "relative_paths"], "properties": {"instrument_id": {"type": "string", "enum": list(PI_DATASETS)}, "endpoint_id": {"type": "string"}, "relative_paths": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}},
    {"name": "pi_portal_download_files", "description": "Download a bounded set of selected files from one audited PI endpoint into runtime_data/PIPortal and write a provenance manifest with source URLs, timestamps, byte counts, and SHA-256 hashes.", "inputSchema": {"type": "object", "required": ["instrument_id", "relative_paths"], "properties": {"instrument_id": {"type": "string", "enum": list(PI_DATASETS)}, "endpoint_id": {"type": "string"}, "relative_paths": {"type": "array", "items": {"type": "string"}, "minItems": 1}}}},
]


def dispatch_pi_portal(toolkit: PIPortalToolkit, name: str, arguments: dict) -> dict:
    calls = {
        "pi_portal_status": lambda: toolkit.status(),
        "pi_portal_list_instruments": lambda: toolkit.list_instruments(**arguments),
        "pi_portal_browse": lambda: toolkit.browse(**arguments),
        "pi_portal_find_files": lambda: toolkit.find_files(**arguments),
        "pi_portal_plan_download": lambda: toolkit.plan_download(**arguments),
        "pi_portal_download_files": lambda: toolkit.download_files(**arguments),
    }
    if name not in calls:
        return _error("unknown_tool", name)
    try:
        return calls[name]()
    except Exception as exc:
        return _error(type(exc).__name__, str(exc))
