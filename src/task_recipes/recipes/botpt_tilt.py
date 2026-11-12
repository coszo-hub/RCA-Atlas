# pip install xarray netCDF4 pandas numpy matplotlib requests
import re
import numpy as np
import pandas as pd
import requests
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFDES = "RS03ECAL-MJ03E-06-BOTPTA302"   # Axial's BOTPTs: MJ03E eastern caldera, RS03CCAL-MJ03F-05-BOTPTA301 caldera centre,
                                         # RS03INT2-MJ03D-06-BOTPTA303 International District, RS03ASHS-MJ03B-09-BOTPTA304 ASHES
START, END = "2016-01-01", "2020-01-01"  # UTC; END is not included
STEP = 60          # seconds: one of every STEP of the 1-Hz LILY samples is read (60: one a minute; 1: every sample)
AVERAGE = "1h"     # the averaging period of the saved and plotted series ("1h", "1D")
JUMP = 10.0        # microradians between samples STEP apart: faster than this is the instrument, not the ground
GAP_JUMP = 10.0    # microradians across a gap of more than an hour: an offset while no data came (or real tilt; see the list)
REMOVE = ("relevel", "across gap", "step")   # the kinds of step taken out; leave out "step" or "across gap" to keep
                   # them (an eruption tilts the ground hundreds of microradians in hours: April 2015 needs a look)
CLIP = 329.9       # the LILY reads +-330 microradians at most; samples beyond this are clipped and dropped
WARMUP = 0.1       # degrees C: after a gap of over an hour the LILY restarts cold (unpowered, it cools ~1.5 C) and its tilt
                   # is 15-25 microradians off until it warms, ~12 hours; samples are dropped until its temperature is
                   # within this of the hour before the gap
THREDDS = "https://thredds.dataexplorer.oceanobservatories.org/thredds"

# 1. The Gold Copy's LILY samples (1 Hz, 2014 to now at all four sites), every file overlapping the span, read over
#    OPeNDAP one in STEP so only those are downloaded.
folder = f"ooigoldcopy/public/{REFDES}-streamed-botpt_lily_sample"
listing = requests.get(f"{THREDDS}/catalog/{folder}/catalog.xml", timeout=120).text
if "urlPath" not in listing:   # no such folder: a designator written short (RS03CCAL-MJ03F-BOTPTA301) is matched in full
    top = requests.get(f"{THREDDS}/catalog/ooigoldcopy/public/catalog.xml", timeout=120).text
    full = [t.split("-streamed-")[0] for t in re.findall(r'title="([^"]+-streamed-botpt_lily_sample)"', top)
            if set(REFDES.upper().split("-")) <= set(t.split("-"))]
    if len(full) != 1:
        raise SystemExit(f"no Gold Copy LILY folder for {REFDES}; name it in full ({', '.join(full) or 'none match'})")
    print(f"{REFDES} is {full[0]}")
    REFDES = full[0]
    folder = f"ooigoldcopy/public/{REFDES}-streamed-botpt_lily_sample"
    listing = requests.get(f"{THREDDS}/catalog/{folder}/catalog.xml", timeout=120).text
start, end = pd.Timestamp(START), pd.Timestamp(END)
names = ["lily_x_tilt", "lily_y_tilt", "corrected_compass_direction", "lily_temp", "seafloor_tilt_magnitude_qartod_results"]
parts, broken = [], []
for path in sorted(set(re.findall(r'urlPath="([^"]+\.nc)"', listing))):
    a, b = (pd.Timestamp(x[:15]) for x in re.search(r"_(\d{8}T\d{6})[\d.]*-(\d{8}T\d{6})[\d.]*\.nc$", path).groups())
    if b < start or a >= end:
        continue
    try:
        ds = xr.open_dataset(f"{THREDDS}/dodsC/{path}")
        sub = ds[names].isel(obs=slice(None, None, STEP)).swap_dims({"obs": "time"}).sel(time=slice(start, end))
        parts.append(sub.to_dataframe()[names])
    except OSError:   # a few Gold Copy files fail on the server (DAP error 500, java.io.EOFException)
        broken.append(f"{a:%Y-%m-%d}-{b:%Y-%m-%d}")
if broken:
    print("unreadable Gold Copy files (a gap in what follows):", ", ".join(broken))
if not parts:
    raise SystemExit(f"no Gold Copy LILY tilt for {REFDES} from {START} to {END}")
df = pd.concat(parts).sort_index()
df = df[~df.index.duplicated() & (df.index >= start) & (df.index < end)]
df.columns = ["x", "y", "ccmp", "temp", "qartod"]
print(f"{len(df)} samples, {df.index[0]} to {df.index[-1]}; QARTOD flags on the tilt magnitude: "
      f"{df['qartod'].value_counts().sort_index().to_dict()}")
clipped = (df["x"].abs() > CLIP) | (df["y"].abs() > CLIP)
df.loc[clipped, ["x", "y"]] = np.nan
print(f"{clipped.sum()} samples at the LILY's +-330 microradian limit dropped")
warming, restarts = pd.Series(False, index=df.index), 0
for i in np.flatnonzero(df.index.to_series().diff() > pd.Timedelta(hours=1)):
    t, last = df.index[i], df.index[i - 1]   # the first sample after the gap, and the last before it
    before = df.loc[(df.index <= last) & (df.index > last - pd.Timedelta(hours=1)), "temp"].median()
    later = df.loc[(df.index >= t) & (df.index < t + pd.Timedelta(days=3)), "temp"]
    if np.isnan(before) or not len(later) or later.iloc[0] >= before - WARMUP:
        continue
    warm = later.index[later >= before - WARMUP]
    warming[(df.index >= t) & (df.index < (warm[0] if len(warm) else later.index[-1]))] = True
    restarts += 1
df.loc[warming, ["x", "y"]] = np.nan
print(f"{restarts} restarts after a gap: {warming.sum()} samples while the LILY warmed up dropped")

# 2. Steps. A relevel: the LILY drives itself back to level when its tilt nears its range, so x and y go to near zero
#    within minutes. A step: a jump of more than JUMP between samples under an hour apart, not a relevel. Across a
#    gap: a jump of more than GAP_JUMP while no data came. Each one's size is the change from the hour before to the
#    hour after, and those of the kinds in REMOVE are taken out of everything after them.
ok = df[["x", "y"]].dropna()
dt = ok.index.to_series().diff().dt.total_seconds()
change = ok.diff().abs().max(axis=1)
gap = (dt > 3600) & (change > GAP_JUMP)
marks = ok.index[((change > JUMP) & (dt <= 3600)) | gap]   # a relevel sends nothing for 4-10 minutes
events = []   # [first, last] time of each step
for t in marks:
    if events and (t - events[-1][1]) <= pd.Timedelta(minutes=30) and not gap[t]:
        events[-1][1] = t
    else:
        events.append([ok.index[ok.index.get_loc(t) - 1], t])
rows = []
for first, last in events:
    before = ok[(ok.index > first - pd.Timedelta(hours=1)) & (ok.index <= first)].median()
    after = ok[(ok.index >= last) & (ok.index < last + pd.Timedelta(hours=1))].median()
    d = after - before
    if max(abs(d["x"]), abs(d["y"])) < JUMP:
        continue   # back where it was within the hour: a spike, not a step
    hours = (last - first).total_seconds() / 3600
    kind = ("relevel" if max(abs(after["x"]), abs(after["y"])) < 25 and max(abs(d["x"]), abs(d["y"])) > 50
            else "across gap" if hours > 1 else "step")
    rows.append({"start": first, "end": last, "kind": kind, "hours": round(hours, 1),
                 **{k: round(float(v), 1) for k, v in (("x_before", before["x"]), ("y_before", before["y"]),
                    ("x_after", after["x"]), ("y_after", after["y"]), ("dx", d["x"]), ("dy", d["y"]))}})
steps = pd.DataFrame(rows, columns=["start", "end", "kind", "hours", "x_before", "y_before", "x_after", "y_after", "dx", "dy"])
df["x_stitched"], df["y_stitched"] = df["x"], df["y"]
for _, s in steps[steps["kind"].isin(REMOVE)].iterrows():   # samples during a step are dropped, those after shifted back
    df.loc[(df.index > s["start"]) & (df.index < s["end"]), ["x_stitched", "y_stitched"]] = np.nan
    df.loc[df.index >= s["end"], "x_stitched"] -= s["dx"]
    df.loc[df.index >= s["end"], "y_stitched"] -= s["dy"]
print(f"{len(steps)} steps ({', '.join(f'{n} {k}' for k, n in steps['kind'].value_counts().items()) or 'none'}); "
      f"taken out: {', '.join(REMOVE)}")
if len(steps):
    print(steps.to_string(index=False))

# 3. East and north: x and y are the instrument's own axes. OOI's corrected compass (ccmp, its per-sensor lookup on
#    the LILY's compass, which a steel frame bends) gives y's bearing, and x points 90 degrees clockwise of it;
#    rotating by it reproduces OOI's seafloor_tilt_direction (450 - atan2(y, x) + ccmp, mod 360).
ccmp = df["ccmp"].median()
spread = df["ccmp"].quantile([0.05, 0.95]).to_numpy()
print(f"corrected compass: median {ccmp:.0f} degrees (5-95 %: {spread[0]:.0f}-{spread[1]:.0f}); y points there, x at "
      f"{(ccmp + 90) % 360:.0f}")
c = np.radians(ccmp)
df["east"] = df["x_stitched"] * np.cos(c) + df["y_stitched"] * np.sin(c)
df["north"] = df["y_stitched"] * np.cos(c) - df["x_stitched"] * np.sin(c)

# 4. Averages, and the tilt change over the span (from the first to the last day's mean).
mean = df[["x", "y", "x_stitched", "y_stitched", "east", "north", "temp"]].resample(AVERAGE).mean()
mean["count"] = df["x"].resample(AVERAGE).count()
mean["magnitude"] = np.hypot(mean["east"], mean["north"])
mean["direction"] = np.degrees(np.arctan2(mean["east"], mean["north"])) % 360
day = df[["east", "north"]].resample("1D").mean().dropna()
if len(day) > 1:
    de, dn = day.iloc[-1] - day.iloc[0]
    years = (day.index[-1] - day.index[0]).days / 365.25
    print(f"tilt change {day.index[0]:%Y-%m-%d} to {day.index[-1]:%Y-%m-%d}: east {de:+.1f}, north {dn:+.1f} microradians, "
          f"{np.hypot(de, dn):.1f} toward {np.degrees(np.arctan2(de, dn)) % 360:.0f} degrees "
          f"({np.hypot(de, dn) / years:.1f} microradians a year) in OOI's direction convention")

name = f"{REFDES}_{START}_{END}_tilt"
mean.rename_axis("time_utc").to_csv(name + f"_{AVERAGE}.csv", float_format="%.3f")
steps.to_csv(name + "_steps.csv", index=False, float_format="%.3f")

# 5. Plot: the recorded x and y with the steps marked; east and north after stitching; the path of the tilt.
fig = plt.figure(figsize=(12, 9))
a = fig.add_subplot(3, 2, (1, 2))
b = fig.add_subplot(3, 2, (3, 4), sharex=a)
h = fig.add_subplot(3, 2, 5)
a.plot(mean.index, mean["x"], lw=0.7, label="x (recorded)")
a.plot(mean.index, mean["y"], lw=0.7, label="y (recorded)")
for t in steps.get("end", []):
    a.axvline(t, color="r", lw=0.6, ls=":")
a.set_ylabel("microradians")
a.legend(loc="upper left", fontsize=8)
a.set_title(f"{REFDES} LILY tilt ({AVERAGE} means); dotted: relevels and jumps taken out", fontsize=10)
b.plot(mean.index, mean["east"], lw=0.8, label="east")
b.plot(mean.index, mean["north"], lw=0.8, label="north")
b.set_ylabel("stitched tilt (microradians)")
b.legend(loc="upper left", fontsize=8)
path = h.scatter(mean["east"], mean["north"], c=mean.index.year + mean.index.day_of_year / 366, s=2, cmap="viridis")
h.set_xlabel("east")
h.set_ylabel("north")
h.set_aspect("equal", "datalim")
fig.colorbar(path, ax=h, label="year")
t = fig.add_subplot(3, 2, 6, sharex=a)
t.plot(mean.index, mean["temp"], "k", lw=0.6)
t.set_ylabel("LILY temperature (C)")
for ax in (a, b, t):
    ax.tick_params(axis="x", labelbottom=True, labelrotation=30)
fig.tight_layout()
fig.savefig(name + ".png", dpi=130)
