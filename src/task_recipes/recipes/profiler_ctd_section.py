# pip install erddapy pandas matplotlib gsw
import gsw
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from erddapy import ERDDAP

DATASET = "ooi-rs01sbps-sf01a-2a-ctdpfa102"         # the shallow profiler's CTD: Slope Base, or Axial Base ooi-rs03axps-sf03a-2a-ctdpfa302
LAT, LON = 44.53, -125.39                           # the site, for TEOS-10 (Axial Base: 45.83, -129.75)
START, END = "2025-06-01T00:00:00Z", "2025-06-08T00:00:00Z"   # the span, UTC (a week is ~30,000 rows; months: a month at a time)
VARIABLES = {                                       # what to plot: ERDDAP name -> label
    "sea_water_temperature_profiler_depth_enabled": "temperature (°C)",
    "sea_water_practical_salinity_profiler_depth_enabled": "practical salinity",
    "moles_of_oxygen_per_unit_mass_in_sea_water_profiler_depth_enabled": "dissolved oxygen (µmol/kg)",
}
PRESSURE = "sea_water_pressure_profiler_depth_enabled"

e = ERDDAP(server="https://erddap.dataexplorer.oceanobservatories.org/erddap", protocol="tabledap", response="csv")
e.dataset_id = DATASET
names = [PRESSURE, *VARIABLES]
e.variables = ["time", *names, *(f"{n}_qc_agg" for n in names)]
e.constraints = {"time>=": START, "time<=": END}
df = pd.read_csv(e.get_download_url(), skiprows=[1], parse_dates=["time"])
for n in names:   # QARTOD: a value flagged 4 (FAIL) or 9 (MISSING) is dropped; 3 (SUSPECT) is kept
    df.loc[df[f"{n}_qc_agg"].isin([4, 9]), n] = np.nan
df = df.dropna(subset=[PRESSURE])
if df.empty:
    raise SystemExit(f"no {DATASET} data between {START} and {END}")
DEPTH = "depth (m)"   # from pressure (TEOS-10): the dataset's own depth column is empty at some sites
df[DEPTH] = -gsw.z_from_p(df[PRESSURE], LAT)
if df[DEPTH].max() - df[DEPTH].min() < 20:   # parked at its 200 m platform, as Axial Base's was in June-August 2025
    print(f"the profiler moved only between {df[DEPTH].min():.0f} and {df[DEPTH].max():.0f} m in this span: it was not profiling")

# Section: each sample at its time and depth, coloured by its value (the profiler climbs from ~200 m to near the
# surface and back, nine profiles a day).
fig, axes = plt.subplots(len(VARIABLES), 1, sharex=True, figsize=(11, 2.8 * len(VARIABLES)), squeeze=False)
for ax, (n, label) in zip(axes[:, 0], VARIABLES.items()):
    ok = df[n].notna()
    points = ax.scatter(df["time"][ok], df[DEPTH][ok], c=df[n][ok], s=4, cmap="viridis",
                        vmin=df[n].quantile(0.01), vmax=df[n].quantile(0.99))
    ax.invert_yaxis()
    ax.set_ylabel("depth (m)")
    fig.colorbar(points, ax=ax, label=label)
axes[0, 0].set_title(f"{DATASET}, {START[:10]} to {END[:10]}")
fig.autofmt_xdate()
fig.tight_layout()
name = f"{DATASET}_{START[:10]}_{END[:10]}"
fig.savefig(name + "_section.png", dpi=150)

# T-S diagram with potential density (sigma0, TEOS-10) contours, each sample coloured by depth.
T, SP, p = (df[k] for k in ("sea_water_temperature_profiler_depth_enabled",
                            "sea_water_practical_salinity_profiler_depth_enabled", PRESSURE))
ok = T.notna() & SP.notna() & p.notna()
SA = gsw.SA_from_SP(SP[ok], p[ok], LON, LAT)
CT = gsw.CT_from_t(SA, T[ok], p[ok])
s_grid, t_grid = np.meshgrid(np.linspace(SA.min() - 0.1, SA.max() + 0.1, 100), np.linspace(CT.min() - 0.5, CT.max() + 0.5, 100))
fig, ax = plt.subplots(figsize=(7, 6))
lines = ax.contour(s_grid, t_grid, gsw.sigma0(s_grid, t_grid), colors="0.6", linewidths=0.7)
ax.clabel(lines, fmt="%.1f", fontsize=8)
points = ax.scatter(SA, CT, c=df[DEPTH][ok], s=3, cmap="viridis_r")
fig.colorbar(points, ax=ax, label="depth (m)")
ax.set_xlabel("absolute salinity (g/kg)")
ax.set_ylabel("conservative temperature (°C)")
ax.set_title("T-S, contours: potential density anomaly σ0 (kg/m³)")
fig.tight_layout()
fig.savefig(name + "_ts.png", dpi=150)
df.to_csv(name + ".csv", index=False)
