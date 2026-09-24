"""Physical sites (sensors within 150 m), regions, and water-column reach."""
from __future__ import annotations

import math
import re
from typing import Callable

from .sensors import COLUMN_KIND

KX = 111.32 * math.cos(math.radians(45.15))
KZ = 111.13
SITE_RADIUS_KM = 0.15

REGIONS = [
    {"key": "axial", "label": "Axial Seamount", "lonMin": -180.0, "lonMax": -129.0,
     "view": {"ll": [-129.885, 45.885], "dist": 62, "polar": 0.72, "az": -0.3, "exag": 3}},
    {"key": "slope", "label": "Oregon Slope Base", "lonMin": -129.0, "lonMax": -125.3,
     "view": {"ll": [-125.39, 44.51], "dist": 14, "polar": 0.95, "az": -0.4, "exag": 2.5}},
    {"key": "hydrate", "label": "Hydrate Ridge", "lonMin": -125.3, "lonMax": -124.9,
     "view": {"ll": [-125.12, 44.57], "dist": 22, "polar": 0.92, "az": -0.4, "exag": 2.5}},
    {"key": "shelf", "label": "Oregon Shelf", "lonMin": -124.9, "lonMax": 0.0,
     "view": {"ll": [-124.62, 44.56], "dist": 95, "polar": 0.86, "az": -0.25, "exag": 4}},
]
OVERVIEW_VIEW = {"ll": [-126.75, 45.02], "dist": 650, "polar": 0.84, "az": 0.0, "exag": 6}


def region_for(lon: float) -> str:
    for r in REGIONS:
        if r["lonMin"] <= lon < r["lonMax"]:
            return r["key"]
    raise ValueError(f"longitude {lon} is outside every region")


def _km(a: dict, b: dict) -> float:
    return math.hypot((a["lon"] - b["lon"]) * KX, (a["lat"] - b["lat"]) * KZ)


def _in_water(sensor: dict, seafloor: float) -> bool:
    return bool(sensor.get("depthRange")) or (sensor.get("depth") is not None and sensor["depth"] < seafloor - 60)


def _label(name: str) -> str:
    return name.replace(", Axial Seamount", "").replace("Axial Seamount ", "Axial ")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_sites(located: list[dict], unlocated: list[dict],
                elev: Callable[[float, float], float]) -> tuple[list[dict], list[dict]]:
    clusters: list[list[dict]] = []
    for sensor in sorted(located, key=lambda x: (x["lat"], x["lon"], x["id"])):
        home = next((c for c in clusters if any(_km(sensor, m) < SITE_RADIUS_KM for m in c)), None)
        if home is None:
            clusters.append([sensor])
        else:
            home.append(sensor)

    result, used_ids = [], set()
    for members in clusters:
        lat = sum(m["lat"] for m in members) / len(members)
        lon = sum(m["lon"] for m in members) / len(members)
        seafloor = int(round(-elev(lon, lat)))
        weights: dict[str, int] = {}
        for m in members:
            name = m.get("location") or m.get("siteCode") or "Unnamed site"
            weights[name] = weights.get(name, 0) + (1 if _in_water(m, seafloor) else 100)
        name = max(weights, key=lambda k: (weights[k], k))
        parts = list(dict.fromkeys(m.get("location") or m.get("siteCode") or "Unnamed site" for m in members))
        column: dict[str, list[int]] = {}
        for m in members:
            if not _in_water(m, seafloor):
                continue
            kind = COLUMN_KIND.get((m.get("node") or "")[:2], "Water-column sensor")
            a, b = m["depthRange"] or [m["depth"], m["depth"]]
            column[kind] = [min(column[kind][0], a), max(column[kind][1], b)] if kind in column else [a, b]
        base_id = _slug(name)
        site_id = base_id
        n = 2
        while site_id in used_ids:
            site_id, n = f"{base_id}-{n}", n + 1
        used_ids.add(site_id)
        region = region_for(lon)
        for m in members:
            m["site"], m["region"] = site_id, region
        result.append({
            "id": site_id, "name": name, "label": _label(name), "region": region,
            "lat": round(lat, 6), "lon": round(lon, 6), "seafloor": seafloor,
            "sensorIds": [m["id"] for m in members], "parts": parts,
            "column": sorted(({"kind": k, "a": v[0], "b": v[1]} for k, v in column.items()), key=lambda c: c["a"]),
            "unlocatedIds": [],
        })

    unplaced = []
    for u in unlocated:
        home = next((t for t in result if any(
            (u.get("siteCode") and m.get("siteCode") == u["siteCode"]) or
            (u.get("location") and m.get("location") == u["location"])
            for m in located if m["site"] == t["id"])), None)
        if home:
            home["unlocatedIds"].append(u["id"])
            u["site"], u["region"] = home["id"], home["region"]
        else:
            unplaced.append(u)
    return result, unplaced
