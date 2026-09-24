"""Replace the straight-line approximation west of the US EEZ with the mapped route in ooi_cables.csv.

  curl -LO https://raw.githubusercontent.com/MaleenKidiwela/CascadiaEarthquakes/main/ooi_cables.csv
  python src/atlas_map_data/cable/merge_csv.py ooi_cables.csv

The CSV is bare Lat,Long rows: the cable lines one after another with no separators. Where it overlaps the
Marine Cadastre charted route it matches within metres (median 1 m, worst 0.19 km), so it is used for the
north backbone beyond the EEZ (EEZ limit -> PN3A -> PN3B) and for the secondary cables at Axial Base and in the
caldera. Stdlib only; rewrites rca_cable.geojson in place and is idempotent.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEOJSON = HERE / "rca_cable.geojson"
SOURCE_URL = "https://github.com/MaleenKidiwela/CascadiaEarthquakes/blob/main/ooi_cables.csv"
SOURCE = "M. Kidiwela, CascadiaEarthquakes ooi_cables.csv"
# Row ranges (0-based, inclusive) of the lines used, checked against known end points below.
NORTH_BACKBONE = (333, 534)          # Pacific City landfall -> PN3B
PN3A_LOCAL = (544, 722)              # secondary cables around PN3A / LJ03A
CALDERA = (723, 2199)                # secondary cables in the caldera from PN3B
RUN_BREAK_KM = 0.25                  # consecutive rows further apart than this start a new cable run
MIN_RUN_KM = 0.2


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 111.13)


def length(coords):
    return sum(km(a, b) for a, b in zip(coords, coords[1:]))


def nearest(coords, p):
    return min(range(len(coords)), key=lambda i: km(coords[i], p))


def on_segment(coords, p):
    """(i, distance km): the segment coords[i] -> coords[i + 1] passing closest to p (the CSV's vertices are sparse)."""
    best = None
    for i, (a, b) in enumerate(zip(coords, coords[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1)))
        d = km((a[0] + t * dx, a[1] + t * dy), p)
        if best is None or d < best[1]:
            best = (i, d)
    return best


def runs(rows, lo, hi):
    out = [[rows[lo]]]
    for i in range(lo + 1, hi + 1):
        (out.append([rows[i]]) if km(rows[i - 1], rows[i]) > RUN_BREAK_KM else out[-1].append(rows[i]))
    return [r for r in out if length(r) >= MIN_RUN_KM]


def feature(name, coords, note=None):
    props = {"name": name, "source": SOURCE, "source_url": SOURCE_URL, "accuracy": "mapped",
             "length_km": round(length(coords), 2), "line": "north"}
    if note:
        props["note"] = note
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]}}


def main(csv_path: str) -> int:
    rows = [(float(r["Long"]), float(r["Lat"])) for r in csv.DictReader(open(csv_path))]
    g = json.loads(GEOJSON.read_text())
    feats = g["features"]
    node = {f["properties"]["name"].split(" ")[0]: f["geometry"]["coordinates"] for f in feats if f["geometry"]["type"] == "Point"}
    eez = next(f for f in feats if f["properties"]["name"].startswith("North backbone: PN5A area -> US EEZ limit"))["geometry"]["coordinates"][-1]

    north = rows[NORTH_BACKBONE[0]:NORTH_BACKBONE[1] + 1]
    assert km(north[-1], node["PN3B"]) < 0.05, "north backbone must end at PN3B"
    (i_eez, d_eez), i_pn3a = on_segment(north, eez), nearest(north, node["PN3A"])
    # The charted line ends on the CSV's route; PN3A's stand-in (the MJ03A junction box) is ~0.5 km off it.
    assert d_eez < 0.3 and km(north[i_pn3a], node["PN3A"]) < 1.0 and i_eez < i_pn3a, (d_eez, i_eez, i_pn3a)
    beyond = [tuple(eez)] + north[i_eez + 1:i_pn3a + 1]
    climb = north[i_pn3a:]

    keep = [f for f in feats if f["geometry"]["type"] != "LineString"
            or (f["properties"].get("source_url") != SOURCE_URL and f["properties"]["accuracy"] != "approximate")]
    new = [feature("North backbone: US EEZ limit -> PN3A (Axial Base)", beyond,
                   "Vertices are sparse beyond the EEZ (up to ~50 km apart); the route bows north of a straight line by up to ~13 km."),
           feature("North backbone: PN3A (Axial Base) -> PN3B (Axial Caldera)", climb)]
    for i, r in enumerate(runs(rows, *PN3A_LOCAL), 1):
        new.append(feature(f"Secondary cable: Axial Base (PN3A/LJ03A) run {i}", r))
    for i, r in enumerate(runs(rows, *CALDERA), 1):
        new.append(feature(f"Secondary cable: Axial caldera (PN3B) run {i}", r))
    # The backbone dips to PN3A and back: that turning point, not the MJ03A junction box it was proxied by, is the node.
    pn3a = next(f for f in keep if f["properties"]["name"].startswith("PN3A"))
    pn3a["geometry"]["coordinates"] = [round(north[i_pn3a][0], 6), round(north[i_pn3a][1], 6)]
    pn3a["properties"].update(name="PN3A (Axial Base) - approximate", source=f"{SOURCE}: where the north backbone turns at Axial Base",
                              source_url=SOURCE_URL, note="Placed where the north backbone turns at Axial Base in ooi_cables.csv (M. Kidiwela); the MJ03A junction box is ~0.5 km away.")
    g["description"] = g["description"].split(" Beyond the US EEZ")[0].replace(" Segments beyond the US EEZ are approximate.", "") + (
        f" Beyond the US EEZ, and the secondary cables at Axial, from {SOURCE} ({SOURCE_URL}).")
    g["features"] = keep + new
    GEOJSON.write_text(json.dumps(g, indent=1))
    print(f"north backbone beyond EEZ {length(beyond):.1f} km, PN3A->PN3B {length(climb):.1f} km, "
          f"{len(new) - 2} secondary runs ({sum(f['properties']['length_km'] for f in new[2:]):.1f} km)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
