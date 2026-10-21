"""DAS experiment overlays for the Atlas map.

The conventional 2021 layer uses its published OptaSense channel geometry.
MultiDAS exposes only documented unmasked distance intervals.  Its coordinates
were not published, so those intervals are projected *schematically* along the
researched RCA backbone, never presented as a channel-location map.
"""
from __future__ import annotations

import math

from .corpus import load_jsonl


COLORS = {"conventional": "#a98cff", "multidas": "#ffbd59", "optodas": "#62d7d2"}


def _km(a, b):
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 111.13)


def _backbone(cable: dict, name: str) -> list[list[float]]:
    pts = []
    for line in cable["lines"]:
        if line["kind"] != f"{name.title()} backbone":
            continue
        for p in line["coords"]:
            if not pts or p != pts[-1]:
                pts.append(p)
    return pts


def _slice_by_distance(coords: list[list[float]], start_m: float, end_m: float) -> list[list[float]]:
    """Map a documented DAS distance interval onto a cable centerline schematic.

    MultiDAS distances are cable-distance coordinates from the shore-side end;
    never stretch the last saved coordinate to an entire backbone. In
    particular, north 300 km does not reach Axial on the ~500 km mapped route.
    """
    lengths = [0.0]
    for a, b in zip(coords, coords[1:]):
        lengths.append(lengths[-1] + _km(a, b) * 1000)
    total = lengths[-1]
    target_a, target_b = min(start_m, total), min(end_m, total)
    out = []
    for i, (a, b) in enumerate(zip(coords, coords[1:])):
        lo, hi = lengths[i], lengths[i + 1]
        if hi < target_a or lo > target_b:
            continue
        for d in (max(lo, target_a), min(hi, target_b)):
            t = 0 if hi == lo else (d - lo) / (hi - lo)
            p = [round(a[0] + (b[0] - a[0]) * t, 6), round(a[1] + (b[1] - a[1]) * t, 6)]
            if not out or out[-1] != p:
                out.append(p)
    return out


def _conventional(data) -> list[dict]:
    out = []
    for cable in ("north", "south"):
        rows = [r for r in load_jsonl(data / "OOIDASGeometry" / "channel_locations.jsonl") if r["cable"] == cable]
        # Fifty 2 m channels is a 100 m sample interval: sufficient visually without shipping ~78k points.
        points = [[r["longitude"], r["latitude"]] for r in rows[::50]]
        if rows and points[-1] != [rows[-1]["longitude"], rows[-1]["latitude"]]:
            points.append([rows[-1]["longitude"], rows[-1]["latitude"]])
        if rows:
            out.append({"id": f"conventional-{cable}", "experiment": "2021 conventional DAS", "kind": "conventional",
                        "cable": cable, "coords": points, "color": COLORS["conventional"],
                        "detail": f"OptaSense QuantX published channel geometry; channels {rows[0]['channel_number']:,}–{rows[-1]['channel_number']:,} at 2 m spacing.",
                        "caveat": "Applies to OptaSense channel geometry; it is not an asserted Silixa channel map."})
    return out


FIRST_SOUTH_REPEATER_M = 95_000   # "the first optical repeater on the South cable ... about 95 km offshore" (OOI)


def _distance_to(coords: list[list[float]], point: list[float]) -> float:
    """Metres along a centerline to its vertex nearest `point`."""
    along, best = 0.0, (float("inf"), 0.0)
    for i, p in enumerate(coords):
        if i:
            along += _km(coords[i - 1], p) * 1000
        best = min(best, (_km(p, point), along))
    return best[1]


def first_south_span(south: list[list[float]], conventional: list[dict]) -> list[list[float]]:
    """The south cable from shore to its first optical repeater, where the 2024 multiplexed DAS and 2025-26 OptoDAS
    observed. It ends where the 2021 OptaSense south-cable channel geometry ends, at that same repeater; ~95 km
    when the geometry is missing. (This was the backbone's first 101 vertices, which ran 204 km to Slope Base.)"""
    end = next((l["coords"][-1] for l in conventional if l["cable"] == "south" and l["coords"]), None)
    return _slice_by_distance(south, 0, _distance_to(south, end) if end else FIRST_SOUTH_REPEATER_M)


def build(data, cable: dict) -> dict:
    conventional = _conventional(data)
    coverage = load_jsonl(data / "OOIDASGeometry" / "multidas_unmasked_coverage.jsonl")
    multi = []
    for item in coverage:
        centerline = _backbone(cable, item["cable"])
        for i, interval in enumerate(item["saved_unmasked_intervals_m"], 1):
            multi.append({"id": f"multidas-{item['cable']}-{i}", "experiment": "2025–2026 Nokia MultiDAS", "kind": "multidas",
                          "cable": item["cable"], "coords": _slice_by_distance(centerline, interval["start_m"], interval["end_m"]),
                          "color": COLORS["multidas"], "distance": interval,
                          "detail": f"Saved unmasked interval {interval['start_m']/1000:g}–{interval['end_m']/1000:g} km ({interval['length_m']/1000:g} km).",
                          "caveat": "Schematic on the mapped backbone at the documented shore-distance coordinate; exact MultiDAS channel coordinates were not published."})
    south = _backbone(cable, "south")
    # The official project page documents OptoDAS on the first south-cable span; no channel-coordinate file exists.
    opto = [{"id": "optodas-south-first-span", "experiment": "OptoDAS, south cable first span (2024 multiplexed DAS; 2025–26 OptoDAS)",
             "kind": "optodas", "cable": "south", "coords": first_south_span(south, conventional), "color": COLORS["optodas"],
             "detail": "South cable from shore to the first optical repeater (~95 km offshore).",
             "caveat": "Schematic along the mapped backbone; it ends where the 2021 south-cable channel geometry reaches that repeater. OptoDAS channel coordinates were not published."}]
    return {"layers": conventional + multi + opto,
            "summary": {"conventional": "2021 OptaSense geometry", "multidas": "2025–2026 unmasked spans", "optodas": "2025–2026 south first span"}}
