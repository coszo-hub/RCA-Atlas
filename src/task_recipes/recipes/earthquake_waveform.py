# pip install obspy matplotlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

NETWORK, STATION = "OO", "AXCC1"                    # the station
CHANNELS = None                                     # None: its fastest seismometer channels (HH? or EH?); or "BH?"
ORIGIN = UTCDateTime("2025-10-15T04:43:15.86")      # the earthquake's origin time, UTC
BEFORE, AFTER = 5, 25                               # seconds to plot before and after it
OUTPUT = "VEL"                                      # ground velocity (m/s); "DISP" (m) or "ACC" (m/s²)
FREQMIN, FREQMAX = 4.0, 50.0                        # display band, Hz
PAD = 60                                            # extra seconds each side, cut off after filtering

client = Client("https://service.earthscope.org")
t1, t2 = ORIGIN - BEFORE, ORIGIN + AFTER
if CHANNELS is None:   # seismometer channels (instrument code H) at the highest sampling rate the station has then
    found = client.get_stations(network=NETWORK, station=STATION, channel="?H?", starttime=t1, endtime=t2, level="channel")
    CHANNELS = max(found[0][0], key=lambda c: c.sample_rate).code[:2] + "?"
st = client.get_waveforms(NETWORK, STATION, "*", CHANNELS, t1 - PAD, t2 + PAD)
inv = client.get_stations(network=NETWORK, station=STATION, channel=CHANNELS, starttime=t1, endtime=t2, level="response")
st.merge(method=1, fill_value="interpolate")   # one trace per channel, short gaps filled


def pre_filt(tr):
    """The band where the instrument records ground motion: from its low corner (where its response falls to 0.7 of
    the flat level) to its high corner or 0.9 of Nyquist, whichever is lower. Below and above it, dividing by a
    tiny response would blow up noise, so remove_response tapers it off there."""
    nyq = tr.stats.sampling_rate / 2
    f = np.logspace(-4, np.log10(nyq), 500)
    amp = np.abs(inv.get_response(tr.id, tr.stats.starttime).get_evalresp_response_for_frequencies(f, output="DEF"))
    flat = f[amp >= amp.max() / np.sqrt(2)]
    low = max(flat[0], 2 / (tr.stats.endtime - tr.stats.starttime))   # no lower than the record can resolve
    high = min(flat[-1], 0.9 * nyq)
    return (float(low / 2), float(low), float(0.8 * high), float(high))


for tr in st:
    tr.detrend("linear")
    tr.taper(0.05)
    tr.remove_response(inventory=inv, output=OUTPUT, pre_filt=pre_filt(tr), water_level=None,
                       zero_mean=False, taper=False)   # pre_filt alone keeps the division stable
# The horizontals' names (N, E) do not say where they point: some OOI seismometers are not aligned with north.
# With all three components, rotate them to true north and east with the azimuths in the station metadata.
if len(st) == 3:
    st.rotate("->ZNE", inventory=inv, components=("ZNE", "Z12", "123"))
for tr in st:
    fmax = min(FREQMAX, 0.45 * tr.stats.sampling_rate)   # the band must stay below Nyquist
    tr.filter("bandpass", freqmin=FREQMIN, freqmax=fmax, corners=4, zerophase=True)
st.trim(t1, t2)

units = {"VEL": "m/s", "DISP": "m", "ACC": "m/s²"}[OUTPUT]
fig, axes = plt.subplots(len(st), 1, sharex=True, figsize=(10, 2.2 * len(st)), squeeze=False)
for ax, tr in zip(axes[:, 0], st):
    ax.plot(tr.times(reftime=ORIGIN), tr.data, "k", lw=0.6)
    ax.set_ylabel(f"{tr.stats.channel}\n{units}")
axes[0, 0].set_title(f"{NETWORK}.{STATION} {ORIGIN.isoformat()[:22]} UTC, {FREQMIN:g}-{FREQMAX:g} Hz")
axes[-1, 0].set_xlabel("seconds after origin")
fig.tight_layout()
name = f"{NETWORK}.{STATION}_{ORIGIN.strftime('%Y%m%dT%H%M%S')}"
fig.savefig(name + ".png", dpi=150)
st.write(name + ".mseed", format="MSEED")   # the corrected, filtered traces
