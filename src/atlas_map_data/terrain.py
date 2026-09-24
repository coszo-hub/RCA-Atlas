"""GMRT seafloor grids: fetch (ESRI ASCII), parse, sample, and write compact Int16 files."""
from __future__ import annotations

import array
import math
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GMRT_URL = "https://www.gmrt.org/services/GridServer"
CREDIT = "GMRT, Ryan et al. (2009), CC BY 4.0"
NODATA_FILL = -3000
GRIDS = {
    "axial": {"north": 46.08, "south": 45.78, "east": -129.6, "west": -130.15, "resolution": "high"},
    "hydrate": {"north": 44.75, "south": 44.35, "east": -124.9, "west": -125.5, "resolution": "high"},
    "overview": {"north": 46.35, "south": 43.95, "east": -123.7, "west": -130.6, "resolution": "med"},
}
FINEST_FIRST = ["axial", "hydrate", "overview"]


@dataclass
class Grid:
    name: str
    ncols: int
    nrows: int
    west: float
    south: float
    cellsize: float
    values: array.array

    def _h(self, r: int, c: int) -> float:
        r = min(self.nrows - 1, max(0, r))
        c = min(self.ncols - 1, max(0, c))
        return self.values[r * self.ncols + c]

    def sample(self, lon: float, lat: float) -> float | None:
        fc = (lon - self.west) / self.cellsize - 0.5
        fr = self.nrows - (lat - self.south) / self.cellsize - 0.5   # row 0 is the north edge
        if fc < -0.5 or fr < -0.5 or fc > self.ncols - 0.5 or fr > self.nrows - 0.5:
            return None
        c0, r0 = math.floor(fc), math.floor(fr)
        tc, tr = fc - c0, fr - r0
        top = self._h(r0, c0) * (1 - tc) + self._h(r0, c0 + 1) * tc
        bottom = self._h(r0 + 1, c0) * (1 - tc) + self._h(r0 + 1, c0 + 1) * tc
        return top * (1 - tr) + bottom * tr

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.west + self.ncols * self.cellsize, self.south + self.nrows * self.cellsize)

    def meta(self) -> dict:
        return {"ncols": self.ncols, "nrows": self.nrows, "west": self.west, "south": self.south,
                "cellsize": self.cellsize, "min": min(self.values), "max": max(self.values)}


def read_esri_ascii(path: Path, name: str) -> Grid:
    with open(path, encoding="ascii") as fh:
        header = {}
        for _ in range(6):
            key, value = fh.readline().split()
            header[key.lower()] = float(value)
        nodata = header["nodata_value"]
        values = array.array("h")
        for line in fh:
            for token in line.split():
                v = float(token)
                values.append(NODATA_FILL if v == nodata else int(max(-32000, min(32000, round(v)))))
    return Grid(name, int(header["ncols"]), int(header["nrows"]), header["xllcorner"],
                header["yllcorner"], header["cellsize"], values)


def write_bin(grid: Grid, path: Path) -> None:
    data = array.array("h", grid.values)
    if sys.byteorder != "little":
        data.byteswap()
    path.write_bytes(data.tobytes())


def read_bin(path: Path, meta: dict, name: str) -> Grid:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        values.byteswap()
    return Grid(name, meta["ncols"], meta["nrows"], meta["west"], meta["south"], meta["cellsize"], values)


class Stack:
    FALLBACK = -2500.0

    def __init__(self, grids: list[Grid]):
        self.grids = grids

    def covered(self, lon: float, lat: float) -> bool:
        return any(g.sample(lon, lat) is not None for g in self.grids)

    def elev(self, lon: float, lat: float) -> float:
        for g in self.grids:
            v = g.sample(lon, lat)
            if v is not None:
                return v
        return self.FALLBACK


def fetch_gmrt(name: str, dest: Path, urlopen=urllib.request.urlopen) -> Path:
    spec = GRIDS[name]
    query = urllib.parse.urlencode({**{k: spec[k] for k in ("north", "south", "east", "west")},
                                    "layer": "topo", "format": "esriascii", "resolution": spec["resolution"]})
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{name}.asc"
    with urlopen(f"{GMRT_URL}?{query}", timeout=300) as resp:
        out.write_bytes(resp.read())
    return out
