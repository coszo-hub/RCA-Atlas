# OOI asset-management metadata

`build_asset_metadata.py` turns OOI's public [asset-management](https://github.com/oceanobservatories/asset-management)
repository into `data/OOIAssetManagement`, the corpus collection `ooi_asset_management`. It covers the RCA's cabled
instruments: the Axial and Hydrate Ridge sites (`RS*`) and the Endurance Array's cabled Oregon Shelf and Offshore
platforms (`CE02SHBP`, `CE04OSBP`, `CE04OSPS`, `CE04OSPD`).

| Chunk | Holds |
|---|---|
| `ooi_assets_<refdes>` | make and model; every deployment's dates, sensor asset, serial number, firmware, deploy and recovery cruises, position and depth; when it was last recovered |
| `ooi_assets_calibration_<refdes>` | the calibration coefficients in force for each deployment |
| `ooi_assets_type_<type>` | every instrument of a type, by make and model |
| `ooi_assets_site_<site>` | a site's instruments, most often redeployed first |
| `ooi_assets_cruises_<year>` | a year's cruises and the instruments each deployed and recovered |
| `ooi_assets_depth_<band>` | instruments by the depth of their latest deployment, deepest first |
| `ooi_assets_node_<site-node>` | the junction box, profiler pod or platform asset (and serial) on a node over time |
| `ooi_assets_sourced_<id>` | serial numbers and components a paper, web page or document gives, cited to that source |

Each instrument chunk opens with its timeline: each deployment against the one before (sensor and serial, make,
model and firmware, node box, calibration, position and depth, and the days out of the water).

Rules the chunks follow:
- A deployment's calibration is its sensor's latest calibration dated on or before the deployment's start.
- OOI seldom fills `CUID_Recover`. A deployment that ended during a cabled-array cruise is said to have been recovered
  on it, marked as inferred.
- A reference designator's latest `versionNumber` of each deployment is used.
- A node's history is the node.uid of the instruments deployed on it, each asset's period ending where the next
  begins. When the sheets put one asset on two nodes for more than 30 days, both nodes' chunks say so (four cases).
- Each chunk is cited by one source named for what it holds ("OOI asset-management: <refdes> deployments, assets and
  calibrations"), linked to its main file and listing every file it draws on.

## Serial numbers from papers, web pages and documents

`source_serials.json` lists them, curated: each entry was read in its source and names the instrument (or node) it
belongs to, its components with make, model and serial, and the exact quotes that support them. The build checks
each quote word for word against the corpus chunk it names and stops if one is missing. Each entry is its own
chunk, cited to its own source (a paper by its DOI), and the Worker fetches it with the instrument's record. An
entry states only what its source says; notes of our own (a misprint, a lost minus sign) are marked as RCA Atlas
notes. Searched for: S/N, SN and serial number(s) in the full text, COSZO documents, datasheets, web pages and RCA
Information; the rest were chip part numbers, model variables, a manual's example file and laboratory equipment.

It also writes `src/atlas_worker/src/asset_directory.json`, which the Worker bundles: which chunk holds which
instrument, site, type, cruise year and depth band. A question about serial numbers, deployments, cruises,
calibrations, makes or depth gets those chunks by id (`/v1/chunks`), because the main search ranks this collection's
few hundred chunks below web pages on the same instrument.

## Rebuild

```bash
cd source_material/repositories
git clone --depth 1 --filter=blob:none --sparse https://github.com/oceanobservatories/asset-management.git
cd asset-management
git sparse-checkout set --no-cone '/deployment/RS*' '/deployment/CE02SHBP*' '/deployment/CE04OSBP*' \
  '/deployment/CE04OSPS*' '/deployment/CE04OSPD*' '/bulk/*' '/cruise/*' '/vocab/*'
# add the calibrations of every sensor those deployments name
python3 -c "import csv,glob; print('\n'.join(sorted({r['sensor.uid'] for f in glob.glob('deployment/*_Deploy.csv') for r in csv.DictReader(open(f, encoding='utf-8', errors='replace')) if r.get('sensor.uid')})))" \
  | sed 's#.*#/calibration/*/&__*#' | (git sparse-checkout list; cat) | git sparse-checkout set --no-cone --stdin
cd ../../..
.venv/bin/python src/ooi_asset_management/build_asset_metadata.py
```

Then rebuild the corpus and redeploy the Worker, which bundles the new directory.
