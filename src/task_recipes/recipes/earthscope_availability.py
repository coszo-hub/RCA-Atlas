# pip install obspy pandas matplotlib
import io
import numpy as np
import pandas as pd
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.clients.fdsn.header import FDSNNoDataException

NETWORK = "OO"
STATIONS = "AX*"                  # stations: "AXCC1,HYS14", or wildcards ("AX*" is Axial's, "HYS*" Hydrate Ridge's)
CHANNELS = "HHZ,EHZ"              # HHZ broadband, EHZ short-period; "HN?" accelerometer, "HDH" hydrophone, "BDO" BOTPT
START, END = "2025-01-01", "2026-01-01"   # days, UTC; END is not included
LIST_GAPS = False                 # True: download the data and list each gap (keep the span to days)
MIN_GAP = 1.0                     # seconds: shorter gaps are not listed
MAX_DOWNLOAD_DAYS = 31            # channel-days the script may download (a day of a 200 Hz channel is about 25 MB)

client = Client("https://service.earthscope.org")
days = pd.date_range(START, END, freq="D", inclusive="left")

# 1. Which channels exist, and when they were installed (each epoch), from the station metadata.
inv = client.get_stations(network=NETWORK, station=STATIONS, channel=CHANNELS,
                          starttime=UTCDateTime(START), endtime=UTCDateTime(END), level="channel")
installed = {}
for net in inv:
    for sta in net:
        for cha in sta:
            cid = f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}"
            on = installed.setdefault(cid, pd.Series(False, index=days))
            end = pd.Timestamp(cha.end_date.datetime) if cha.end_date else days[-1] + pd.Timedelta(days=1)
            on[(days + pd.Timedelta(days=1) > pd.Timestamp(cha.start_date.datetime)) & (days < end)] = True
installed = pd.DataFrame(installed).sort_index(axis=1)
if installed.empty:
    raise SystemExit(f"no {CHANNELS} channels at {NETWORK}.{STATIONS} between {START} and {END}")

# 2. Daily percent of each day with data, from EarthScope's MUSTANG quality metrics (seismometer and accelerometer
#    channels only; computed a day or two after the data arrive).
def mustang(metric):
    r = requests.get("https://service.earthscope.org/mustang/measurements/1/query", timeout=600, params={
        "metric": metric, "net": NETWORK, "sta": STATIONS, "cha": CHANNELS, "format": "csv",
        "timewindow": f"{START},{END}"})
    r.raise_for_status()
    m = pd.read_csv(io.StringIO(r.text), skiprows=1)   # the first line is the metric's name
    if m.empty:
        return pd.DataFrame(index=days)
    m["cid"] = m["target"].str.rsplit(".", n=1).str[0]   # OO.AXCC1..HHZ.M -> OO.AXCC1..HHZ
    m["day"] = pd.to_datetime(m["start"].str[:10])
    return m.pivot_table(index="day", columns="cid", values="value").reindex(days)

percent = mustang("percent_availability").reindex(columns=installed.columns)
ngaps = mustang("num_gaps").reindex(columns=installed.columns)
route = {c: "MUSTANG" for c in percent.columns if percent[c].notna().any()}

# 3. Channels MUSTANG has no metrics for (hydrophone, BOTPT), or all of them when gaps are listed: download each
#    day and measure it.
download = [c for c in installed.columns if LIST_GAPS or c not in route]
need = sum(int(installed[c].sum()) for c in download)
if need > MAX_DOWNLOAD_DAYS:
    raise SystemExit(f"{need} channel-days to download ({', '.join(download)}): shorten START-END, narrow "
                     f"STATIONS or CHANNELS, or raise MAX_DOWNLOAD_DAYS")
gaps = []
for cid in download:
    net, sta, loc, cha = cid.split(".")
    for day in days[installed[cid].to_numpy()]:
        t0 = UTCDateTime(day.to_pydatetime())
        try:
            st = client.get_waveforms(net, sta, loc or "--", cha, t0, t0 + 86400)
        except FDSNNoDataException:
            st = []
        for tr in st:   # records can give the rate a few ppm off (200.00006 Hz), which stops merging
            tr.stats.sampling_rate = round(tr.stats.sampling_rate, 3)
        st.trim(t0, t0 + 86400)
        if st:
            found = st.get_gaps(min_gap=MIN_GAP)   # between records, before merging hides them
            st.merge()                             # one trace per channel, gaps masked
            have = sum(np.ma.count(tr.data) / tr.stats.sampling_rate for tr in st)
            for g in found:
                gaps.append({"channel": cid, "gap_start": str(g[4])[:23], "gap_end": str(g[5])[:23],
                             "seconds": round(g[6], 3)})
            for edge, t in (("start", st[0].stats.starttime), ("end", st[-1].stats.endtime)):   # gaps at the day's edges
                lost = t - t0 if edge == "start" else t0 + 86400 - t
                if lost >= MIN_GAP:
                    a, b = (t0, t) if edge == "start" else (t, t0 + 86400)
                    gaps.append({"channel": cid, "gap_start": str(a)[:23], "gap_end": str(b)[:23], "seconds": round(lost, 3)})
        else:
            have = 0.0
            if LIST_GAPS:
                gaps.append({"channel": cid, "gap_start": str(t0)[:23], "gap_end": str(t0 + 86400)[:23], "seconds": 86400.0})
        percent.loc[day, cid] = min(100.0, 100 * have / 86400)
        route.setdefault(cid, "downloaded")

# 4. Each channel-day: not installed, no data, partial, full, or not computed yet (MUSTANG's last day or two).
percent = percent.where(installed)
summary = []
for cid in installed.columns:
    p, on = percent[cid], installed[cid]
    outage = (p == 0).astype(int)
    runs = outage.groupby((outage != outage.shift()).cumsum()).agg(["sum", "size"])
    longest = runs[runs["sum"] > 0]["size"].max() if (outage > 0).any() else 0
    with_data = p[p > 0].index
    summary.append({"channel": cid, "route": route.get(cid, "no metrics"), "installed_days": int(on.sum()),
                    "days_with_data": int((p > 0).sum()), "full_days": int((p >= 99.99).sum()),
                    "no_data_days": int((p == 0).sum()), "not_computed_days": int((on & p.isna()).sum()),
                    "mean_percent": round(float(p.mean()), 2) if p.notna().any() else None,
                    "longest_outage_days": int(longest),
                    "gaps_per_day": round(float(ngaps[cid].mean()), 2) if cid in ngaps and ngaps[cid].notna().any() else None,
                    "first_day_with_data": str(with_data.min().date()) if len(with_data) else "",
                    "last_day_with_data": str(with_data.max().date()) if len(with_data) else ""})
summary = pd.DataFrame(summary)
print(summary.to_string(index=False))
name = f"{NETWORK}_{STATIONS}_{CHANNELS}_{START}_{END}".replace("*", "x").replace(",", "-").replace("?", "x")
summary.to_csv(name + "_summary.csv", index=False)
percent.rename_axis("day").to_csv(name + "_daily_percent.csv", float_format="%.3f")
if LIST_GAPS:
    pd.DataFrame(gaps, columns=["channel", "gap_start", "gap_end", "seconds"]).to_csv(name + "_gaps.csv", index=False)
    print(f"{len(gaps)} gaps of {MIN_GAP:g} s or more")

# 5. Heatmap: channel by day (by month for spans over a year); grey where the channel was not installed.
grid = percent.T if len(days) <= 400 else percent.resample("MS").mean().T
fig, ax = plt.subplots(figsize=(11, 0.35 * len(grid) + 1.6))
cmap = plt.get_cmap("viridis").copy()
cmap.set_bad("0.85")
im = ax.imshow(np.ma.masked_invalid(grid.to_numpy(float)), aspect="auto", cmap=cmap, vmin=0, vmax=100,
               interpolation="nearest")
ax.set_yticks(range(len(grid)), [c.replace(f"{NETWORK}.", "") for c in grid.index])
ticks = np.linspace(0, grid.shape[1] - 1, min(8, grid.shape[1])).astype(int)
ax.set_xticks(ticks, [str(grid.columns[i].date()) for i in ticks], rotation=30, ha="right")
fig.colorbar(im, ax=ax, label="% of the day with data" if len(days) <= 400 else "monthly mean %")
ax.set_title(f"{NETWORK} {STATIONS} {CHANNELS}: data availability, {START} to {END} (grey: not installed or not yet computed)")
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
