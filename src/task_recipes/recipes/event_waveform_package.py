# pip install obspy matplotlib pandas requests
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from obspy import UTCDateTime, Stream
from obspy.clients.fdsn import Client
from obspy.clients.fdsn.header import FDSNNoDataException
from obspy.core.util import AttribDict
from obspy.geodetics import gps2dist_azimuth, kilometers2degrees
from obspy.taup import TauPyModel

# The events: from a catalogue (EVENTS = None), or your own list of origin times, with their location when known
# (dicts with time, and latitude, longitude, depth_km and magnitude if you have them).
EVENTS = None
CATALOG = "usgs"         # "usgs" (ComCat, the world) or "axial" (the Axial Seamount Earthquake Catalog)
QUERY = dict(starttime="2025-07-29", endtime="2025-07-30", minmagnitude=8)   # the catalogue search
REGION = None            # None: anywhere; or (latitude, longitude, radius in degrees): (43.9, -128.6, 2.0) is the
                         # Blanco fracture zone, (45.95, -130.0, 0.1) Axial's caldera, (40.4, -126.5, 3.0) Mendocino
MAX_EVENTS = 5           # the largest this many
NETWORK = "OO"
STATIONS = "AXBA1,AXCC1,AXEC2,HYS14,HYSB1"   # the OO seismic stations
CHANNELS = None          # None: at each station, its slowest seismometer channels sampled at MIN_RATE or more
MIN_RATE = 20            # Hz: 20 takes BH or SH (40 Hz) for distant events; 100 takes HH or EH (200 Hz) for local ones
BEFORE, AFTER = 120, 1200   # seconds before and after the predicted P arrival (the origin time when no location)
OUTPUT = "VEL"           # ground velocity (m/s); "DISP" (m) or "ACC" (m/s²)
FREQMIN, FREQMAX = 0.02, 1.0   # Hz: band for the record section (the saved traces are not filtered)
PAD = 300                # extra seconds each side for the response removal, cut off afterwards
OUT = Path("events")

client = Client("https://service.earthscope.org")
model = TauPyModel("iasp91")

# 1. The events, each with its origin and, when known, its location.
if EVENTS is None and CATALOG == "usgs":
    where = dict(zip(("latitude", "longitude", "maxradius"), REGION)) if REGION else {}
    cat = Client("USGS").get_events(**{k: UTCDateTime(v) if "time" in k else v for k, v in QUERY.items()}, **where,
                                    orderby="magnitude", limit=MAX_EVENTS)
    EVENTS = [{"time": str(o.time), "latitude": o.latitude, "longitude": o.longitude, "depth_km": (o.depth or 0) / 1000,
               "magnitude": e.preferred_magnitude().mag if e.preferred_magnitude() else None,
               "name": e.event_descriptions[0].text if e.event_descriptions else ""}
              for e in cat for o in [e.preferred_origin() or e.origins[0]]]
elif EVENTS is None:   # the Axial catalogue: a hypo71 file a day (latitude and longitude in degrees and minutes, west)
    EVENTS, day = [], UTCDateTime(UTCDateTime(QUERY["starttime"]).date)
    while day < UTCDateTime(QUERY["endtime"]):
        text = requests.get(f"http://axial.ocean.washington.edu/hypo71/hypo71_{day.strftime('%Y%m%d')}.dat", timeout=60).text
        for p in (line.split() for line in text.splitlines()):
            if len(p) >= 18 and p[0] == day.strftime("%Y%m%d") and float(p[8]) >= QUERY.get("minmagnitude", -9):
                t = UTCDateTime(f"{p[0]}T{p[1].zfill(4)}") + float(p[2])
                if UTCDateTime(QUERY["starttime"]) <= t < UTCDateTime(QUERY["endtime"]):
                    EVENTS.append({"time": str(t), "latitude": float(p[3]) + float(p[4]) / 60,
                                   "longitude": -(float(p[5]) + float(p[6]) / 60), "depth_km": float(p[7]),
                                   "magnitude": float(p[8]), "name": f"Axial catalog {p[15]}"})
        day += 86400
    EVENTS = sorted(EVENTS, key=lambda ev: -ev["magnitude"])[:MAX_EVENTS]
if not EVENTS:
    raise SystemExit("no events: widen QUERY or lower its minmagnitude")
EVENTS = sorted(EVENTS, key=lambda ev: str(ev["time"]))[:MAX_EVENTS]

# 2. The stations and their responses for the events' span.
first, last = UTCDateTime(EVENTS[0]["time"]), UTCDateTime(EVENTS[-1]["time"])
inv = client.get_stations(network=NETWORK, station=STATIONS, channel=CHANNELS or "?H?", level="response",
                          starttime=first - 86400, endtime=last + 86400)


def channels_at(sta, t):
    """The seismometer channels (instrument code H) the station had at time t, at the chosen rate."""
    live = [c for c in sta.select(time=t) if CHANNELS or c.sample_rate >= MIN_RATE]
    if not live:
        return None
    rate = max(c.sample_rate for c in live) if CHANNELS else min(c.sample_rate for c in live)
    return sorted({c.code[:2] for c in live if c.sample_rate == rate})[0] + "?"


def pre_filt(tr):
    """The band where the instrument records ground motion (its response within 3 dB of flat), no lower than the
    record can resolve and no higher than 0.9 of Nyquist; remove_response tapers the spectrum off outside it."""
    nyq = tr.stats.sampling_rate / 2
    f = np.logspace(-4, np.log10(nyq), 500)
    amp = np.abs(inv.get_response(tr.id, tr.stats.starttime).get_evalresp_response_for_frequencies(f, output="DEF"))
    flat = f[amp >= amp.max() / np.sqrt(2)]
    low, high = max(flat[0], 2 / (tr.stats.endtime - tr.stats.starttime)), min(flat[-1], 0.9 * nyq)
    return (float(low / 2), float(low), float(0.8 * high), float(high))


rows = []
for ev in EVENTS:
    origin = UTCDateTime(ev["time"])
    located = ev.get("latitude") is not None and ev.get("longitude") is not None
    folder = OUT / origin.strftime("%Y%m%dT%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    section = []
    for net in inv:
        for sta in net:
            row = {"event": str(origin)[:22], "magnitude": ev.get("magnitude"), "station": sta.code}
            # 3. Where the station is from the event, and when P arrives there (iasp91).
            if located:
                dist_m, az, baz = gps2dist_azimuth(ev["latitude"], ev["longitude"], sta.latitude, sta.longitude)
                gcarc = kilometers2degrees(dist_m / 1000)
                arrivals = model.get_travel_times(source_depth_in_km=max(ev.get("depth_km") or 0, 0),
                                                  distance_in_degree=gcarc, phase_list=["P", "p", "Pdiff", "PKP"])
                ref = origin + (arrivals[0].time if arrivals else 0)
                row.update(distance_deg=round(gcarc, 3), azimuth=round(az, 1), back_azimuth=round(baz, 1),
                           p_arrival=str(ref)[:22] if arrivals else "")
            else:
                ref, baz, gcarc = origin, None, None
            cha = channels_at(sta, ref)
            if cha is None:
                rows.append({**row, "status": "no channel at this time"})
                continue
            # 4. Download with a margin, merge, remove the response, rotate, cut to the window.
            t1, t2 = ref - BEFORE, ref + AFTER
            try:
                st = client.get_waveforms(net.code, sta.code, "*", cha, t1 - PAD, t2 + PAD)
            except FDSNNoDataException:
                rows.append({**row, "channels": cha, "status": "no data"})
                continue
            for tr in st:   # records can give the rate a few ppm off (200.00006 Hz), which stops merging
                tr.stats.sampling_rate = round(tr.stats.sampling_rate, 3)
            gaps = len(st.get_gaps())
            st.merge(method=1, fill_value="interpolate")
            for tr in st:
                tr.detrend("linear")
                tr.taper(0.05)
                tr.remove_response(inventory=inv, output=OUTPUT, pre_filt=pre_filt(tr), water_level=None,
                                   zero_mean=False, taper=False)
            if len(st) == 3:   # true north and east from the azimuths in the metadata, then radial and transverse
                st.rotate("->ZNE", inventory=inv, components=("ZNE", "Z12", "123"))
                if baz is not None:
                    st.rotate("NE->RT", back_azimuth=baz)
            z = st.select(component="Z").copy()   # the record section's, filtered before cutting so its edges are clean
            for tr in z:
                tr.filter("bandpass", freqmin=FREQMIN, freqmax=min(FREQMAX, 0.45 * tr.stats.sampling_rate), zerophase=True)
            z.trim(t1, t2)
            st.trim(t1, t2)
            if not st or min(tr.stats.npts for tr in st) < 0.9 * (t2 - t1) * st[0].stats.sampling_rate:
                rows.append({**row, "channels": cha, "status": f"incomplete ({gaps} gaps)"})
                continue
            # 5. Save MiniSEED, StationXML, and SAC with the event and station in its header.
            name = f"{net.code}.{sta.code}.{origin.strftime('%Y%m%dT%H%M%S')}"
            st.write(str(folder / f"{name}.mseed"), format="MSEED", encoding="FLOAT64")
            inv.select(station=sta.code, channel=cha, time=ref).write(str(folder / f"{name}.xml"), format="STATIONXML")
            for tr in st:
                tr.stats.sac = AttribDict({"stla": sta.latitude, "stlo": sta.longitude, "stel": sta.elevation,
                                           "o": origin - tr.stats.starttime, "kevnm": origin.strftime("%y%m%d%H%M")})
                if located:
                    tr.stats.sac.update({"evla": ev["latitude"], "evlo": ev["longitude"], "evdp": ev.get("depth_km") or 0,
                                         "mag": ev.get("magnitude") or -12345.0, "gcarc": gcarc, "az": az, "baz": baz,
                                         "dist": dist_m / 1000, "a": ref - tr.stats.starttime, "ka": "P"})
                tr.write(str(folder / f"{tr.id}.{origin.strftime('%Y%m%dT%H%M%S')}.sac"), format="SAC")
            rows.append({**row, "channels": cha, "rate_hz": st[0].stats.sampling_rate, "gaps_filled": gaps,
                         "status": "ok", "components": "".join(tr.stats.channel[-1] for tr in st)})
            if z:
                section.append((gcarc if gcarc is not None else len(section), sta.code, z[0]))

    # 6. Record section: the vertical components in FREQMIN-FREQMAX, each scaled to its peak, by distance.
    if section:
        fig, ax = plt.subplots(figsize=(10, 1.0 + 0.8 * len(section)))
        section.sort(key=lambda s: s[0])
        for i, (d, code, tr) in enumerate(section):
            ax.plot(tr.times() - BEFORE, i + 0.45 * tr.data / np.abs(tr.data).max(), "k", lw=0.5)
            ax.text(-BEFORE, i + 0.25, f"{code} {d:.2f}°" if located else code, fontsize=8)
        ax.axvline(0, color="r", lw=0.8)
        ax.set_yticks([])
        ax.set_xlabel("seconds after predicted P (iasp91)" if located else "seconds after origin")
        title = f"{str(origin)[:19]} M{ev.get('magnitude') or '?'} {ev.get('name', '')}, Z {FREQMIN:g}-{FREQMAX:g} Hz"
        ax.set_title(title.strip())
        fig.tight_layout()
        fig.savefig(folder / "record_section.png", dpi=150)
        plt.close(fig)

table = pd.DataFrame(rows)
print(table.to_string(index=False))
table.to_csv("events_stations.csv", index=False)   # what was saved for each event and station, and why not
