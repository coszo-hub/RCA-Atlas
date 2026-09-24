"""Build the atlas bundle.

  python -m atlas_map_data.build_atlas_bundle                     # offline build from caches
  python -m atlas_map_data.build_atlas_bundle --refresh-terrain   # download GMRT grids first
  python -m atlas_map_data.build_atlas_bundle --refresh-external  # refresh ERDDAP + QA/QC coverage first
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import access, cable, families, paths, sensors, sites, status, terrain, validate
from .corpus import load_jsonl


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _vertical_channels(data: Path) -> dict[str, str]:
    best: dict[str, str] = {}
    for ch in load_jsonl(data / "StationMetadata" / "channels.jsonl"):
        key, code = f"{ch['network']}.{ch['station']}", ch["channel"] or ""
        for preferred in ("HHZ", "BHZ", "EHZ", "SHZ"):
            if code == preferred and (key not in best or ["HHZ", "BHZ", "EHZ", "SHZ"].index(preferred)
                                      < ["HHZ", "BHZ", "EHZ", "SHZ"].index(best[key])):
                best[key] = code
    return best


def _pi_endpoints(data: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ep in load_jsonl(data / "PIPortal" / "endpoints.jsonl"):
        out.setdefault(ep["instrument_id"], []).append(ep)
    return out


def build(out: Path, runtime: Path, data: Path) -> dict:
    rows = load_jsonl(data / "Instruments" / "instruments.jsonl")
    records = [sensors.sensor_from_row(r) for r in rows]
    fetch_rows = load_jsonl(data / "FETCH" / "instruments.jsonl") if (data / "FETCH" / "instruments.jsonl").exists() else []
    records.extend(sensors.sensor_from_fetch_row(r) for r in fetch_rows)
    sensors.apply_corrections(records, sensors.load_corrections(paths.PACKAGE / "corrections.json"))

    index = status.load_status_index(load_jsonl(data / "Nereus" / "graphrag" / "entities.jsonl"),
                                     load_jsonl(data / "Nereus" / "graphrag" / "instrument_crosswalk.jsonl"))
    external = access.load_external(runtime)
    pi = _pi_endpoints(data)
    channels = _vertical_channels(data)
    for r in records:
        if not r.get("status"):
            r.update(status.resolve(r, index))
        r["statusGroup"] = status.STATUS_GROUP.get(r["status"])   # unknown values fail in validate
        if not r.get("access"):
            r["access"] = access.build_access(r, external, pi, channels)

    grids = {n: terrain.read_esri_ascii(runtime / "terrain" / f"{n}.asc", n) for n in terrain.FINEST_FIRST}
    stack = terrain.Stack([grids[n] for n in terrain.FINEST_FIRST])
    located = [r for r in records if validate.is_located(r)]
    unlocated = [r for r in records if not validate.is_located(r)]
    site_list, unplaced = sites.build_sites(located, unlocated, stack.elev)
    errors = validate.validate(records, site_list, unplaced, len(records), stack)

    if not errors:
        _write(out / "families.json", {"families": families.FAMILIES})
        _write(out / "sensors.json", {"sensors": records, "unplaced": [u["id"] for u in unplaced]})
        _write(out / "sites.json", {"sites": site_list})
        _write(out / "regions.json", {"overview": sites.OVERVIEW_VIEW, "regions": sites.REGIONS})
        _write(out / "cable.json", cable.load_cable(paths.PACKAGE / "cable" / "rca_cable.geojson"))
        for n, g in grids.items():
            (out / "terrain").mkdir(parents=True, exist_ok=True)
            terrain.write_bin(g, out / "terrain" / f"{n}.bin")
        _write(out / "terrain" / "terrain.json", {"credit": terrain.CREDIT, "grids": {n: g.meta() for n, g in grids.items()}})
    summary = {"builtAt": datetime.now(timezone.utc).isoformat(), "total": len(records), "located": len(located),
               "unlocated": len(unlocated), "unplaced": len(unplaced), "sites": len(site_list),
               "corpusSnapshot": json.loads((data / "Instruments" / "manifest.json").read_text()).get("created_at")
               if (data / "Instruments" / "manifest.json").exists() else None,
               "warnings": external["warnings"], "errors": errors}
    if not errors:
        _write(out / "manifest.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=paths.BUNDLE)
    ap.add_argument("--refresh-terrain", action="store_true")
    ap.add_argument("--refresh-external", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh_terrain:
        for name in terrain.FINEST_FIRST:
            print(f"downloading GMRT {name} …", flush=True)
            terrain.fetch_gmrt(name, paths.RUNTIME / "terrain")
    if args.refresh_external:
        print(f"ERDDAP datasets: {access.refresh_erddap(paths.RUNTIME)}")
        print(f"EarthScope OO stations: {access.refresh_earthscope(paths.RUNTIME)}")
        sys.path.insert(0, str(paths.REPO / "src" / "agentic_qaqc"))
        from qaqc_agent_tools import QAQCToolkit  # his toolkit; stdlib only
        print(f"QA/QC reference designators: {access.refresh_qaqc(paths.RUNTIME, QAQCToolkit().get_index())}")
    summary = build(args.out, paths.RUNTIME, paths.DATA)
    for w in summary["warnings"]:
        print(f"warning: {w}")
    for e in summary["errors"]:
        print(f"error: {e}")
    if summary["errors"]:
        print(f"build failed with {len(summary['errors'])} errors; nothing written")
        return 1
    print(f"wrote {args.out}: {summary['total']} sensors ({summary['located']} located), {summary['sites']} sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
