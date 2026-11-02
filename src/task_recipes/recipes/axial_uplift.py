# pip install erddapy pandas matplotlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from erddapy import ERDDAP

CENTER = "ooi-rs03ccal-mj03f-05-botpta301"          # Central Caldera bottom pressure (MJ03F), the caldera center
RIM = "ooi-rs03ecal-mj03e-06-botpta302"             # Eastern Caldera bottom pressure (MJ03E), on the eastern rim
START, END = "2024-10-01T00:00:00Z", "2025-10-01T00:00:00Z"   # the span, UTC
RATE_MONTHS = [1, 3, 6]                             # fit the uplift rate over the last 1, 3 and 6 months


def daily_depth(dataset):
    """OOI's daily mean seafloor depth (botsflu_daydepth, m, negative below sea level), computed from the bottom
    pressure with the predicted tide removed: one row a day, without the days its QARTOD flag fails."""
    e = ERDDAP(server="https://erddap.dataexplorer.oceanobservatories.org/erddap", protocol="tabledap", response="csv")
    e.dataset_id = dataset
    e.variables = ["time", "botsflu_daydepth", "botsflu_daydepth_qc_agg"]
    e.constraints = {"time>=": START, "time<=": END}
    # Only the rows that hold a daily depth (one a day of the 1,440): ERDDAP wants NaN unquoted, which erddapy quotes.
    df = pd.read_csv(e.get_download_url() + "&botsflu_daydepth!=NaN", skiprows=[1], index_col="time", parse_dates=True)
    df = df[~df["botsflu_daydepth_qc_agg"].isin([4, 9])]   # 4 FAIL, 9 MISSING
    return df["botsflu_daydepth"].groupby(df.index.floor("D")).mean()


center, rim = daily_depth(CENTER), daily_depth(RIM)
both = pd.concat({"center": center, "rim": rim}, axis=1, sort=True).dropna()
if len(both) < 2:
    raise SystemExit(f"fewer than two days with both stations between {START} and {END}")
# Uplift: the seafloor rising makes its depth (negative) less negative. Each station from its first day, in cm.
uplift = (both - both.iloc[0]) * 100
# Differential uplift: the center relative to the rim, which removes the tidal residuals and oceanographic
# pressure changes the two stations share, leaving the volcano's inflation (as OSU's Axial forecasts use it).
uplift["differential"] = uplift["center"] - uplift["rim"]
# A day when one station's mean is far off (a spike of tens of cm) is left out: more than 6 robust standard deviations
# (1.4826 x the median absolute deviation) from the differential's 15-day running median.
off = uplift["differential"] - uplift["differential"].rolling(15, center=True, min_periods=5).median()
spike = off.abs() > 6 * 1.4826 * off.abs().median()
print(f"left out {int(spike.sum())} day(s) with a spike: {[d.date().isoformat() for d in uplift.index[spike]]}")
uplift = uplift[~spike]


def rate(series, months):
    """The least-squares rate over the last `months` months, in cm a year."""
    last = series[series.index >= series.index[-1] - pd.DateOffset(months=months)]
    if len(last) < 7:
        return np.nan
    days = (last.index - last.index[0]).days.to_numpy()
    return np.polyfit(days, last.to_numpy(), 1)[0] * 365.25


rates = pd.DataFrame({m: {k: rate(uplift[k], m) for k in ("center", "rim", "differential")} for m in RATE_MONTHS})
rates.columns = [f"last {m} months (cm/yr)" for m in RATE_MONTHS]
print(rates.round(1).to_string())

name = f"axial_uplift_{START[:10]}_{END[:10]}"
uplift.round(2).to_csv(name + ".csv", index_label="date")
fig, (a, b) = plt.subplots(2, 1, sharex=True, figsize=(10, 7))
a.plot(uplift.index, uplift["center"], ".", ms=3, label=f"caldera center (MJ03F): {rates.iloc[0, -1]:.1f} cm/yr")
a.plot(uplift.index, uplift["rim"], ".", ms=3, label=f"eastern rim (MJ03E): {rates.iloc[1, -1]:.1f} cm/yr")
a.set_ylabel("uplift since start (cm)")
a.legend(title=f"each station, de-tided; rate over the last {RATE_MONTHS[-1]} months")
b.plot(uplift.index, uplift["differential"], ".", ms=3, color="tab:red")
for m, r in zip(RATE_MONTHS, rates.loc["differential"]):
    last = uplift["differential"][uplift.index >= uplift.index[-1] - pd.DateOffset(months=m)]
    days = (last.index - last.index[0]).days.to_numpy()
    if len(last) >= 7:
        b.plot(last.index, np.polyval(np.polyfit(days, last.to_numpy(), 1), days), lw=2, label=f"last {m} months: {r:.1f} cm/yr")
b.set_ylabel("center minus rim (cm)")
b.legend(title="differential uplift")
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
