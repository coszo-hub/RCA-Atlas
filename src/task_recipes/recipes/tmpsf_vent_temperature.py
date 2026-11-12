# pip install erddapy pandas numpy xarray netCDF4 utide matplotlib requests
import re
import numpy as np
import pandas as pd
import requests
import xarray as xr
import utide
from erddapy import ERDDAP
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATASET = "ooi-rs03ashs-mj03b-07-tmpsfa301"   # the ASHES diffuse-flow array: 24 thermistors, one value a minute
CTD = "ooi-rs03ashs-mj03b-10-ctdpfb304"       # the CTD on the same junction box: the ambient seawater
BOTPT = "RS03ASHS-MJ03B-09-BOTPTA304"         # the pressure gauge beside it: the ocean tide (Gold Copy 15-s means)
START, END = "2019-03-01", "2019-04-01"       # UTC; END is not included
AVERAGE = "1h"                                # the averaging period
DROP = [4]                                    # QARTOD flags dropped (4 fail); add 3 to drop suspect
WARM = 0.5                                    # degrees C above the ambient (median) for a probe to count as warm
                                              # (the coldest probes read 0.1-0.2 C above the CTD, a few metres higher)
FLAT_MINUTES = 60                             # a probe repeating one value this long is stuck
ERDDAP_URL = "https://erddap.dataexplorer.oceanobservatories.org/erddap"
THREDDS = "https://thredds.dataexplorer.oceanobservatories.org/thredds"

probes = [f"tempsfl_{i:02d}" for i in range(1, 25)]
start, end = pd.Timestamp(START), pd.Timestamp(END)
e = ERDDAP(server=ERDDAP_URL, protocol="tabledap", response="csv")


def erddap(dataset, variables, a, b, extra=""):
    e.dataset_id, e.variables = dataset, variables
    e.constraints = {"time>=": f"{a:%Y-%m-%dT%H:%M:%SZ}", "time<": f"{b:%Y-%m-%dT%H:%M:%SZ}"}
    return pd.read_csv(e.get_download_url() + extra, skiprows=[1], index_col="time", parse_dates=True)


# 1. The thermistors and their QARTOD flags, a month at a time (49 columns of a row a minute).
parts = []
for month in pd.date_range(start.normalize(), end, freq="MS", inclusive="both").union([start]):
    a, b = max(month, start), min(month + pd.offsets.MonthBegin(1), end)
    if a < b:
        try:
            parts.append(erddap(DATASET, ["time"] + probes + [f"{p}_qc_agg" for p in probes], a, b))
        except Exception as error:   # ERDDAP answers 404 for a month with no data
            print(f"{a:%Y-%m}: no data ({type(error).__name__})")
if not parts:
    raise SystemExit(f"no TMPSF data between {START} and {END}")
df = pd.concat(parts).sort_index()
df = df[~df.index.duplicated()]
df.index = df.index.tz_localize(None)
minutes = int((min(end, df.index[-1].ceil("1min")) - max(start, df.index[0].floor("1min"))).total_seconds() / 60)
temps = df[probes].where(~df[[f"{p}_qc_agg" for p in probes]].isin(DROP).to_numpy())

# 2. Each probe's record: coverage, flags, stuck runs, and how far above the ambient (the CTD's hourly mean) it reads.
ambient = erddap(CTD, ["time", "sea_water_temperature"], start, end, '&orderByMean("time/1hour")')["sea_water_temperature"]
ambient.index = ambient.index.tz_localize(None)
hourly = temps.resample(AVERAGE).mean()
hourly[temps.resample(AVERAGE).count() < 0.5 * pd.Timedelta(AVERAGE).total_seconds() / 60] = np.nan
excess = hourly.sub(ambient.reindex(hourly.index, method="nearest", tolerance=pd.Timedelta("1h")), axis=0)
rows = []
for p in probes:
    x = df[p]
    runs = x.ne(x.shift()).cumsum()
    stuck = x.groupby(runs).transform("size").where(x.notna(), 0) >= FLAT_MINUTES
    rows.append({"probe": int(p[-2:]), "coverage_pct": 100 * temps[p].count() / max(minutes, 1),
                 "flagged": int(df[f"{p}_qc_agg"].isin(DROP).sum()), "stuck_minutes": int(stuck.sum()),
                 "median_C": temps[p].median(), "p95_C": temps[p].quantile(0.95), "max_C": temps[p].max(),
                 "above_ambient_C": excess[p].median()})
table = pd.DataFrame(rows)
table["warm"] = table["above_ambient_C"] > WARM
print(f"ambient (CTD): median {ambient.median():.3f} C; probes warmer than it by over {WARM} C: "
      f"{', '.join(str(n) for n in table.loc[table['warm'], 'probe']) or 'none'}")
print(table.round(3).to_string(index=False))

# 3. The tide in the warm probes: UTide fitted to each warm probe's hourly temperature and to the bottom pressure
#    beside it, and the hours by which the temperature's cycle lags the pressure's (positive: warmest after high tide).
tides = []
if (end - start).days >= 15 and table["warm"].any():
    folder = f"ooigoldcopy/public/{BOTPT}-streamed-botpt_nano_sample_15sec"
    listing = requests.get(f"{THREDDS}/catalog/{folder}/catalog.xml", timeout=120).text
    pres = []
    for path in sorted(set(re.findall(r'urlPath="([^"]+\.nc)"', listing))):
        a, b = (pd.Timestamp(x[:15]) for x in re.search(r"_(\d{8}T\d{6})[\d.]*-(\d{8}T\d{6})[\d.]*\.nc$", path).groups())
        if b >= start and a < end:
            ds = xr.open_dataset(f"{THREDDS}/dodsC/{path}")
            pres.append(ds["botsflu_meanpres"].swap_dims({"obs": "time"}).sel(time=slice(start, end)).to_series())
    pressure = pd.concat(pres).sort_index().resample("1h").mean() * 0.6894757 if pres else pd.Series(dtype=float)
    lat = 45.93
    if pressure.notna().sum() > 15 * 24:
        cp = utide.solve(pressure.dropna().index, pressure.dropna().to_numpy(), lat=lat, method="ols",
                         conf_int="linear", verbose=False)
        ref = dict(zip(cp["name"], zip(cp["A"], cp["g"])))
        print(f"tide in pressure: M2 {ref['M2'][0]:.3f} dbar, K1 {ref['K1'][0]:.3f} dbar")
    else:
        ref = {}
        print("no Gold Copy pressure for the span: tidal amplitudes only, no lag")
    period = {"M2": 12.4206, "S2": 12.0, "N2": 12.6583, "K1": 23.9345, "O1": 25.8193}
    for p in table.loc[table["warm"], "probe"]:
        x = hourly[f"tempsfl_{p:02d}"].dropna()
        if len(x) < 15 * 24:
            continue
        ct = utide.solve(x.index, x.to_numpy(), lat=lat, method="ols", conf_int="linear", trend=True, verbose=False)
        fit = utide.reconstruct(x.index, ct, verbose=False).h
        share = 1 - np.var(x.to_numpy() - fit) / np.var(x.to_numpy())
        for name_, amp, phase in zip(ct["name"], ct["A"], ct["g"]):
            if name_ in ("M2", "K1", "S2", "O1"):
                lag = ((phase - ref[name_][1] + 180) % 360 - 180) / 360 * period[name_] if name_ in ref else np.nan
                tides.append({"probe": p, "constituent": name_, "amplitude_C": amp, "phase_deg": phase,
                              "lag_after_pressure_h": lag, "tidal_share_of_variance": share})
    tides = pd.DataFrame(tides)
    if len(tides):
        print("tides in the warm probes (lag: hours after the pressure's same constituent):")
        print(tides.round(3).to_string(index=False))

name = f"{DATASET}_{START}_{END}"
hourly.rename_axis("time_utc").to_csv(name + f"_{AVERAGE}.csv", float_format="%.4f")
table.to_csv(name + "_probes.csv", index=False, float_format="%.4f")
if len(tides):
    tides.to_csv(name + "_tides.csv", index=False, float_format="%.4f")

# 4. Plot: every probe's temperature (warm ones coloured) with the ambient; each probe's excess over ambient.
fig, (a, b) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1.3]})
for p in probes:
    warm = bool(table.loc[table["probe"] == int(p[-2:]), "warm"].iloc[0])
    a.plot(hourly.index, hourly[p], lw=0.8 if warm else 0.4, color=None if warm else "0.7",
           label=f"probe {int(p[-2:])}" if warm else None, zorder=3 if warm else 1)
a.plot(ambient.index, ambient, "k--", lw=0.8, label="ambient (CTD)")
a.set_ylabel(f"temperature (C), {AVERAGE} means")
a.legend(loc="upper left", fontsize=7, ncol=4)
a.set_title(f"{DATASET}: grey probes are within {WARM} C of the ambient", fontsize=10)
b.bar(table["probe"], table["above_ambient_C"], color=np.where(table["warm"], "tab:red", "0.6"))
b.axhline(WARM, color="k", lw=0.6, ls=":")
b.set_xticks(table["probe"])
b.set_xlabel("probe")
b.set_ylabel("median above ambient (C)")
fig.tight_layout()
fig.savefig(name + ".png", dpi=130)
