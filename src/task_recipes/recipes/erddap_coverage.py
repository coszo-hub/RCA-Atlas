# pip install pandas matplotlib requests
import io
import numpy as np
import pandas as pd
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ERDDAP = "https://erddap.dataexplorer.oceanobservatories.org/erddap"
REFDES = "RS03CCAL-MJ03F-05-BOTPTA301"    # the instrument's reference designator (its dataset is "ooi-" + refdes)
VARIABLES = None                          # None: every data variable; or ["botpres", "botsflu_meandepth"]
START, END = "2014-08-01", None           # days, UTC; END is not included; None: up to today
MIN_GAP_DAYS = 7                          # list runs of days without data at least this long

dataset = "ooi-" + REFDES.lower()
info = pd.read_csv(f"{ERDDAP}/info/{dataset}/index.csv")
attrs = info[info["Row Type"] == "attribute"]
units = attrs[attrs["Attribute Name"] == "units"].set_index("Variable Name")["Value"]
names = info.loc[info["Row Type"] == "variable", "Variable Name"].tolist()
if VARIABLES is None:   # the measurements, not coordinates, QC flags or test records
    VARIABLES = [v for v in names if v not in ("time", "latitude", "longitude", "z", "station", "deployment")
                 and not v.endswith(("_qc_agg", "_qc_tests", "_qc_executed", "_qc_results", "_profiler_depth_enabled"))]
stop = pd.Timestamp(END) if END else pd.Timestamp.now("UTC").tz_localize(None).normalize() + pd.Timedelta(days=1)

# One request: for each day, how many values of each variable are not missing (ERDDAP's orderByCount), a year at a
# time so a large dataset does not time out.
edges = pd.date_range(START, stop, freq="YS").union([pd.Timestamp(START), stop])
parts = []
for a, b in zip(edges[:-1], edges[1:]):
    query = (f"time,{','.join(VARIABLES)}&time>={a:%Y-%m-%d}T00:00:00Z&time<{b:%Y-%m-%d}T00:00:00Z"
             '&orderByCount("time/1day")')
    r = requests.get(f"{ERDDAP}/tabledap/{dataset}.csv?{query}", timeout=900)
    if r.status_code == 404:   # no rows in this year
        continue
    r.raise_for_status()
    parts.append(pd.read_csv(io.StringIO(r.text), skiprows=[1], parse_dates=["time"]))
if not parts:
    raise SystemExit(f"{dataset} has no data from {START} to {stop:%Y-%m-%d}")
counts = pd.concat(parts).drop_duplicates("time").set_index("time").sort_index()
counts.index = counts.index.tz_localize(None).normalize()
days = pd.date_range(START, stop, freq="D", inclusive="left")
counts = counts.reindex(days, fill_value=0).astype(int)

# A full day's count is the variable's usual daily count (1440 for 1-minute data, 1 for a daily product).
summary, gaps = [], []
for v in VARIABLES:
    c = counts[v]
    full = int(c[c > 0].median()) if (c > 0).any() else 0
    has = c > 0
    run_id = (has != has.shift()).cumsum()
    for _, run in c[~has].groupby(run_id[~has]):
        if len(run) >= MIN_GAP_DAYS:
            gaps.append({"variable": v, "first_day": str(run.index[0].date()), "last_day": str(run.index[-1].date()),
                         "days": len(run)})
    summary.append({"variable": v, "units": units.get(v, ""), "values_per_full_day": full,
                    "days_with_data": int(has.sum()), "percent_of_days": round(100 * has.mean(), 1),
                    "first_day": str(c[has].index.min().date()) if has.any() else "",
                    "last_day": str(c[has].index.max().date()) if has.any() else "",
                    f"gaps_of_{MIN_GAP_DAYS}d_or_more": sum(g["variable"] == v for g in gaps)})
summary = pd.DataFrame(summary)
gaps = pd.DataFrame(gaps, columns=["variable", "first_day", "last_day", "days"])
print(summary.to_string(index=False))
print(gaps.to_string(index=False))
name = f"{REFDES}_coverage"
summary.to_csv(name + "_summary.csv", index=False)
gaps.to_csv(name + "_gaps.csv", index=False)
counts.rename_axis("day").to_csv(name + "_daily_counts.csv")

# Percent of a full day, by variable and day (by month for spans over a year and a half).
pct = counts[VARIABLES].div(summary.set_index("variable")["values_per_full_day"].replace(0, np.nan)).clip(upper=1) * 100
grid = (pct if len(days) <= 550 else pct.resample("MS").mean()).T
fig, ax = plt.subplots(figsize=(11, 0.32 * len(grid) + 1.8))
im = ax.imshow(grid.to_numpy(float), aspect="auto", cmap="viridis", vmin=0, vmax=100, interpolation="nearest")
ax.set_yticks(range(len(grid)), grid.index, fontsize=8)
ticks = np.linspace(0, grid.shape[1] - 1, min(10, grid.shape[1])).astype(int)
ax.set_xticks(ticks, [str(grid.columns[i].date()) for i in ticks], rotation=30, ha="right")
fig.colorbar(im, ax=ax, label="% of a full day" if len(days) <= 550 else "monthly mean %")
ax.set_title(f"{REFDES} on OOI's ERDDAP: values present, {START} to {days[-1]:%Y-%m-%d}")
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
