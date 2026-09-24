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


def _slice_by_distance(coords: list[list[float]], start_m: float, end_m: float, coordinate_max_m: float) -> list[list[float]]:
    """Map a documented DAS distance interval onto a cable centerline schematic."""
    lengths = [0.0]
    for a, b in zip(coords, coords[1:]):
        lengths.append(lengths[-1] + _km(a, b) * 1000)
    total = lengths[-1]
    target_a, target_b = total * start_m / coordinate_max_m, total * end_m / coordinate_max_m
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


def build(data, cable: dict) -> dict:
    conventional = _conventional(data)
    coverage = load_jsonl(data / "OOIDASGeometry" / "multidas_unmasked_coverage.jsonl")
    multi = []
    for item in coverage:
        centerline = _backbone(cable, item["cable"])
        for i, interval in enumerate(item["saved_unmasked_intervals_m"], 1):
            multi.append({"id": f"multidas-{item['cable']}-{i}", "experiment": "2025–2026 Nokia MultiDAS", "kind": "multidas",
                          "cable": item["cable"], "coords": _slice_by_distance(centerline, interval["start_m"], interval["end_m"], item["maximum_saved_distance_m"]),
                          "color": COLORS["multidas"], "distance": interval,
                          "detail": f"Saved unmasked interval {interval['start_m']/1000:g}–{interval['end_m']/1000:g} km ({interval['length_m']/1000:g} km).",
                          "caveat": "Schematic on the mapped backbone: MultiDAS mask distances are documented, but exact channel coordinates were not published."})
    south = _backbone(cable, "south")
    # The official project page documents OptoDAS on the first south-cable span; no channel-coordinate file exists.
    opto = [{"id": "optodas-south-first-span", "experiment": "2025–2026 OptoDAS", "kind": "optodas", "cable": "south",
             "coords": south[:101], "color": COLORS["optodas"], "detail": "Documented first south-cable span.",
             "caveat": "Schematic first-span extent; published materials do not supply OptoDAS channel coordinates."}]
    return {"layers": conventional + multi + opto,
            "summary": {"conventional": "2021 OptaSense geometry", "multidas": "2025–2026 unmasked spans", "optodas": "2025–2026 south first span"}}
