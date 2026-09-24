"""Axial Seamount subsurface layers → atlas bundle (needs numpy + scipy; separate from the stdlib build).

  git clone https://github.com/MaleenKidiwela/axial_visuals <dir>
  python -m atlas_map_data.subsurface --source <dir>

Reproduces the geometry of github.com/MaleenKidiwela/axial_visuals (final notebook cell): the
relocated earthquake catalog, the AMC reflector top, and polynomial fits to the west and east
caldera-wall faults. Every layer is written in lon/lat and metres below sea level.

The notebook puts every layer on one datum, 1,500 m below sea level (about the caldera floor):
catalog and wall depths are kilometres below it, and the AMC file stores elevation + 20,000 m,
which the notebook shifts by the same 1,500 m. Undoing that datum gives true depths.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.interpolate import griddata
from scipy.io import loadmat
from scipy.spatial import ConvexHull, Delaunay

LAT0, LON0 = 45.9547, -130.0089          # AXCC1, the notebook's local frame origin
XLT = 111.19
XLN = XLT * np.cos(np.deg2rad(LAT0))
DATUM_M = 1500.0
UTM_NORM = (419691.465854, 5081627.38769)  # UTM 9N offsets of the AMC .xyz
CREDIT = ("Subsurface: M. Kidiwela, axial_visuals (relocated earthquakes 2015-2021, AMC reflector top, "
          "caldera-wall fault fits); caldera rim from W. Chadwick")


def to_ll(x_km, y_km):
    return LON0 + np.asarray(x_km) / XLN, LAT0 + np.asarray(y_km) / XLT


def to_xy(lat, lon):
    return (np.asarray(lon) - LON0) * XLN, (np.asarray(lat) - LAT0) * XLT


def _field(arr, name):
    out = []
    for e in arr.flat:
        v = np.asarray(getattr(e, name)).ravel()
        out.append(float(v[0]) if v.size else np.nan)
    return np.array(out)


def _datenum(dn: float) -> datetime:
    return datetime.fromordinal(int(dn)) + timedelta(days=dn % 1) - timedelta(days=366)


def utm_to_ll(E, N, zone=9):
    a, e = 6378137.0, 0.0818191908426215
    e2 = e * e; ep2 = e2 / (1 - e2); k0 = 0.9996
    x, y = np.asarray(E, float) - 500000.0, np.asarray(N, float)
    lon0 = np.deg2rad((zone - 1) * 6 - 180 + 3)
    mu = y / k0 / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    fp = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    s, c, t = np.sin(fp), np.cos(fp), np.tan(fp)
    C1, T1 = ep2 * c ** 2, t ** 2
    N1 = a / np.sqrt(1 - e2 * s ** 2)
    R1 = a * (1 - e2) / (1 - e2 * s ** 2) ** 1.5
    D = x / (N1 * k0)
    lat = fp - (N1 * t / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
                                + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = lon0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6
                  + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / c
    return np.rad2deg(lat), np.rad2deg(lon)


def _surface(key, label, X_km, Y_km, Z_km):
    """A rows×cols vertex grid; masked vertices are null and drop their triangles."""
    lon, lat = to_ll(X_km, Y_km)
    elev = -(DATUM_M - Z_km * 1000.0)            # Z is km above the datum (negative = deeper)
    ok = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(elev)
    pts = []
    for a, b, m, ok_ in zip(lon.ravel(), lat.ravel(), elev.ravel(), ok.ravel()):
        pts.append([round(float(a), 6), round(float(b), 6), round(float(m), 1)] if ok_ else None)
    return {"key": key, "label": label, "rows": int(X_km.shape[0]), "cols": int(X_km.shape[1]), "points": pts}


def west_wall(src: Path, n=60):
    xyz = np.asarray(loadmat(src / "I_fitting_WW_slices.mat")["fit_x_y_z"], float)
    x, y, z = xyz.T
    m = (y >= -2.5) & (y <= 0.0)
    x, y, z = x[m], y[m], z[m]
    A = np.column_stack([x ** 2, y ** 2, x * y, x, y, np.ones_like(x)])
    a, b, c, d, e, f = np.linalg.lstsq(A, z, rcond=None)[0]
    X, Y = np.meshgrid(np.linspace(x.min(), x.max(), n), np.linspace(-3.0, 0.0, n))
    Z = a * X ** 2 + b * Y ** 2 + c * X * Y + d * X + e * Y + f + 0.156
    Z = np.where((Z < -1.6) | (Z > 0.0), np.nan, Z)
    return _surface("west-wall", "West caldera-wall fault", X, Y, Z)


def east_wall(src: Path, n=60):
    arr = np.atleast_1d(loadmat(src / "East_Felix_06_Dis.mat", squeeze_me=True, struct_as_record=False)["Felix"])
    lat, lon, dep = _field(arr, "lat"), _field(arr, "lon"), _field(arr, "depth")
    m = (lat >= 45.93) & (lat <= 45.97) & (lon >= -130.00) & (lon <= -129.975) & (dep <= 2.5)
    x, y = to_xy(lat[m], lon[m])
    z = -dep[m]

    def design(yv, zv):
        return np.column_stack([np.ones_like(yv), yv, zv, yv ** 2, yv * zv, zv ** 2, yv ** 3, yv ** 2 * zv, yv * zv ** 2, zv ** 3])
    coef = np.linalg.lstsq(design(y, z), x, rcond=None)[0]
    Y, Z = np.meshgrid(np.linspace(y.min(), y.max(), n), np.linspace(z.min(), z.max(), n))
    X = (design(Y.ravel(), Z.ravel()) @ coef).reshape(Y.shape)
    P1, P2 = np.array([1.57, -1.44, -0.01]), np.array([2.12, -2.74, -0.94])
    t = (X - P1[0]) / (P2 - P1)[0]
    beyond = (t >= 0) & (t <= 1) & (Z > P1[2] + t * (P2 - P1)[2])      # the notebook's trim line
    mask = ((Y < -2.5) & (Z > -0.8)) | (X < 0.75) | (X > 2.75) | beyond | ((Y < -2.2) & (Z > -0.5))
    return _surface("east-wall", "East caldera-wall fault", np.where(mask, np.nan, X), Y, np.where(mask, np.nan, Z))


def amc(src: Path, n=110):
    raw = np.loadtxt(src / "axial_amc_top_utm_norm_km_20000.xyz")[:, :3]
    lat, lon = utm_to_ll(raw[:, 0] + UTM_NORM[0], raw[:, 1] + UTM_NORM[1])
    x, y = to_xy(lat, lon)
    z = (raw[:, 2] - 20000.0 + DATUM_M) / 1000.0       # km relative to the datum, negative down
    keep = raw[:, 2] >= np.percentile(raw[:, 2], 5)
    x, y, z = x[keep], y[keep], z[keep]
    X, Y = np.meshgrid(np.linspace(x.min(), x.max(), n), np.linspace(y.min(), y.max(), n))
    Z = griddata((x, y), z, (X, Y), method="linear")
    Z = np.where(np.isnan(Z), griddata((x, y), z, (X, Y), method="nearest"), Z)
    hull = Delaunay(np.column_stack([x, y])[ConvexHull(np.column_stack([x, y])).vertices])
    Z = np.where(hull.find_simplex(np.column_stack([X.ravel(), Y.ravel()])).reshape(X.shape) >= 0, Z, np.nan)
    return _surface("amc", "Axial magma chamber (AMC) reflector top", X, Y, Z)


def earthquakes(src: Path):
    arr = np.atleast_1d(loadmat(src / "FA_Cl_ALL_simple.mat", squeeze_me=True, struct_as_record=False)["Po_Clu"])
    lat, lon, dep, on = (_field(arr, f) for f in ("lat", "lon", "depth", "on"))
    ok = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(dep) & np.isfinite(on)
    lat, lon, dep, on = lat[ok], lon[ok], dep[ok], on[ok]
    order = np.argsort(on)
    lat, lon, dep, on = lat[order], lon[order], dep[order], on[order]
    t0 = _datenum(float(on[0])).date()
    day0 = datetime(t0.year, t0.month, t0.day)
    days = np.array([(_datenum(float(v)) - day0).total_seconds() / 86400 for v in on])
    q = np.column_stack([np.round((lon - LON0) * 1e5), np.round((lat - LAT0) * 1e5),
                         np.round(DATUM_M + dep * 1000.0), np.round(days, 2)])
    return {"count": int(len(q)), "day0": day0.date().isoformat(), "lon0": LON0, "lat0": LAT0, "scale": 1e-5,
            "fields": ["dLon", "dLat", "depthM", "day"],
            "rows": [[int(a), int(b), int(c), float(d)] for a, b, c, d in q]}


def rim(src: Path):
    text = (src / "axial_calderaRim.m").read_text()
    block = re.search(r"calderaRim\s*=\s*\[(.*?)\];", text, flags=re.S).group(1)
    return [[float(a), float(b)] for a, b in re.findall(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", block)]


def build(src: Path, out: Path) -> dict:
    bundle = {"credit": CREDIT, "datumM": DATUM_M, "rim": rim(src), "earthquakes": earthquakes(src),
              "surfaces": [amc(src), west_wall(src), east_wall(src)]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "subsurface.json").write_text(json.dumps(bundle, separators=(",", ":")))
    return bundle


def main(argv: list[str] | None = None) -> int:
    from . import paths
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=paths.BUNDLE)
    args = ap.parse_args(argv)
    b = build(args.source, args.out)
    print(f"earthquakes {b['earthquakes']['count']} ({b['earthquakes']['day0']} +{b['earthquakes']['rows'][-1][3]:.0f} d)")
    for s in b["surfaces"]:
        pts = [p for p in s["points"] if p]
        print(f"{s['key']}: {len(pts)}/{s['rows'] * s['cols']} vertices, elev {min(p[2] for p in pts):.0f}..{max(p[2] for p in pts):.0f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
