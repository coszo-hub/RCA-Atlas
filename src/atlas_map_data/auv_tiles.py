"""MBARI AUV bathymetry → level-of-detail tiles for the atlas (needs h5py + numpy; separate from the stdlib build).

  python -m atlas_map_data.auv_tiles --source <MBARI ... _AUVOverShip_Topo1mSq.grd> --out src/atlas_map/public/atlas/auv
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path

import h5py
import numpy as np

CREDIT = "MBARI Axial Seamount bathymetry, cruise V2506: 1 m AUV survey merged over ship-based multibeam"
Z_OFFSET, Z_SCALE = -1000.0, 10.0
KX = 111.32 * math.cos(math.radians(45.94))
KZ = 111.13


def _encode(block: np.ndarray) -> bytes:
    q = np.clip(np.round((block - Z_OFFSET) * Z_SCALE), -32000, 32000).astype(np.int32)
    d = q.copy()
    d[:, 1:] = q[:, 1:] - q[:, :-1]
    if np.abs(d[:, 1:]).max(initial=0) > 32000:
        raise ValueError("delta overflow; raise Z_SCALE resolution or reduce stride")
    return gzip.compress(d.astype("<i2").tobytes(), 9)


def decode(data: bytes, cells: int, z_offset: float, z_scale: float) -> list[list[float]]:
    s = cells + 1
    d = np.frombuffer(gzip.decompress(data), dtype="<i2").reshape(s, s).astype(np.int64)
    return (np.cumsum(d, axis=1) / z_scale + z_offset).tolist()


def build(source: Path, out: Path, sites: list[tuple[float, float]], cells: int = 256,
          levels=((0, 16), (1, 4), (2, 1)), l2_radius_km: float = 1.2) -> dict:
    with h5py.File(source, "r") as f:
        lon, lat, z = f["lon"][:], f["lat"][:], f["z"]
        ny, nx = z.shape
        cell = float(lon[1] - lon[0])
        west, south = float(lon[0]) - cell / 2, float(lat[0]) - cell / 2
        north = south + ny * cell
        finest = max(level for level, _ in levels)

        def near_site(lon0, lat0, lon1, lat1):
            for plat, plon in sites:
                cx, cy = min(max(plon, lon0), lon1), min(max(plat, lat0), lat1)
                if math.hypot((cx - plon) * KX, (cy - plat) * KZ) <= l2_radius_km:
                    return True
            return False

        index = {"source": source.name, "credit": CREDIT, "west": west, "north": north, "cellDeg": cell,
                 "tileCells": cells, "zOffset": Z_OFFSET, "zScale": Z_SCALE, "nx": nx, "ny": ny, "levels": []}
        for level, stride in levels:
            lnx, lny = math.ceil(nx / stride), math.ceil(ny / stride)
            tnx, tny = math.ceil(lnx / cells), math.ceil(lny / cells)
            tile_deg = cells * stride * cell
            outdir = out / f"L{level}"
            outdir.mkdir(parents=True, exist_ok=True)
            tiles = []
            for ty in range(tny):
                lat1, lat0 = north - ty * tile_deg, north - (ty + 1) * tile_deg
                wanted = [tx for tx in range(tnx) if level != finest or
                          near_site(west + tx * tile_deg, lat0, west + (tx + 1) * tile_deg, lat1)]
                if not wanted:
                    continue
                r0 = ty * cells
                last = min(r0 + cells, lny - 1)
                lo, hi = max(ny - (last + 1) * stride, 0), ny - r0 * stride     # ascending-lat source rows
                strip = z[lo:hi, :].astype(np.float32)[::-1]                      # north-first
                if stride > 1:
                    h, w = (strip.shape[0] // stride) * stride, (nx // stride) * stride
                    rows_needed = last - r0 + 1
                    if h // stride < rows_needed:                                  # ragged south edge
                        strip = np.concatenate([strip, np.repeat(strip[-1:], rows_needed * stride - strip.shape[0], axis=0)])
                        h = rows_needed * stride
                    pooled = strip[:h, :w].reshape(h // stride, stride, w // stride, stride).mean(axis=(1, 3))
                    if w < nx:
                        pooled = np.concatenate([pooled, pooled[:, -1:]], axis=1)
                else:
                    pooled = strip
                for tx in wanted:
                    block = pooled[:cells + 1, tx * cells: tx * cells + cells + 1]
                    if block.size == 0 or np.isnan(block).all():
                        continue
                    pr, pc = cells + 1 - block.shape[0], cells + 1 - block.shape[1]
                    if pr or pc:
                        block = np.pad(block, ((0, pr), (0, pc)), mode="edge")
                    if np.isnan(block).any():
                        block = np.where(np.isnan(block), np.nanmean(block), block)
                    (outdir / f"{ty}_{tx}.bin.gz").write_bytes(_encode(block))
                    tiles.append([ty, tx])
            index["levels"].append({"level": level, "stride": stride, "cellDeg": cell * stride,
                                    "tilesX": tnx, "tilesY": tny, "tiles": tiles})
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index))
    return index


def main(argv: list[str] | None = None) -> int:
    from . import paths
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=paths.BUNDLE / "auv")
    ap.add_argument("--sensors", type=Path, default=paths.BUNDLE / "sensors.json")
    args = ap.parse_args(argv)
    sensors = json.loads(args.sensors.read_text())["sensors"]
    sites = [(s["lat"], s["lon"]) for s in sensors if s.get("lat") is not None]
    ix = build(args.source, args.out, sites)
    for L in ix["levels"]:
        print(f"L{L['level']}: stride {L['stride']}, {len(L['tiles'])} tiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
