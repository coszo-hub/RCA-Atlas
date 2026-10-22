"""Offshore Quaternary faults → the atlas fault file.

  python -m atlas_map_data.faults --refresh    # download the USGS traces in the atlas area into faults/qfaults.geojson

The traces are the USGS Quaternary Fault and Fold Database (public domain), cut to the overview terrain. The build
keeps the faults that lie offshore and drops folds (anticlines, synclines, monoclines) and the Cascadia fold and
fault belt, whose hundreds of short accretionary-wedge thrusts would bury the faults named here.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from . import paths

QFAULTS = "https://earthquake.usgs.gov/arcgis/rest/services/haz/Qfaults/MapServer/21/query"
BBOX = (-130.7, 43.9, -123.6, 46.4)   # west, south, east, north: the overview terrain and a margin
FIELDS = "fault_name,fault_id,section_name,age,slip_sense,slip_rate,linetype,dip_direction,mapped_scale,fault_url"
SOURCE = paths.PACKAGE / "faults" / "qfaults.geojson"
CREDIT = "Faults: USGS Quaternary Fault and Fold Database (public domain)"
FOLDS = {"Anticline", "Syncline", "Monocline"}
SEAFLOOR_M = -50.0   # below this the line is on the seafloor, not in a bay or estuary (Tillamook Bay, Yaquina)
DROPPED = {"784": "Cascadia fold and fault belt"}
MEGATHRUST = "781"
# Where a fault's USGS line is not the fault itself.
NOTES = {MEGATHRUST: "Drawn at the deformation front, where the megathrust between the Juan de Fuca and North "
                     "American plates reaches the seafloor; the fault dips east beneath the margin."}


def refresh(dest: Path = SOURCE, urlopen=urllib.request.urlopen) -> int:
    q = urllib.parse.urlencode({
        "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": FIELDS, "f": "geojson"})
    req = urllib.request.Request(f"{QFAULTS}?{q}", headers={"User-Agent": "rca-atlas"})
    with urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("exceededTransferLimit"):
        raise RuntimeError("USGS returned a partial result; page the query")
    for f in data["features"]:      # metre precision; the source maps at 1:250,000 or coarser
        g = f.get("geometry")
        if g:
            g["coordinates"] = [[round(x, 5), round(y, 5)] for x, y in g["coordinates"]] if g["type"] == "LineString" \
                else [[[round(x, 5), round(y, 5)] for x, y in part] for part in g["coordinates"]]
    data["source"] = f"{QFAULTS}?{q}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, separators=(",", ":")))
    return len(data["features"])


def _parts(geometry: dict) -> list[list]:
    return [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]


def _runs(coords: list, covered) -> list[list]:
    """The stretches of a line inside the terrain, two points or more."""
    runs, run = [], []
    for c in coords:
        if covered(c[0], c[1]):
            run.append([round(c[0], 5), round(c[1], 5)])
        else:
            if len(run) > 1:
                runs.append(run)
            run = []
    if len(run) > 1:
        runs.append(run)
    return runs


def load_faults(path: Path, covered, elev) -> dict:
    """covered(lon, lat): inside the overview terrain; elev(lon, lat): its elevation, metres (negative below sea level)."""
    faults: dict[str, dict] = {}
    for f in json.loads(path.read_text())["features"]:
        p = f["properties"]
        if p["slip_sense"] in FOLDS or p["fault_id"] in DROPPED or not f.get("geometry"):
            continue
        for coords in _parts(f["geometry"]):
            for run in _runs(coords, covered):
                below = sum(elev(x, y) < SEAFLOOR_M for x, y in run)
                if below * 2 <= len(run):          # mostly on land or in a bay
                    continue
                fault = faults.setdefault(p["fault_id"], {
                    "id": p["fault_id"], "name": p["fault_name"][:1].upper() + p["fault_name"][1:],
                    "slipSense": p["slip_sense"], "age": p["age"], "slipRate": p["slip_rate"] or None,
                    "dip": p["dip_direction"] or None, "megathrust": p["fault_id"] == MEGATHRUST,
                    "note": NOTES.get(p["fault_id"]), "url": p["fault_url"], "lines": []})
                fault["lines"].append({"constrained": p["linetype"] == "Well Constrained", "coords": run})
    ordered = sorted(faults.values(), key=lambda x: (not x["megathrust"], x["name"].startswith("Unnamed"), x["name"]))
    return {"credit": CREDIT, "dropped": sorted(DROPPED.values()), "faults": ordered}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh:
        print(f"USGS Quaternary fault traces: {refresh()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
