# pip install obspy matplotlib requests
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from obspy import Stream, UTCDateTime
from obspy.clients.fdsn import Client
from obspy.signal.trigger import coincidence_trigger

NETWORK = "OO"
STATIONS = ["AXCC1", "AXEC1", "AXEC2", "AXEC3", "AXAS1", "AXAS2", "AXID1"]   # the stations to trigger on (Axial's caldera)
START = UTCDateTime("2025-10-15T00:00:00")          # the start, UTC
HOURS = 6                                           # how long
FREQMIN, FREQMAX = 35.0, 80.0                       # band, Hz: above fin whale calls (about 18-30 Hz)
STA, LTA = 0.2, 10.0                                # short- and long-term windows, seconds
ON, OFF = 3.0, 1.2                                  # STA/LTA ratio that starts and ends a trigger
MIN_STATIONS = 2                                    # stations that must trigger together for a detection
CATALOG = "http://axial.ocean.washington.edu/hypo71"   # the Axial Seamount Earthquake Catalog, to compare (Axial only)

client = Client("https://service.earthscope.org")
end = START + HOURS * 3600
st = Stream()
for station in STATIONS:   # each station's fastest vertical seismometer channel (HHZ or EHZ)
    try:
        found = client.get_stations(network=NETWORK, station=station, channel="?HZ", starttime=START, endtime=end, level="channel")
        channel = max(found[0][0], key=lambda c: c.sample_rate).code
        part = client.get_waveforms(NETWORK, station, "*", channel, START - 3 * LTA, end)   # a margin for the LTA to settle
    except Exception as error:   # FDSNNoDataException: no data then
        print(f"{station}: no data ({type(error).__name__})")
        continue
    for tr in part:   # records can give the rate a few ppm off (200.00006 Hz), which stops merging
        tr.stats.sampling_rate = round(tr.stats.sampling_rate, 3)
    part.merge(method=1, fill_value=0)   # gaps become zeros, which do not trigger
    st += part
if not st:
    raise SystemExit(f"no data at {STATIONS} from {START} for {HOURS} hours")
st.detrend("demean")
st.taper(max_percentage=None, max_length=5)
for tr in st:   # counts are enough to detect; the band stays below Nyquist
    tr.filter("bandpass", freqmin=FREQMIN, freqmax=min(FREQMAX, 0.45 * tr.stats.sampling_rate), corners=4, zerophase=True)

# Recursive STA/LTA on each trace; a detection is a time when MIN_STATIONS of them are triggered at once.
detections = [d for d in coincidence_trigger("recstalta", ON, OFF, st, MIN_STATIONS, sta=STA, lta=LTA, details=True)
              if d["time"] >= START]

# The catalog's earthquakes in the same hours (hypo71 rows: yyyymmdd HHMM SS.SS ... magnitude ... ID).
events = []
day = UTCDateTime(START.date)
while day < end:
    text = requests.get(f"{CATALOG}/hypo71_{day.strftime('%Y%m%d')}.dat", timeout=60).text
    for p in (line.split() for line in text.splitlines()):
        if len(p) >= 18 and p[0] == day.strftime("%Y%m%d"):
            t = UTCDateTime(f"{p[0]}T{p[1].zfill(4)}") + float(p[2])
            if START <= t < end:
                events.append({"time": t, "magnitude": float(p[8]), "id": p[15]})
    day += 86400
# A detection matches a catalog earthquake that began up to 3 s before it (P waves cross the caldera in a second or two).
for d in detections:
    match = next((e for e in events if 0 <= d["time"] - e["time"] <= 3), None)
    d["catalog_id"], d["magnitude"] = (match["id"], match["magnitude"]) if match else ("", "")
matched = {d["catalog_id"] for d in detections if d["catalog_id"]}
print(f"{len(detections)} detections, {len(events)} catalog earthquakes, {len(matched)} of them detected")

name = f"{NETWORK}_detections_{START.strftime('%Y%m%dT%H%M')}_{HOURS}h"
with open(name + ".csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time_utc", "duration_s", "stations", "coincidence_sum", "catalog_id", "catalog_magnitude"])
    for d in detections:
        w.writerow([d["time"].isoformat(), round(d["duration"], 2), " ".join(sorted({s.split(".")[1] for s in d["trace_ids"]})),
                    d["coincidence_sum"], d["catalog_id"], d["magnitude"]])

fig, (a, b) = plt.subplots(2, 1, figsize=(11, 6), gridspec_kw={"height_ratios": [2, 1]})
tr = st[0].slice(START, end)
a.plot(tr.times("matplotlib"), tr.data, "k", lw=0.3)
for d in detections:
    a.axvline(d["time"].matplotlib_date, color="tab:green" if d["catalog_id"] else "tab:red", lw=0.6, alpha=0.7)
a.set_title(f"{tr.id} {FREQMIN:g}-{FREQMAX:g} Hz; detections in the catalog (green) and not (red)")
a.xaxis_date()
hours = [START + 3600 * h for h in range(HOURS + 1)]
count = lambda times: [sum(h0 <= t < h1 for t in times) for h0, h1 in zip(hours, hours[1:])]
x = [h.matplotlib_date for h in hours[:-1]]
b.bar(x, count([d["time"] for d in detections]), width=0.8 / 24, align="edge", alpha=0.6, label="detections")
b.bar(x, count([e["time"] for e in events]), width=1 / 24, align="edge", fill=False, edgecolor="k", label="catalog earthquakes")
b.xaxis_date()
b.set_ylabel("per hour")
b.legend()
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
