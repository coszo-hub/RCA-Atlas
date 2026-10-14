"""Sandbox data-correction tools for RCA Atlas agents.

Each module is pure NumPy/SciPy and operates on arrays the agent has already
loaded (or on files inside its sandbox through `tools.dispatch`):

- `gaps`: diagnose data gaps, fill runs, and timestamp faults in a series.
- `timing`: ambient-noise cross-correlation, peak lags, clock offsets, jumps,
  and timestamp correction (a port of the chronos pipeline).
- `dvv`: relative velocity change by stretching, MWCS, and dynamic time warping.
- `pressure`: A-0-A and SCPR calibration sequences and linear drift correction.
- `earthquakes`: hypo71 parsing, counts, and histograms over date ranges.
- `router`: per-task priority routing of a question to its handler.
"""
