"""Bundle checks. Any returned string fails the build."""
from __future__ import annotations

TOLERANCE_M = 250


def validate(sensors: list[dict], sites: list[dict], unplaced: list[dict], total_rows: int, stack) -> list[str]:
    errors = []
    located = [s for s in sensors if s.get("lat") is not None]
    unlocated = [s for s in sensors if s.get("lat") is None]
    if len(located) + len(unlocated) != total_rows:
        errors.append(f"counts do not reconcile: {len(located)} located + {len(unlocated)} unlocated != {total_rows} inventory rows")
    site_ids = {t["id"] for t in sites}
    listed = {i for t in sites for i in t["sensorIds"] + t["unlocatedIds"]} | {u["id"] for u in unplaced}
    for s in sensors:
        if s["id"] not in listed:
            errors.append(f"{s['id']}: not listed by any site or as unplaced")
        if s.get("lat") is not None and s.get("site") not in site_ids:
            errors.append(f"{s['id']}: site {s.get('site')!r} does not exist")
        if not s.get("family"):
            errors.append(f"{s['id']}: no family")
    for s in located:
        if not stack.covered(s["lon"], s["lat"]):
            errors.append(f"{s['id']}: position {s['lat']}, {s['lon']} is outside every terrain grid")
            continue
        checked = s.get("waterDepth") if s.get("depthRange") else s.get("depth")
        if checked is None or s.get("corrections"):
            continue
        seafloor = -stack.elev(s["lon"], s["lat"])
        if abs(checked - seafloor) > TOLERANCE_M:
            errors.append(f"{s['id']}: listed depth {checked:,.0f} m differs from the seafloor ({seafloor:,.0f} m) "
                          f"by {abs(checked - seafloor):,.0f} m; add a reviewed entry to corrections.json")
    return errors
