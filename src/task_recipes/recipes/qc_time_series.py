# pip install erddapy pandas matplotlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from erddapy import ERDDAP

DATASET = "ooi-rs03ashs-mj03b-10-ctdpfb304"         # any OOI ERDDAP dataset (its download recipe gives the ID)
VARIABLE = "sea_water_temperature"                  # one of its variables with a QARTOD flag (VARIABLE_qc_agg)
START, END = "2025-01-01T00:00:00Z", "2025-07-01T00:00:00Z"   # the span, UTC
DROP = [4, 9]                                       # QARTOD flags to drop: 4 FAIL, 9 MISSING; add 3 to drop SUSPECT
AVERAGE = "1D"                                      # the averaging period: "1D" daily, "1h" hourly, "7D" weekly

FLAGS = {1: "pass", 2: "not evaluated", 3: "suspect", 4: "fail", 9: "missing"}
e = ERDDAP(server="https://erddap.dataexplorer.oceanobservatories.org/erddap", protocol="tabledap", response="csv")
e.dataset_id = DATASET
e.variables = ["time", VARIABLE, f"{VARIABLE}_qc_agg"]
parts = []
for month in pd.date_range(pd.Timestamp(START).normalize(), pd.Timestamp(END), freq="MS", inclusive="both").union([pd.Timestamp(START)]):
    # A month at a time: a dataset of a row a minute is ~44,000 rows a month, and one request of many months can time out.
    a, b = max(month, pd.Timestamp(START)), min(month + pd.offsets.MonthBegin(1), pd.Timestamp(END))
    if a >= b:
        continue
    e.constraints = {"time>=": a.strftime("%Y-%m-%dT%H:%M:%SZ"), "time<": b.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        parts.append(pd.read_csv(e.get_download_url(), skiprows=[1], index_col="time", parse_dates=True))
    except Exception as error:   # ERDDAP answers 404 for a month with no data
        print(f"{a:%Y-%m}: no data ({type(error).__name__})")
if not parts:
    raise SystemExit(f"no {VARIABLE} in {DATASET} between {START} and {END}")
df = pd.concat(parts).sort_index()
df = df[~df.index.duplicated()]
flag = df[f"{VARIABLE}_qc_agg"]
print("QARTOD flags:", {FLAGS.get(int(k), k): int(n) for k, n in flag.value_counts().sort_index().items()})
good = df[VARIABLE].where(~flag.isin(DROP))
mean = good.resample(AVERAGE).agg(["mean", "std", "count"])

name = f"{DATASET}_{VARIABLE}_{START[:10]}_{END[:10]}"
mean.to_csv(name + f"_{AVERAGE}_mean.csv", index_label="time_utc")
fig, ax = plt.subplots(figsize=(11, 4.5))
ax.plot(good.index, good, ",", color="0.6", label="samples kept")
bad = df[VARIABLE].where(flag.isin(DROP))
ax.plot(bad.index, bad, "x", color="tab:red", ms=3, label=f"dropped (flags {', '.join(FLAGS[f] for f in DROP)})")
ax.fill_between(mean.index, mean["mean"] - mean["std"], mean["mean"] + mean["std"], color="tab:blue", alpha=0.2, step="post")
ax.step(mean.index, mean["mean"], where="post", color="tab:blue", label=f"{AVERAGE} mean ± std")
ax.set_ylim(good.quantile(0.001) - good.std(), good.quantile(0.999) + good.std())   # dropped outliers do not set the scale
ax.set_ylabel(VARIABLE)
ax.set_title(DATASET)
ax.legend(loc="best", fontsize=8)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
