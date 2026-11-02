# pip install ooipy==1.3.0 matplotlib
import datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import ooipy
import pandas as pd

# The hydrophone: a broadband one by its node (64 kHz, from the OOI raw-data archive) - LJ03A Axial Base seafloor,
# PC03A Axial Base 200 m platform, LJ01A Oregon Slope Base seafloor, PC01A Slope Base 200 m platform, LJ01C Oregon
# Offshore, LJ01D Oregon Shelf - or a low-frequency one by its seismic station (200 Hz, from EarthScope): AXBA1,
# AXCC1, AXEC2, HYS14 or HYSB1.
HYDROPHONE = "LJ03A"
START = datetime.datetime(2025, 10, 15, 3, 18)      # the start, UTC
MINUTES = 5                                         # how long
AVERAGE = None                                      # seconds in each column; None: 1 (broadband) or 10 (low-frequency)
L = None                                            # samples per FFT; None: 16384 (3.9 Hz bins at 64 kHz) or 512 (0.39 Hz at 200 Hz)
FMIN, FMAX = 5, 32000                               # frequencies to plot, Hz (a low-frequency hydrophone stops at 100)

end = START + datetime.timedelta(minutes=MINUTES)
if HYDROPHONE in ("AXBA1", "AXCC1", "AXEC2", "HYS14", "HYSB1"):   # a station: its low-frequency hydrophone (HDH)
    data = ooipy.get_acoustic_data_LF(START, end, HYDROPHONE)
else:
    data = ooipy.get_acoustic_data(START, end, HYDROPHONE)
    # OOIPy 1.3.0 finds a broadband hydrophone's calibration by its deployment, but fails for the current one (its end
    # time is blank): find the hydrophone (asset ID) deployed then from OOI's deployments list instead.
    deployments = pd.read_csv("https://raw.githubusercontent.com/OOI-CabledArray/deployments/main/HYDBBA_deployments.csv")
    on = deployments[deployments["referenceDesignator"].str.contains(f"-{HYDROPHONE}-")
                     & (pd.to_datetime(deployments["startTime"]) <= pd.Timestamp(START))
                     & (pd.to_datetime(deployments["endTime"]).isna() | (pd.to_datetime(deployments["endTime"]) > pd.Timestamp(START)))]
    asset = on["assetID"].iloc[-1]
    data.get_asset_ID = lambda: asset
if data is None:
    raise SystemExit(f"no data from {HYDROPHONE} between {START} and {end}")

# Each column: Welch's PSD of AVERAGE seconds with the median of its periodograms (not the mean, which the broadband
# hydrophones' ADCP pings would dominate), corrected by the hydrophone's frequency-dependent sensitivity from its
# calibration sheet: dB relative to 1 uPa^2/Hz.
broadband = data.stats.sampling_rate > 1000
L = L or (16384 if broadband else 512)
AVERAGE = AVERAGE or (1.0 if broadband else 10.0)
spec = data.compute_spectrogram(L=L, avg_time=AVERAGE, average_type="median", verbose=False)
fmax = min(FMAX, data.stats.sampling_rate / 2)
band = spec.sel(frequency=slice(FMIN, fmax))

name = f"{HYDROPHONE}_{START:%Y%m%dT%H%M}_{MINUTES}min"
fig, ax = plt.subplots(figsize=(11, 5))
level = band.median("time")   # the colour scale spans every frequency's typical level, low and high alike
mesh = ax.pcolormesh(band["time"].values, band["frequency"].values, band.values.T, shading="nearest", cmap="viridis",
                     vmin=float(level.min()) - 5, vmax=float(level.max()) + 10)
ax.set_yscale("log")
ax.set_ylabel("frequency (Hz)")
ax.set_title(f"{data.id} {START:%Y-%m-%d %H:%M} UTC, {MINUTES} min")
fig.colorbar(mesh, label="dB re 1 uPa$^2$/Hz")
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(name + ".png", dpi=150)
band.attrs = {k: str(v) for k, v in band.attrs.items()}   # NetCDF stores no datetime attributes
band.to_netcdf(name + ".nc")   # the spectrogram: time, frequency and dB
