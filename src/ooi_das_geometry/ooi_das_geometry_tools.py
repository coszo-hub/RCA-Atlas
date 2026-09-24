"""Bounded lookups for published OOI RCA DAS channel geography and masks."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "data/OOIDASGeometry"


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"DAS geometry corpus file is unavailable: {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _distance_m(latitude: float, longitude: float, row: dict[str, Any]) -> float:
    radius = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(math.radians, (latitude, longitude, row["latitude"], row["longitude"]))
    a = math.sin((lat2-lat1)/2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2-lon1)/2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class OoiDasGeometryToolkit:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or DEFAULT_ROOT)
        self._locations: list[dict[str, Any]] | None = None
        self._coverage: list[dict[str, Any]] | None = None

    @property
    def locations(self) -> list[dict[str, Any]]:
        if self._locations is None:
            self._locations = _rows(self.root / "channel_locations.jsonl")
        return self._locations

    @property
    def coverage(self) -> list[dict[str, Any]]:
        if self._coverage is None:
            self._coverage = _rows(self.root / "multidas_unmasked_coverage.jsonl")
        return self._coverage

    def channel_location(self, cable: str, channel_number: int) -> dict[str, Any]:
        cable = cable.casefold()
        matches = [row for row in self.locations if row["cable"] == cable and row["channel_number"] == int(channel_number)]
        if not matches:
            return {"ok": False, "error": "not_found", "message": "No published OptaSense channel location matches that cable and channel."}
        row = matches[0]
        return {"ok": True, "location": row, "provenance": {"source_url": row["source_url"], "source_file_sha256": row["source_file_sha256"]}}

    def nearest_channel(self, cable: str, latitude: float, longitude: float) -> dict[str, Any]:
        cable = cable.casefold()
        if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
            raise ValueError("latitude/longitude must be valid WGS84 coordinates")
        candidates = [row for row in self.locations if row["cable"] == cable]
        if not candidates:
            return {"ok": False, "error": "not_found", "message": "Unknown cable; use north or south."}
        row = min(candidates, key=lambda candidate: _distance_m(float(latitude), float(longitude), candidate))
        return {"ok": True, "location": row, "distance_to_channel_m": _distance_m(float(latitude), float(longitude), row),
                "provenance": {"source_url": row["source_url"], "source_file_sha256": row["source_file_sha256"]}}

    def multidas_unmasked_spans(self, cable: str) -> dict[str, Any]:
        cable = cable.casefold()
        rows = [row for row in self.coverage if row.get("cable") == cable]
        if not rows:
            return {"ok": False, "error": "not_found", "message": "No sampled MultiDAS mask metadata matches that cable."}
        return {"ok": True, "cable": cable, "records": rows,
                "warning": "Masks are file-specific. Select a record matching the requested acquisition time before use."}


TOOL_SCHEMAS = [
    {"name": "ooi_das_channel_location", "description": "Return the published preliminary OptaSense DAS channel location, depth, campaign dates, and source checksum for a north or south RCA cable channel.", "inputSchema": {"type": "object", "required": ["cable", "channel_number"], "properties": {"cable": {"type": "string", "enum": ["north", "south"]}, "channel_number": {"type": "integer", "minimum": 0}}}},
    {"name": "ooi_das_nearest_channel", "description": "Find the nearest published preliminary OptaSense DAS channel to a WGS84 location on a specified RCA cable.", "inputSchema": {"type": "object", "required": ["cable", "latitude", "longitude"], "properties": {"cable": {"type": "string", "enum": ["north", "south"]}, "latitude": {"type": "number", "minimum": -90, "maximum": 90}, "longitude": {"type": "number", "minimum": -180, "maximum": 180}}}},
    {"name": "ooi_das_multidas_unmasked_spans", "description": "Return exact saved/unmasked along-cable intervals from sampled DAS25 MultiDAS file headers. Use for requested data availability or analysis; masks vary by file.", "inputSchema": {"type": "object", "required": ["cable"], "properties": {"cable": {"type": "string", "enum": ["north", "south"]}}}},
]


def dispatch(toolkit: OoiDasGeometryToolkit, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    calls = {"ooi_das_channel_location": toolkit.channel_location, "ooi_das_nearest_channel": toolkit.nearest_channel,
             "ooi_das_multidas_unmasked_spans": toolkit.multidas_unmasked_spans}
    if name not in calls:
        return {"ok": False, "error": "unknown_tool", "message": name}
    try:
        return calls[name](**arguments)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}
