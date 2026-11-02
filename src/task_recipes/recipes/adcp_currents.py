# pip install requests xarray netCDF4 matplotlib
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests
import xarray as xr

DATASET = "RS03AXBS-LJ03A-10-ADCPTE303-streamed-adcp_velocity_beam"   # an ADCP's Gold Copy stream (its download recipe names it)
START, END = "2025-10-14T00:00:00", "2025-10-16T00:00:00"   # the span, UTC
AVERAGE = "1h"                                      # the averaging period of each column
ERROR_MAX = 0.1                                     # m/s: a sample whose error velocity is larger is left out
MIN_GOOD = 0.5                                      # a column's bin needs this share of its samples left, else it is blank

T = "https://thredds.dataexplorer.oceanobservatories.org/thredds"
stamp = lambda t: t.replace("-", "").replace(":", "")[:15]
xml = requests.get(f"{T}/catalog/ooigoldcopy/public/{DATASET}/catalog.xml", timeout=120).text
# The ADCP's own files only: its folder also holds the CTD files used to process it.
paths = [p for p in re.findall(r'urlPath="([^"]+\.nc)"', xml)
         if f"_{DATASET}_" in p and (s := re.search(r"_(\d{8}T\d{6})[.\d]*-(\d{8}T\d{6})[.\d]*\.nc$", p))
         and s.group(2) >= stamp(START) and s.group(1) <= stamp(END)]
parts = []
for path in sorted(paths):
    ds = xr.open_dataset(f"{T}/dodsC/{path}").swap_dims({"obs": "time"})   # OPeNDAP: read only what is selected
    ds = ds[["eastward_seawater_velocity", "northward_seawater_velocity", "error_seawater_velocity", "bin_depths"]]
    ds = ds.sel(time=slice(START, END)).load()
    if not ds.sizes["time"]:
        continue
    # East and north are in Earth coordinates with the magnetic variation accounted for (OOI's processing).
    bad = np.abs(ds["error_seawater_velocity"]) > ERROR_MAX
    for v in ("eastward_seawater_velocity", "northward_seawater_velocity"):
        ds[v] = ds[v].where(~bad)
    mean = ds.resample(time=AVERAGE).mean()   # a sample a second: average each file before combining
    # Far from the ADCP the echo is too weak and most samples fail: a bin with too few left in the period is blank.
    good = ds["eastward_seawater_velocity"].notnull().resample(time=AVERAGE).mean()
    for v in ("eastward_seawater_velocity", "northward_seawater_velocity"):
        mean[v] = mean[v].where(good >= MIN_GOOD)
    parts.append(mean)
if not parts:
    raise SystemExit(f"no {DATASET} data between {START} and {END}")
data = xr.concat(parts, dim="time").sortby("time")
data = data.groupby("time").mean()   # an hour split between two files is averaged once more
east, north = data["eastward_seawater_velocity"], data["northward_seawater_velocity"]
data["speed"] = np.hypot(east, north)
data["direction"] = (np.degrees(np.arctan2(east, north)) + 360) % 360   # toward which the water flows, degrees from north
depth = data["bin_depths"].mean("time")   # each bin's depth (m), from the ADCP's own pressure

name = f"{DATASET.split('-streamed')[0]}_{stamp(START)}_{stamp(END)}"
fig, axes = plt.subplots(2, 1, sharex=True, figsize=(11, 7))
for ax, (v, label, cmap, lim) in zip(axes, [("speed", "speed (m/s)", "viridis", None), ("direction", "direction (° toward)", "twilight", (0, 360))]):
    mesh = ax.pcolormesh(data["time"].values, depth.values, data[v].values.T, shading="nearest", cmap=cmap,
                         vmin=lim[0] if lim else 0, vmax=lim[1] if lim else float(data["speed"].quantile(0.98)))
    ax.invert_yaxis()
    ax.set_ylabel("depth (m)")
    fig.colorbar(mesh, ax=ax, label=label)
axes[0].set_title(f"{DATASET.split('-streamed')[0]}, {AVERAGE} means")
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
data.encoding.pop("unlimited_dims", None)
data.assign_coords(depth=("bin", depth.values)).to_netcdf(name + ".nc")   # time, bin (with its depth), speed, direction
