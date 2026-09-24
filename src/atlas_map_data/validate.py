"""Bundle checks. Any returned string fails the build."""
from __future__ import annotations

from .status import STATUS_GROUP

TOLERANCE_M = 250


def is_located(sensor: dict) -> bool:
    """A position counts only when both coordinates are set; corrections may null a placeholder position."""
    return sensor.get("lat") is not None and sensor.get("lon") is not None


def validate(sensors: list[dict], sites: list[dict], unplaced: list[dict], total_rows: int, stack) -> list[str]:
    errors = []
    located = [s for s in sensors if is_located(s)]
    unlocated = [s for s in sensors if not is_located(s)]
    if len(located) + len(unlocated) != total_rows:
        errors.append(f"counts do not reconcile: {len(located)} located + {len(unlocated)} unlocated != {total_rows} inventory rows")
    site_ids = {t["id"] for t in sites}
    listed = {i for t in sites for i in t["sensorIds"] + t["unlocatedIds"]} | {u["id"] for u in unplaced}
    for s in sensors:
        if s["id"] not in listed:
            errors.append(f"{s['id']}: not listed by any site or as unplaced")
        if is_located(s) and s.get("site") not in site_ids:
            errors.append(f"{s['id']}: site {s.get('site')!r} does not exist")
        if not s.get("family"):
            errors.append(f"{s['id']}: no family")
        if s.get("status") not in STATUS_GROUP:
            errors.append(f"{s['id']}: unrecognised Nereus status {s.get('status')!r}; add it to status.STATUS_GROUP")
        if (s.get("lat") is None) != (s.get("lon") is None):
            errors.append(f"{s['id']}: position is half set (lat {s.get('lat')}, lon {s.get('lon')})")
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
