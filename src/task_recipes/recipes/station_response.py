# pip install obspy pandas matplotlib
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

NETWORK = "OO"
STATIONS = "AXCC1"      # one or more stations ("AXCC1,AXAS1") or wildcards ("AX*")
CHANNELS = "*"          # every channel; or "HH?", "EH?,HDH", "BDO" ...
LOCATION = "*"          # "" for the seismometers and hydrophone, "11" for the BOTPT channels
TIME = None             # None: every epoch since installation; or a time ("2025-10-15") for the metadata then

# SEED channel codes: band (sampling rate and kind of sensor), instrument, orientation.
BAND = {"H": "200 Hz-class (80-250 Hz), broadband", "E": "200 Hz-class (80-250 Hz), short-period",
        "B": "40 Hz-class (10-80 Hz), broadband", "S": "40 Hz-class (10-80 Hz), short-period",
        "M": "mid-rate (1-10 Hz)", "L": "about 1 Hz", "V": "about 0.1 Hz", "U": "about 0.01 Hz"}
INSTRUMENT = {"H": "high-gain seismometer", "N": "accelerometer", "D": "pressure (hydrophone or bottom pressure)",
              "K": "temperature", "A": "tilt", "L": "low-gain seismometer"}

# Tilt, temperature and pressure units (microradian, C, psia) are not ObsPy's seismic units; their responses are
# used as they are, which is right for them, so ObsPy's warning about it is not shown.
warnings.filterwarnings("ignore", message="The unit '")
client = Client("https://service.earthscope.org")
when = dict(starttime=UTCDateTime(TIME), endtime=UTCDateTime(TIME) + 1) if TIME else {}
inv = client.get_stations(network=NETWORK, station=STATIONS, location=LOCATION, channel=CHANNELS, level="response", **when)


def flat_band(resp, rate):
    """Where the response is within 3 dB of its largest value: the band the channel records faithfully."""
    f = np.logspace(-4, np.log10(rate / 2), 600)
    amp = np.abs(resp.get_evalresp_response_for_frequencies(f, output="DEF"))
    flat = f[amp >= amp.max() / np.sqrt(2)]
    return (float(flat[0]), float(flat[-1])) if len(flat) else (np.nan, np.nan)


rows, latest = [], {}
for net in inv:
    for sta in net:
        for cha in sta:
            r, sens = cha.response, cha.response.instrument_sensitivity if cha.response else None
            stages = r.response_stages if r else []
            low, high = flat_band(r, cha.sample_rate) if r and sens else (np.nan, np.nan)
            rows.append({
                "station": sta.code, "location": cha.location_code or "--", "channel": cha.code,
                "epoch_start": str(cha.start_date)[:19], "epoch_end": str(cha.end_date)[:19] if cha.end_date else "open",
                "rate_hz": cha.sample_rate,
                "band": BAND.get(cha.code[0], cha.code[0]), "instrument": INSTRUMENT.get(cha.code[1], cha.code[1]),
                "azimuth_deg": cha.azimuth, "dip_deg": cha.dip, "latitude": cha.latitude, "longitude": cha.longitude,
                "elevation_m": cha.elevation, "sensor": cha.sensor.description if cha.sensor else "",
                "datalogger": cha.data_logger.description if cha.data_logger else "",
                "sensitivity": sens.value if sens else np.nan, "sensitivity_hz": sens.frequency if sens else np.nan,
                "input_units": sens.input_units if sens else "", "output_units": sens.output_units if sens else "",
                "units_per_count": 1 / sens.value if sens and sens.value else np.nan,
                "flat_low_hz": low, "flat_high_hz": high, "n_stages": len(stages),
                "stages": "; ".join(f"{s.stage_sequence_number} {type(s).__name__.replace('ResponseStage', '') or 'Gain'}"
                                    f" {s.stage_gain:.4g}" for s in stages)})
            key = (sta.code, cha.location_code, cha.code[:2])   # one curve per sensor and rate: Z, N and E share it
            if r and sens and (key not in latest or cha.start_date > latest[key][0].start_date):
                latest[key] = (cha, r)

table = pd.DataFrame(rows).sort_values(["station", "location", "channel", "epoch_start"])
name = f"{NETWORK}_{STATIONS}_{CHANNELS}_metadata".replace("*", "x").replace(",", "-").replace("?", "x")
table.to_csv(name + ".csv", index=False)
show = ["station", "location", "channel", "epoch_start", "epoch_end", "rate_hz", "azimuth_deg", "dip_deg", "sensitivity",
        "input_units", "flat_low_hz", "flat_high_hz", "n_stages"]
print(table[show].to_string(index=False))
print(f"\n{len(table)} channel epochs; a new epoch starts when an instrument is swapped or its metadata corrected.")
# Two horizontals of one sensor should be 90 degrees apart; metadata that says otherwise rotates them wrongly.
for (code, loc, start, band), g in table[table["dip_deg"] == 0].groupby(
        ["station", "location", "epoch_start", table["channel"].str[:2]]):
    az = g.set_index(g["channel"].str[2])["azimuth_deg"]
    pair = ("N", "E") if {"N", "E"} <= set(az.index) else ("1", "2") if {"1", "2"} <= set(az.index) else None
    if pair and abs(((az[pair[1]] - az[pair[0]]) % 360) - 90) > 1:
        print(f"CHECK {code}.{loc}.{band}{pair[0]}/{band}{pair[1]} from {start}: azimuths {az[pair[0]]:g} and "
              f"{az[pair[1]]:g} are not 90 degrees apart, so one is wrong; do not rotate with them")
print("Counts to physical units: divide by the sensitivity (counts per input unit), which is exact only at "
      "sensitivity_hz and holds within 3 dB between flat_low_hz and flat_high_hz; outside that band remove the full "
      "response (ObsPy's remove_response with a pre-filter). Azimuth is the horizontal's direction clockwise from "
      "north; dip -90 is up for a vertical seismometer.")

# Each channel's latest response: amplitude relative to its sensitivity, and phase, against frequency.
if latest:
    fig, (a, p) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for (code, loc, chan), (cha, r) in sorted(latest.items()):
        f = np.logspace(-4, np.log10(cha.sample_rate / 2), 600)
        h = r.get_evalresp_response_for_frequencies(f, output="DEF")
        label = f"{code}.{loc or '--'}.{cha.code} ({r.instrument_sensitivity.input_units})"
        a.loglog(f, np.abs(h) / r.instrument_sensitivity.value, lw=0.9, label=label)
        p.semilogx(f, np.degrees(np.unwrap(np.angle(h))), lw=0.9)
    a.axhline(1 / np.sqrt(2), color="0.6", ls=":", lw=0.8)
    a.set_ylim(1e-3, 3)
    a.set_ylabel("amplitude / sensitivity")
    a.legend(fontsize=7, ncol=2)
    p.set_ylabel("phase (degrees)")
    p.set_xlabel("frequency (Hz)")
    a.set_title(f"{NETWORK} {STATIONS} {CHANNELS}: instrument responses, one channel of each kind (latest epoch), dotted line -3 dB", fontsize=10)
    fig.tight_layout()
    fig.savefig(name + ".png", dpi=150)
