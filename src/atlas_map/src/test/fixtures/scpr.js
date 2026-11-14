// The file's own preamble and header (Axial-Seamount/self-calibrating-pressure, 2026-11-14), with a few rows.
export const SCPR_CSV = `# SCPR OO.AXCC1 seafloor pressure, 3600-s means, 2018-07-06 .. 2026-11-13 (UTC)
# Gauges: PARO1 = loc 40 (Paroscientific SN 136576), PARO2 = loc 41 (SN 132123). Pressure in Pa (absolute).
# *_drift_sigma: 1-sigma uncertainty of the drift removed. *_n: 1-Hz samples averaged.
# Empty corr: drift uncertainty > 100 Pa (corrected until 2026-08-21); after the last calibration
#   (2026-02-05) the drift is extrapolated (provisional).
# Calibration table 3a0bedc3aa5d; generated 2026-11-14T00:50Z by scpr_export.py
time_utc,paro1_raw_pa,paro1_corr_pa,paro1_corr_masked_pa,paro1_uplift_m,paro1_drift_sigma_pa,paro1_n,paro2_raw_pa,paro2_corr_pa,paro2_corr_masked_pa,paro2_uplift_m,paro2_drift_sigma_pa,paro2_n
2018-07-06T08:00:00Z,15546892.6,15546892.6,15546892.6,,40.0,736,15559038.8,15559038.8,15559038.8,,40.0,736
2025-12-01T00:00:00Z,15540000.0,15539000.0,15539000.0,0.612,90.0,3600,15552000.0,15551000.0,15551000.0,0.598,90.0,3600
2026-11-13T22:00:00Z,15551361.7,,,,136.9,3600,15562312.9,,,,136.9,3600
2026-11-13T23:00:00Z,15549385.0,,,,136.9,3600,15560336.3,,,,136.9,3599
`;
