# pip install h5py numpy scipy pandas xarray netCDF4 matplotlib requests
import os
import re
import tempfile
import numpy as np
import pandas as pd
import requests
import h5py
import xarray as xr
from scipy.signal import butter, sosfiltfilt
from scipy.signal.windows import tukey
from scipy.integrate import cumulative_trapezoid
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# The RCA's fibre-optic DAS experiments on the PI data portal (each has its own file format and units):
#   "das2021": OptaSense QuantX, 1-5 November 2021, north and south cables, mostly 200 Hz, 2.04 m channels,
#              one-minute HDF5 files of about 1.2 GB holding phase
#   "das24":   ASN OptoDAS, 6-10 May 2024, south cable to its first repeater (97 km), 200 Hz, 10.2 m channels,
#              ten-second HDF5 files of 76 MB holding phase rate
#   "das25":   ASN OptoDAS, 13 November 2025 to January 2026, south cable's first span, 8 Hz (the public copy),
#              ten-second HDF5 files of about 2 MB holding phase rate
EXPERIMENT = "das24"
CABLE = "south"            # das2021 only: "north" or "south" (das24 and das25 recorded the south cable)
FIBER = "TransmitFiber"    # das2021 only: "TransmitFiber" (1-5 November) or "ReceiveFiber" (5 November, 14:20-17:00)
START, END = "2024-05-07T12:00:00", "2024-05-07T12:01:00"   # UTC; END is not included
DIST_KM = (20.0, 40.0)     # optical distance along the fibre from the interrogator on shore, km
CHANNEL_STEP = 1           # keep every nth channel (das2021's 2 m channels: 5 keeps one every 10 m)
OUTPUT = "strain_rate"     # "strain_rate" (1/s) or "strain"
BAND = (1.0, 50.0)         # Hz, zero-phase band-pass; None for none (strain from phase rate then drifts)
COMMON_MODE = False        # True: take out what every channel records at the same instant (the interrogator's
                           # laser noise, the vertical stripes), the median across channels; it also takes out
                           # any wave arriving everywhere at once
MAX_FILES = 12             # a guard: the portal sends whole files (no partial downloads), 1.2 GB a minute for das2021
PORTAL = "http://piweb.ooirsn.uw.edu"
LAMBDA, XI = 1550e-9, 0.78  # das2021: laser wavelength (m) and the fibre's photoelastic factor (Lindsey et al. 2020)

start, end = pd.Timestamp(START), pd.Timestamp(END)


def links(url):
    """The files and folders a portal directory lists."""
    text = requests.get(url, timeout=120).text
    return sorted(set(h for h in re.findall(r'href="([^"?]+)"', text) if not h.startswith(("/", ".."))))


# 1. The files, with the start time in their names, from the portal's folders.
found = []   # (start time from the name, url)
if EXPERIMENT == "das2021":
    base = f"{PORTAL}/das/data/Optasense/{CABLE.capitalize()}Cable/{FIBER}/"
    for run in links(base):   # one folder per acquisition run, each with its own gauge length and rate
        if run.startswith("ShortDuration"):
            continue          # minutes of parameter tests on 1 November 2021
        for name in links(base + run):
            m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{6})Z\.h5$", name)
            if m:
                found.append((pd.Timestamp(m.group(1)), base + run + name))
else:
    for day in pd.date_range((start - pd.Timedelta(minutes=1)).normalize(), end.normalize(), freq="D"):
        folder = (f"{PORTAL}/das24/data/{day:%Y%m%d}/dphi/" if EXPERIMENT == "das24"
                  else f"{PORTAL}/das25/data/OptoDAS/{day:%Y/%m/%d}/south/8Hz/")
        try:
            names = links(folder)
        except requests.RequestException:
            continue
        for name in names:
            m = re.search(r"(\d{6})\.hdf5$", name)
            if m:
                found.append((pd.Timestamp(f"{day:%Y-%m-%d}T{m.group(1)}"), folder + name))
found = sorted({t: u for t, u in sorted(found, reverse=True)}.items())   # one file a start time (runs can repeat one)
# a file runs until the next one starts; the last is given a minute
chosen = [u for i, (t, u) in enumerate(found)
          if t < end and (found[i + 1][0] if i + 1 < len(found) else t + pd.Timedelta(minutes=1)) > start]
if not chosen:
    raise SystemExit(f"no {EXPERIMENT} files between {START} and {END}: see the dates above")
if len(chosen) > MAX_FILES:
    raise SystemExit(f"{len(chosen)} files for {START} to {END}: shorten the span or raise MAX_FILES")
print(f"{len(chosen)} files from {chosen[0]} to {chosen[-1].rsplit('/', 1)[1]}")


def read(path):
    """One file's samples for the chosen channels, in strain or strain rate, with its times and channel distances."""
    with h5py.File(path, "r") as f:
        if EXPERIMENT == "das2021":   # ProdML: phase in 2*pi/2**16 rad, [locus, time]
            acq = f["Acquisition"]
            gauge, dx = float(acq.attrs["GaugeLength"]), float(acq.attrs["SpatialSamplingInterval"])
            n = float(acq["Custom"].attrs.get("Fibre Refractive Index", 1.4682))
            first = int(acq.attrs.get("StartLocusIndex", 0))
            distance = (first + np.arange(int(acq.attrs["NumberOfLoci"]))) * dx
            keep = np.flatnonzero((distance >= DIST_KM[0] * 1e3) & (distance <= DIST_KM[1] * 1e3))[::CHANNEL_STEP]
            raw = acq["Raw[0]/RawData"][keep[0]:keep[-1] + 1:CHANNEL_STEP, :].T
            micro = acq["Raw[0]/RawDataTime"][:]   # microseconds since 1970
            times = pd.to_datetime(micro, unit="us")
            factor = 2 * np.pi / 2 ** 16 * LAMBDA / (4 * np.pi * n * XI * gauge)   # Lindsey et al. 2020
            info = dict(gauge_length_m=gauge, channel_spacing_m=dx, refractive_index=n,
                        dt=float(np.median(np.diff(micro))) / 1e6,
                        conversion=f"strain = phase(rad) * {LAMBDA:g}/(4 pi {n:.4f} {XI} {gauge:.2f} m)")
            return raw.astype(np.float32) * np.float32(factor), "strain", times, distance[keep], keep + first, info
        # OptoDAS: phase rate per metre (rad/(s m)) as data * dataScale, [time, channel];
        # strain rate = that / sensitivity (rad per strain per metre), as in the uwfiberlab OOI_DAS_2025 notebook
        h = f["header"]
        distance = f["cableSpec/sensorDistances"][:]   # the true spacing: header dx times the ROI decimation
        keep = np.flatnonzero((distance >= DIST_KM[0] * 1e3) & (distance <= DIST_KM[1] * 1e3))[::CHANNEL_STEP]
        raw = f["data"][:, keep[0]:keep[-1] + 1:CHANNEL_STEP]
        dt, scale, sens = float(h["dt"][()]), float(h["dataScale"][()]), float(h["sensitivities"][()].ravel()[0])
        times = pd.to_datetime(float(h["time"][()]) + dt * np.arange(raw.shape[0]), unit="s")
        info = dict(gauge_length_m=float(h["gaugeLength"][()]), channel_spacing_m=float(np.median(np.diff(distance))), dt=dt,
                    header_dx_m=float(h["dx"][()]), data_scale=scale, sensitivity=sens,
                    conversion=f"strain rate = data * {scale:.6g} / {sens:.6g}")
        rate = raw.astype(np.float32) * np.float32(scale / sens)
        return rate, "strain_rate", times, distance[keep], h["channels"][()][keep], info


# 2. Download each file whole (the portal ignores byte ranges), keep the chosen channels, delete it.
pieces = []
for url in chosen:
    with tempfile.NamedTemporaryFile(suffix=".h5", delete=False, dir=".") as tmp:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            for block in r.iter_content(1 << 22):
                tmp.write(block)
    try:
        pieces.append(read(tmp.name))
    finally:
        os.remove(tmp.name)
kind, distance, channels, info = pieces[0][1], pieces[0][3], pieces[0][4], pieces[0][5]
dt = info["dt"]
fs = 1 / dt
print(f"{EXPERIMENT}: {fs:g} Hz, gauge length {info['gauge_length_m']:.2f} m, channels every "
      f"{info['channel_spacing_m'] * CHANNEL_STEP:.2f} m ({len(distance)} from {distance[0] / 1e3:.2f} to "
      f"{distance[-1] / 1e3:.2f} km); {info['conversion']}")
if "header_dx_m" in info:
    print(f"  the header's dx ({info['header_dx_m']:.3f} m) is before the ROI decimation; the channels are "
          f"{info['channel_spacing_m']:.3f} m apart (cableSpec/sensorDistances)")

# 3. Join the files on one time line; where one ends more than a sample before the next starts, that is a gap,
#    and each continuous stretch is filtered and integrated on its own (integrating across a gap is wrong).
segments, gaps = [[pieces[0]]], []
for prev, cur in zip(pieces, pieces[1:]):
    expected = prev[2][-1] + pd.Timedelta(seconds=dt)
    if abs((cur[2][0] - expected).total_seconds()) > 1.5 * dt:
        gaps.append((expected, cur[2][0]))
        segments.append([])
    segments[-1].append(cur)
print("gaps between files:", ", ".join(f"{a:%H:%M:%S.%f}-{b:%H:%M:%S.%f}" for a, b in gaps) or "none")

out_t, out_x, shares = [], [], []
for seg in segments:
    x = np.concatenate([p[0] for p in seg])
    t = np.concatenate([p[2].values for p in seg])
    if OUTPUT == "strain_rate" and kind == "strain":
        x = np.gradient(x, dt, axis=0).astype(np.float32)
    elif OUTPUT == "strain" and kind == "strain_rate":   # integrate only after the files are joined
        x = cumulative_trapezoid(x, dx=dt, axis=0, initial=0).astype(np.float32)
    x -= x.mean(axis=0)
    if BAND and len(x) > 3 * fs / BAND[0]:
        lo, hi = BAND[0], min(BAND[1], 0.45 * fs)
        x *= tukey(len(x), min(1.0, 2 * fs / BAND[0] / len(x)))[:, None].astype(np.float32)
        x = sosfiltfilt(butter(4, [lo, hi], "bandpass", fs=fs, output="sos"), x, axis=0).astype(np.float32)
    common = np.median(x, axis=1, keepdims=True)
    shares.append(float(np.var(common) / np.mean(np.var(x, axis=0))))
    if COMMON_MODE:
        x -= common
    out_t.append(t)
    out_x.append(x)
t, x = np.concatenate(out_t), np.concatenate(out_x)
inside = (t >= np.datetime64(start)) & (t < np.datetime64(end))
t, x = t[inside], x[inside]
units = "1/s" if OUTPUT == "strain_rate" else "1"
print(f"common mode (the median across channels) held {100 * np.mean(shares):.0f} % of the mean channel's variance"
      f"{' and was taken out' if COMMON_MODE else ' (COMMON_MODE = True takes it out)'}")

# 4. Per-channel quality against the channels around it (signals like whale calls are louder over kilometres, a bad
#    channel alone): dead (no signal, or a tenth of its neighbours') and noisy (three times its neighbours').
rms = np.sqrt(np.mean(x.astype(np.float64) ** 2, axis=0))
around = pd.Series(rms).rolling(51, center=True, min_periods=1).median().to_numpy()
dead = (rms == 0) | ~np.isfinite(rms) | (rms < 0.1 * around)
loud = (rms > 3 * around) & ~dead
print(f"{len(t)} samples ({(t[-1] - t[0]) / np.timedelta64(1, 's') + dt:.1f} s); median rms {np.median(rms):.3g} "
      f"{units}; dead channels {dead.sum()}, noisy {loud.sum()} (against the 51 channels around each)")

# 5. Save: NetCDF with time and distance (and latitude, longitude and depth for das2021, from the portal's geometry).
ds = xr.Dataset({OUTPUT: (("time", "distance"), x, {"units": units})},
                coords={"time": t,
                        "distance": ("distance", distance, {"units": "m", "long_name": "optical distance along the fibre"}),
                        "channel": ("distance", channels)})
if EXPERIMENT == "das2021":
    geo = pd.read_csv(f"{PORTAL}/das/processed/metadata/Geometry/OOI_RCA_DAS_channel_location_with_depth/"
                      f"{CABLE}_DAS_latlondepth.txt", sep=r"\s+", header=None, names=["channel", "lat", "lon", "elev"])
    geo = geo.set_index(geo["channel"].astype(int)).reindex(channels)
    ds = ds.assign_coords(latitude=("distance", geo["lat"].to_numpy()), longitude=("distance", geo["lon"].to_numpy()),
                          water_depth=("distance", -geo["elev"].to_numpy(), {"units": "m"}))
    print(f"channels {DIST_KM[0]:g}-{DIST_KM[1]:g} km lie at {geo['lat'].min():.3f}-{geo['lat'].max():.3f} N, "
          f"{geo['lon'].min():.3f}-{geo['lon'].max():.3f} E, in {-geo['elev'].max():.0f}-{-geo['elev'].min():.0f} m of water "
          f"({geo['lat'].isna().sum()} channels outside the portal's geometry file)")
ds.attrs.update({k: v for k, v in info.items()},
                experiment=EXPERIMENT, cable=CABLE, band_hz=str(BAND), source_files=" ".join(chosen),
                citation={"das2021": "Wilcock et al. 2023, Rapid: A Community Test of Distributed Acoustic Sensing on the "
                                     "OOI RCA, doi:10.58046/5J60-FJ89",
                          "das24": "Lipovsky, Williams et al. 2024, RAPID: Multiplexed DAS at the OOI RCA, "
                                   "doi:10.58046/4WEF-A282",
                          "das25": "Dienstfrey, Lipovsky, Wilcock, Krauss 2026, Multi-span DAS on the OOI RCA 2025-2026: "
                                   "OptoDAS data, doi:10.5281/zenodo.19930457"}[EXPERIMENT])
name = f"{EXPERIMENT}_{CABLE}_{start:%Y%m%dT%H%M%S}_{DIST_KM[0]:g}-{DIST_KM[1]:g}km_{OUTPUT}"
ds.to_netcdf(name + ".nc")
pd.DataFrame({"distance_m": distance, "channel": channels, "rms": rms, "dead": dead, "noisy": loud}).to_csv(
    name + "_channels.csv", index=False)

# 6. Waterfall: distance against time, colour clipped at the 99th percentile.
fig, (a, b) = plt.subplots(1, 2, figsize=(12, 6), gridspec_kw={"width_ratios": [4, 1]}, sharey=True)
clip = np.percentile(np.abs(x), 99)
seconds = (t - t[0]) / np.timedelta64(1, "s")
a.imshow(x.T, aspect="auto", cmap="RdBu_r", vmin=-clip, vmax=clip, origin="lower", interpolation="none",
         extent=[seconds[0], seconds[-1], distance[0] / 1e3, distance[-1] / 1e3])
a.set_xlabel(f"seconds after {pd.Timestamp(t[0]):%Y-%m-%d %H:%M:%S} UTC")
a.set_ylabel("optical distance along the fibre (km)")
a.set_title(f"{EXPERIMENT} {CABLE}: {OUTPUT.replace('_', ' ')} ({units}), {BAND or 'unfiltered'} Hz", fontsize=10)
b.plot(rms, distance / 1e3, "k", lw=0.6)
b.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
b.plot(rms[dead | loud], distance[dead | loud] / 1e3, "r.", ms=3)
b.set_xlabel("rms")
fig.tight_layout()
fig.savefig(name + ".png", dpi=130)
