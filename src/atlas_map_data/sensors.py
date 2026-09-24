"""Inventory rows → atlas sensor records, with profiler depth ranges and reviewed corrections."""
from __future__ import annotations

import json
from pathlib import Path

from .families import family_for

# OOI node prefixes for moorings that sample the water column. Depths in meters.
COLUMN_KIND = {"SF": "Shallow profiler", "PC": "200 m platform", "DP": "Deep profiler"}


def depth_range(node: str | None, water_depth: float | None) -> list[int] | None:
    prefix = (node or "")[:2]
    if prefix == "SF":
        return [5, 200]
    if prefix == "PC":
        return [200, 200]
    if prefix == "DP" and water_depth:
        return [250, int(round(water_depth)) - 150]
    return None


def sensor_from_row(row: dict) -> dict:
    site, node, code = row.get("site"), row.get("node"), row.get("instrument_code")
    refdes = f"{site}-{node}-{code}" if site and node and code else None
    water = row.get("depth_m")
    rng = depth_range(node, water)
    return {
        "id": row["canonical_id"],
        "instrumentId": row["instrument_id"],
        "name": row["name"],
        "type": row["instrument_type"],
        "family": family_for(row["instrument_type"]),
        "lat": row.get("latitude"),
        "lon": row.get("longitude"),
        "depth": rng[0] if rng else water,
        "depthRange": rng,
        "waterDepth": water,
        "siteCode": site,
        "node": node,
        "refdes": refdes,
        "location": row.get("location"),
        "projects": row.get("projects") or [],
        "coszoRole": row.get("coszo_role"),
        "manufacturer": row.get("manufacturer"),
        "model": row.get("model"),
        "sources": list(row.get("source_urls") or []),
        "arcadaId": row.get("arcada_document_id"),
        "corrections": [],
    }


FETCH_RAW_DATA_URL = "https://github.com/MaleenKidiwela/AxialFetch/tree/dbd132197b484490488fe16173df63140bb0ed22/Data"
FETCH_DISTANCE_DATA_URL = "https://github.com/MaleenKidiwela/AxialFetch/tree/dbd132197b484490488fe16173df63140bb0ed22/src/output/distances"


def sensor_from_fetch_row(row: dict) -> dict:
    """Map-ready record for a documented FETCH station.

    FETCH has no OOI reference designator, so it intentionally has no Nereus,
    ERDDAP, or QA/QC route. Its repository publishes raw station records and
    processed baseline distances instead.
    """
    return {
        "id": row["canonical_id"], "instrumentId": row["instrument_id"], "name": row["name"],
        "type": row["instrument_type"], "family": family_for(row["instrument_type"]),
        "lat": row.get("latitude"), "lon": row.get("longitude"), "depth": None,
        "depthRange": None, "waterDepth": None, "siteCode": "FETCH", "node": None,
        "refdes": None, "location": row.get("location"), "projects": row.get("projects") or [],
        "coszoRole": None, "manufacturer": None, "model": None,
        "sources": list(row.get("source_urls") or []), "arcadaId": None, "corrections": [],
        "status": "UNKNOWN", "statusSource": "FETCH source snapshot", "statusAsOf": None,
        "access": [
            {"kind": "repository", "label": "FETCH raw station data", "url": FETCH_RAW_DATA_URL,
             "how": "Raw station records for the three acoustic ranging stations."},
            {"kind": "repository", "label": "FETCH processed baseline distances", "url": FETCH_DISTANCE_DATA_URL,
             "how": "Calibrated inter-station acoustic baseline-distance products."},
        ],
    }


def load_corrections(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["corrections"]


def _matches(record: dict, match: dict) -> bool:
    return all(record.get(field) in values for field, values in match.items())


def apply_corrections(records: list[dict], corrections: list[dict]) -> None:
    for fix in corrections:
        hits = [r for r in records if _matches(r, fix["match"])]
        if not hits:
            raise ValueError(f"correction matched no sensors: {fix['match']}")
        for r in hits:
            r.update(fix["set"])
            r["corrections"].append(fix["reason"])
