# RCA Atlas sandbox tasks

These are the correction and calibration tasks from Maleen's notes, written as agent tools. Each
module is pure NumPy/SciPy and is validated by `src/atlas_eval` (see
`../atlas_eval/EVALUATION_METHOD.md`).

| Note | Module | Tool(s) |
|---|---|---|
| Diagnose the type of error: data gaps vs timing errors | `gaps.py` | `atlas_diagnose_series`, `atlas_fill_gaps` |
| Perform cross-correlation (chronos `compute_ccf`) | `timing.py` | `atlas_compute_ccf` |
| Compute peak lags for correcting timing errors (chronos `compute_peak_lag`) | `timing.py` | `atlas_peak_lag`, `atlas_clock_track`, `atlas_correct_times` |
| dv/v by stretching, MWCS, dynamic time warping | `dvv.py` | `atlas_dvv` |
| Find calibration sequences and apply calibration (A-0-A, SCPR) | `pressure.py` | `atlas_pressure_calibrate` |
| Non-self-calibrating gauges: calculate linear drift, apply known drift, correct | `pressure.py` | `atlas_pressure_drift` |
| How many earthquakes; histogram for date ranges | `earthquakes.py` | `atlas_quake_histogram` |
| Per-task priority | `router.py`, `router_rules.json` | `atlas_route_question` |

## Conventions

- **Timing.** A positive lag means station B lags A. Δt > 0 means B's clock is late, and
  true time = apparent − Δt (the same convention as chronos and chronfix). Hourly bins whose
  pick quality (CC² envelope peak / median) is below 20 are left empty rather than guessed.
  With `bin_s="auto"`, stacks lengthen to 6 h or 1 day when hours are too noisy.
- **dv/v** is a fraction: dv/v > 0 is a velocity increase, and cur(t) ≈ ref(t·(1 + dv/v)).
- **Pressure** is in kPa. Drift models are linear or exponential + linear (chosen by BIC
  with `drift_kind="auto"`). SCPR detection needs abrupt valve edges; pass `schedule`
  from the command log when it is available.
- **Earthquakes.** Days are UTC. A day with no catalog file, or an unreachable one, is
  listed in `missing_days` rather than counted as zero.

## Running

```sh
PYTHONPATH=src .venv/bin/python -m pytest src/atlas_tasks          # unit tests
ATLAS_SANDBOX_DIR=/path/to/sandbox .venv/bin/python src/atlas_tasks/mcp_server.py   # stdio MCP server
```

Tool inputs are files inside `ATLAS_SANDBOX_DIR` (`.npz`, `.npy`, `.csv` with a header,
or `.json`); paths outside it are refused. `ATLAS_QUAKE_CACHE` caches completed catalog
days.

Not done yet: the date-range histogram *panel* in the Atlas map UI. `atlas_quake_histogram`
returns the bins and can write a PNG, so the panel only needs to call it.
