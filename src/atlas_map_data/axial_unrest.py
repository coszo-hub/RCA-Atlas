"""Axial Seamount's unrest since 2015 → atlas bundle: the real-time earthquake catalog after the relocated one ends,
monthly earthquake counts, and the caldera's uplift since the April 2015 eruption (needs numpy).

  PYTHONPATH=src .venv/bin/python -m atlas_map_data.axial_unrest [--refresh]

--refresh downloads the University of Washington's catalog (hypo71.dat, about 40 MB) and OOI's daily depths from the
Gold Copy into source_material/AxialEarthquakes/latest first; without it the build reads what is there.

The relocated catalog in subsurface.json (2015-2021) stays as it is: its locations are better. Real-time events
after it are added when their horizontal and vertical errors are both within MAX_ERR_KM, each placed at random within
the 0.01-minute cell its position is rounded to (18 m north-south): in the dense eastern-caldera clusters up to 50 share
one rounded position, and their depth errors stood them in vertical columns. The real-time depths share
the relocated catalog's datum, 1.5 km below sea level: 36,217 events in both catalogs differ by a median 0.23 km
in depth and 0.41 km in position. Monthly counts use every real-time event, so the rate is one catalog throughout.

Uplift is OOI's daily mean depth (botsflu_daydepth, de-tided) at the caldera centre (MJ03F) and eastern rim (MJ03E),
in cm above the last day before the 2015 eruption (23 April 2015). The gauges' drift is not corrected (OSU corrects
it with campaign pressure measurements), so the level against 2015 is uncertain by several cm.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import paths

CATALOG_URL = "http://axial.ocean.washington.edu/hypo71.dat"
THREDDS = "https://thredds.dataexplorer.oceanobservatories.org/thredds"
BOTPTS = {"MJ03F": "RS03CCAL-MJ03F-05-BOTPTA301", "MJ03E": "RS03ECAL-MJ03E-06-BOTPTA302"}
SOURCE = paths.REPO / "source_material" / "AxialEarthquakes" / "latest"
MAX_ERR_KM = 1.0                           # 54% of the events after 2021; at 2 km (85%) depth errors smear the faults
CELL_DEG = 0.01 / 60                       # the catalog gives positions to 0.01 arc-minute
DATUM_M = 1500.0
DAY0 = datetime(2015, 1, 22)               # the relocated catalog's first day: one timeline for both
REFERENCE_DAY = "2015-04-23"               # the last day before the eruption began on 24 April 2015
CREDIT = ("Earthquakes after 2021: University of Washington Axial Seamount real-time catalog (W. Wilcock, M. Zhang); "
          "uplift: OOI BOTPT daily depths (botsflu_daydepth), not corrected for gauge drift")


def get(url: str, timeout=300) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "rca-atlas"}), timeout=timeout) as r:
        return r.read()


def refresh(out: Path = SOURCE) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "hypo71.dat").write_bytes(get(CATALOG_URL))
    for node, refdes in BOTPTS.items():
        folder = f"ooigoldcopy/public/{refdes}-streamed-botpt_nano_sample_24hour"
        listing = get(f"{THREDDS}/catalog/{folder}/catalog.xml").decode()
        parts = [get(f"{THREDDS}/dodsC/{p}.ascii?time,botsflu_daydepth").decode()
                 for p in sorted(set(re.findall(r'urlPath="([^"]+\.nc)"', listing)))]
        (out / f"daydepth_{node}.txt").write_text("\n\n=====\n\n".join(parts))


def parse_catalog(text: str) -> np.ndarray:
    """hypo71.dat rows → [days since DAY0, lat, lon, depth km, Mw, ERH km, ERZ km], sorted by time."""
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) < 15:
            continue
        try:
            t = datetime.strptime(p[0] + p[1][:4], "%Y%m%d%H%M") + timedelta(seconds=float(p[2]))
            rows.append(((t - DAY0).total_seconds() / 86400, float(p[3]) + float(p[4]) / 60,
                         -(float(p[5]) + float(p[6]) / 60), float(p[7]), float(p[8]), float(p[13]), float(p[14])))
        except ValueError:
            continue
    a = np.array(rows, float)
    return a[np.argsort(a[:, 0], kind="stable")]


def parse_daydepth(text: str) -> dict[str, float]:
    """OPeNDAP ASCII answers (one a file) → {YYYY-MM-DD: daily depth m}, missing values dropped, later files win."""
    out = {}
    for part in text.split("====="):
        got = {}
        for name in ("time", "botsflu_daydepth"):
            m = re.search(rf"^{name}\[\d+\]\n(.*?)(?:\n\n|\Z)", part, re.S | re.M)
            got[name] = [float(x) for x in m.group(1).replace("\n", " ").split(",") if x.strip()] if m else []
        for t, d in zip(got["time"], got["botsflu_daydepth"]):
            if d > -9e5:
                out[(datetime(1900, 1, 1) + timedelta(seconds=t)).date().isoformat()] = d
    return out


def months_between(first: datetime, last: datetime) -> list[str]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build(source: Path = SOURCE, out: Path = paths.BUNDLE) -> dict:
    sub = json.loads((out / "subsurface.json").read_text())["earthquakes"]
    relocated_end = max(r[3] for r in sub["rows"]) + (datetime.fromisoformat(sub["day0"]) - DAY0).days
    cat = parse_catalog((source / "hypo71.dat").read_text(errors="replace"))
    stamp = lambda d: DAY0 + timedelta(days=float(d))

    # Every real-time event, counted by month (UTC).
    labels = months_between(stamp(cat[0, 0]), stamp(cat[-1, 0]))
    index = {k: i for i, k in enumerate(labels)}
    counts = [0] * len(labels)
    for d in cat[:, 0]:
        counts[index[stamp(d).strftime("%Y-%m")]] += 1

    # The real-time events after the relocated catalog, well located: [dLon, dLat] / 1e-5 deg, depth m below sea
    # level, minutes since DAY0, Mw x 100, as little-endian int32.
    keep = (cat[:, 0] > relocated_end) & (cat[:, 5] <= MAX_ERR_KM) & (cat[:, 6] <= MAX_ERR_KM)
    q = cat[keep].copy()
    rng = np.random.default_rng(0)   # the same placement every build
    q[:, 1:3] += rng.uniform(-CELL_DEG / 2, CELL_DEG / 2, (len(q), 2))
    packed = np.column_stack([np.round((q[:, 2] - sub["lon0"]) * 1e5), np.round((q[:, 1] - sub["lat0"]) * 1e5),
                              np.round(DATUM_M + q[:, 3] * 1000), np.round(q[:, 0] * 1440),
                              np.round(np.clip(q[:, 4], -9, 9) * 100)]).astype("<i4")
    out.mkdir(parents=True, exist_ok=True)
    (out / "quakes_realtime.bin.gz").write_bytes(gzip.compress(packed.tobytes(), 9, mtime=0))

    # Uplift since the eve of the eruption, cm, one value a day (null where none).
    first = datetime(2014, 8, 1)
    days = (stamp(cat[-1, 0]).replace(hour=0, minute=0, second=0, microsecond=0) - first).days + 1
    uplift = {}
    for node in BOTPTS:
        depth = parse_daydepth((source / f"daydepth_{node}.txt").read_text())
        ref = depth[REFERENCE_DAY]
        uplift[node] = [round((depth[d] - ref) * 100, 1) if (d := (first + timedelta(days=i)).date().isoformat()) in depth
                        else None for i in range(days)]

    bundle = {
        "credit": CREDIT, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "day0": DAY0.date().isoformat(),
        "realtime": {"file": "quakes_realtime.bin.gz", "count": int(len(q)), "fields": ["dLon", "dLat", "depthM", "minute", "mw100"],
                     "scale": 1e-5, "lon0": sub["lon0"], "lat0": sub["lat0"], "maxErrKm": MAX_ERR_KM,
                     "first": stamp(q[0, 0]).isoformat(timespec="seconds") if len(q) else None,
                     "last": stamp(q[-1, 0]).isoformat(timespec="seconds") if len(q) else None,
                     "dropped": int(((cat[:, 0] > relocated_end) & ~keep).sum())},
        "monthly": {"start": labels[0], "counts": counts, "source": CATALOG_URL},
        "uplift": {"start": first.date().isoformat(), "reference": REFERENCE_DAY, "units": "cm", "sites": uplift,
                   "names": {"MJ03F": "Caldera centre (MJ03F)", "MJ03E": "Eastern rim (MJ03E)"}},
        "eruptions": [{"start": "2015-04-24", "label": "2015 eruption"}],
    }
    (out / "axial_unrest.json").write_text(json.dumps(bundle, separators=(",", ":")))
    return bundle


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="download the catalog and daily depths first")
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--out", type=Path, default=paths.BUNDLE)
    args = ap.parse_args(argv)
    if args.refresh:
        refresh(args.source)
    b = build(args.source, args.out)
    r, m, u = b["realtime"], b["monthly"], b["uplift"]["sites"]
    print(f"real-time earthquakes {r['count']} ({r['first']} to {r['last']}; {r['dropped']} with errors over {MAX_ERR_KM} km left out)")
    print(f"monthly counts {m['start']} +{len(m['counts'])} months, busiest {max(m['counts'])}")
    for node, v in u.items():
        last = next(x for x in reversed(v) if x is not None)
        print(f"uplift {node}: {sum(x is not None for x in v)} days, latest {last:+.1f} cm against {REFERENCE_DAY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
