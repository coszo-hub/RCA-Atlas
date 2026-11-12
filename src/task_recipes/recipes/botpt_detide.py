# pip install xarray netCDF4 pandas gsw utide matplotlib requests
import copy
import re
import numpy as np
import pandas as pd
import requests
import xarray as xr
import gsw
import utide
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REFDES = "RS03CCAL-MJ03F-05-BOTPTA301"   # Axial's BOTPTs: MJ03F caldera centre, RS03ECAL-MJ03E-06-BOTPTA302 eastern rim,
                                         # RS03INT2-MJ03D-06-BOTPTA303 International District, RS03ASHS-MJ03B-09-BOTPTA304 ASHES
START, END = "2025-01-01", "2025-04-01"  # UTC; END is not included
FIT_DAYS = 365                           # the tide is fitted to this many days ending at END (a year separates K1 from
                                         # P1 and S2 from K2; less leaves their beat in the residual)
GODIN = True                             # also the Godin low-pass (24, 24 and 25-hour running means), with no tide model
THREDDS = "https://thredds.dataexplorer.oceanobservatories.org/thredds"
PSI_TO_DBAR = 0.6894757
ATMOSPHERE_DBAR = 10.1325                # the gauge reads absolute pressure: sea pressure is this much less

# 1. The Gold Copy's 15-second mean pressure (OOI's BOTSFLU product), every deployment's files that overlap the span,
#    read over OPeNDAP so only the span is downloaded.
folder = f"ooigoldcopy/public/{REFDES}-streamed-botpt_nano_sample_15sec"
listing = requests.get(f"{THREDDS}/catalog/{folder}/catalog.xml", timeout=120).text
if "urlPath" not in listing:   # no such folder: a designator written short (RS03CCAL-MJ03F-BOTPTA301) is matched in full
    top = requests.get(f"{THREDDS}/catalog/ooigoldcopy/public/catalog.xml", timeout=120).text
    full = [t.split("-streamed-")[0] for t in re.findall(r'title="([^"]+-streamed-botpt_nano_sample_15sec)"', top)
            if set(REFDES.upper().split("-")) <= set(t.split("-"))]
    if len(full) != 1:
        raise SystemExit(f"no Gold Copy BOTPT folder for {REFDES}; name it in full ({', '.join(full) or 'none match'})")
    print(f"{REFDES} is {full[0]}")
    REFDES = full[0]
    folder = f"ooigoldcopy/public/{REFDES}-streamed-botpt_nano_sample_15sec"
    listing = requests.get(f"{THREDDS}/catalog/{folder}/catalog.xml", timeout=120).text
start, end = pd.Timestamp(START), pd.Timestamp(END)
fit_start = min(start, end - pd.Timedelta(days=FIT_DAYS))
parts = []
for path in sorted(set(re.findall(r'urlPath="([^"]+\.nc)"', listing))):
    a, b = (pd.Timestamp(x[:15]) for x in re.search(r"_(\d{8}T\d{6})[\d.]*-(\d{8}T\d{6})[\d.]*\.nc$", path).groups())
    if b < fit_start or a >= end:
        continue
    ds = xr.open_dataset(f"{THREDDS}/dodsC/{path}")
    lat = float(ds["lat"].values.ravel()[0]) if "lat" in ds else 45.95
    sub = ds[["botsflu_meanpres", "botsflu_meandepth"]].swap_dims({"obs": "time"}).sel(time=slice(fit_start, end))
    parts.append(sub.to_dataframe()[["botsflu_meanpres", "botsflu_meandepth"]])
if not parts:
    raise SystemExit(f"no Gold Copy 15-s pressure for {REFDES} from {START} to {END}")
df = pd.concat(parts).sort_index()
df = df[~df.index.duplicated() & (df.index >= fit_start) & (df.index < end) & (df["botsflu_meanpres"] > 0)]
print(f"{len(df)} 15-s means, {df.index[0]} to {df.index[-1]} (the tide's fit; the products are for {START} to {END})")

# 2. Pressure to depth: sea pressure (absolute minus one atmosphere) in dbar, depth from TEOS-10 at the site's latitude.
p_sea = df["botsflu_meanpres"] * PSI_TO_DBAR - ATMOSPHERE_DBAR
df["depth_m"] = -gsw.z_from_p(p_sea.to_numpy(), lat)
# OOI's de-tided depth (its BOTSFLU product: -0.67 m per psi plus a tide model's prediction), for comparison
df["ooi_detided_m"] = -df["botsflu_meandepth"]
hourly = df[["depth_m", "ooi_detided_m"]].resample("1h").mean()
hourly[df["depth_m"].resample("1h").count() < 120] = np.nan   # an hour needs half its 240 means

# 3. The tide: a harmonic fit (UTide, with a linear trend so uplift does not leak into the tides) to the hourly depths
#    of the fit's span, predicted for the span asked for. Only the daily and faster tides are taken away: the
#    fortnightly, monthly and seasonal ones are as much ocean and volcano as tide, so they stay in the residual.
ok = hourly["depth_m"].notna()
coef = utide.solve(hourly.index[ok], hourly.loc[ok, "depth_m"].to_numpy(), lat=lat, method="ols", conf_int="linear",
                   trend=True, verbose=False)
short = [n for n, f in zip(coef["name"], coef["aux"]["frq"]) if f * 24 > 0.5]   # cycles per hour -> per day
hourly = hourly[(hourly.index >= start) & (hourly.index < end)].copy()
bare = copy.deepcopy(coef)
bare["mean"], bare["slope"] = 0.0, 0.0
mean_trend = (utide.reconstruct(hourly.index, coef, constit=[short[0]], verbose=False).h
              - utide.reconstruct(hourly.index, bare, constit=[short[0]], verbose=False).h)   # the fit's mean and trend
tide = utide.reconstruct(hourly.index, coef, constit=short, verbose=False).h - mean_trend
hourly["utide_tide_m"] = tide
hourly["utide_detided_m"] = hourly["depth_m"] - tide
if GODIN:   # A24 A24 A25: removes the daily and twice-daily tides; the first and last 35 hours are lost
    hourly["godin_m"] = (hourly["depth_m"].rolling(24, center=True).mean().rolling(24, center=True).mean()
                         .rolling(25, center=True).mean())

# 4. How much tide each leaves: the hourly de-tided depth's spread about its own 2-day running mean (the Godin
#    low-pass has none by construction), and the trend.
def rms(x):
    return float(np.sqrt(np.nanmean((x - x.rolling(49, center=True, min_periods=25).mean()) ** 2)) * 100)
print(f"tide left (cm rms): UTide {rms(hourly['utide_detided_m']):.2f}, OOI BOTSFLU {rms(hourly['ooi_detided_m']):.2f}")
order = np.argsort(-coef["A"])[:8]
print("largest tides:", ", ".join(f"{coef['name'][i]} {coef['A'][i] * 100:.1f} cm" for i in order))
ok = hourly["utide_detided_m"].notna()
days = (hourly.index[ok] - hourly.index[0]).total_seconds() / 86400
rate = np.polyfit(days, hourly.loc[ok, "utide_detided_m"], 1)[0] * 365.25 * 100
print(f"de-tided depth trend over {START} to {END}: {rate:.1f} cm/yr; over the fit's year: "
      f"{coef['slope'] * 365.25 * 100:.1f} cm/yr (negative: the seafloor rose)")

name = f"{REFDES}_{START}_{END}"
hourly.rename_axis("time_utc").to_csv(name + "_hourly.csv", float_format="%.4f")
pd.DataFrame({"constituent": coef["name"], "amplitude_m": coef["A"], "phase_deg": coef["g"],
              "amplitude_ci_m": coef["A_ci"]}).to_csv(name + "_tides.csv", index=False, float_format="%.5f")

# 5. Plot: the depth with the fitted tide; the de-tided depths (each about its own mean) with the trend.
fig, (a, b) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
a.plot(hourly.index, hourly["depth_m"], "k", lw=0.5, label="depth (hourly)")
a.plot(hourly.index, hourly["depth_m"].mean() + hourly["utide_tide_m"], "c", lw=0.5, label="UTide tide")
a.invert_yaxis(); a.set_ylabel("depth (m)"); a.legend(loc="upper right")
for col, style, label in (("utide_detided_m", "k", "UTide"), ("ooi_detided_m", "tab:orange", "OOI BOTSFLU"),
                          ("godin_m", "tab:blue", "Godin")):
    if col in hourly:
        b.plot(hourly.index, (hourly[col] - hourly[col].mean()) * 100, style, lw=0.7, label=label)
b.invert_yaxis(); b.set_ylabel("de-tided depth change (cm)\nup is shallower"); b.legend(loc="upper right")
a.set_title(f"{REFDES}: depth from the Gold Copy 15-s mean pressure, {START} to {END}")
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
