# pip install obspy matplotlib
import matplotlib
matplotlib.use("Agg")
import numpy as np
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.signal import PPSD

NETWORK, STATION = "OO", "AXCC1"                    # the station
CHANNEL = None                                      # None: its fastest vertical seismometer channel (HHZ or EHZ); or "BHZ", "HDH"
START = UTCDateTime("2025-10-15")                   # the first day, UTC
DAYS = 1                                            # how many days, one request each
PPSD_LENGTH = 3600                                  # seconds of data in each PSD (ObsPy's default; they overlap by half)

client = Client("https://service.earthscope.org")
end = START + DAYS * 86400
if CHANNEL is None:   # vertical seismometer channels (instrument code H) at the highest sampling rate the station has then
    found = client.get_stations(network=NETWORK, station=STATION, channel="?HZ", starttime=START, endtime=end, level="channel")
    CHANNEL = max(found[0][0], key=lambda c: c.sample_rate).code
inv = client.get_stations(network=NETWORK, station=STATION, channel=CHANNEL, starttime=START, endtime=end, level="response")

ppsd = None
for day in range(DAYS):   # a day at a time: a day of 200 Hz data is ~70 MB in memory
    t = START + day * 86400
    try:
        st = client.get_waveforms(NETWORK, STATION, "*", CHANNEL, t, t + 86400)
    except Exception as error:   # FDSNNoDataException: no data that day
        print(f"{t.date}: no data ({type(error).__name__})")
        continue
    for tr in st:   # records can give the rate a few ppm off (200.00006 Hz), and PPSD skips a trace whose rate differs
        tr.stats.sampling_rate = round(tr.stats.sampling_rate, 3)
    if ppsd is None:   # PPSD removes the instrument response itself, from the station metadata
        # skip_on_gaps: a PSD is computed only where the data have no gap, not with the gap filled by zeros
        # A hydrophone (instrument code D, as HDH) records pressure: its PSD is in dB relative to 1 Pa^2/Hz.
        ppsd = PPSD(st[0].stats, metadata=inv, ppsd_length=PPSD_LENGTH, skip_on_gaps=True,
                    special_handling="hydrophone" if CHANNEL[1] == "D" else None)
    ppsd.add(st)
if ppsd is None:
    raise SystemExit(f"no {CHANNEL} data at {NETWORK}.{STATION} from {START.date} for {DAYS} days")

name = f"{NETWORK}.{STATION}.{CHANNEL}_{START.strftime('%Y%m%d')}_{DAYS}d"
nyquist = ppsd.sampling_rate / 2
# The probability of each power at each frequency, with its median and Peterson's (1993) low and high noise models.
ppsd.plot(name + "_ppsd.png", show_percentiles=True, percentiles=[50], show_noise_models=CHANNEL[1] != "D", xaxis_frequency=True,
          period_lim=(1 / PPSD_LENGTH * 10, nyquist), show=False)
# How the power changed over the period: one column per PSD.
ppsd.plot_spectrogram(filename=name + "_spectrogram.png", show=False)
# The median PSD as a table: frequency (Hz) and power (dB relative to 1 (m/s^2)^2/Hz, ground acceleration, or 1 Pa^2/Hz).
periods, median = ppsd.get_percentile(percentile=50)
unit = "pa2_hz" if CHANNEL[1] == "D" else "m2_s4_hz"
np.savetxt(name + "_median.csv", np.column_stack([1 / periods[::-1], median[::-1]]), delimiter=",",
           header=f"frequency_hz,power_db_rel_1_{unit}", comments="", fmt="%.6g")
ppsd.save_npz(name + ".npz")   # PPSD.load_npz(...) reads it back, to add more days later
