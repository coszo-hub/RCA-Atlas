# Upstream provenance

The integration was verified against:

- `OOI-CabledArray/QAQC_dashboard` commit `d8fa9e30ff5459f51f4e431cf2aa9e20f3985c96` (2026-08-31). The repository does not declare a license. No substantial dashboard source is copied here; the adapter uses its documented/public HTTP interfaces and independently implements the plot filename contract.
- `OOI-CabledArray/rca-data-tools` commit `03358ff29267dfa7ecede48c28915adb58ecb6ce` (2026-09-16), MIT licensed. The self-contained `rca_data_tools/qaqc` package is pinned under `vendor/rca_data_tools`, together with the upstream license, README, and `pyproject.toml`. Its heavy scientific dependencies remain an optional installation for plot generation and QA/QC computation.

Live evidence endpoints:

- `https://ec2.qaqc.ooi-rca.net/QAQC_plots/index.json`
- `https://ec2.qaqc.ooi-rca.net/HITL_notes/index.json`
- `https://ec2.qaqc.ooi-rca.net/api/health`
