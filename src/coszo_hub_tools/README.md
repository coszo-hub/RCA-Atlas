# COSZO Hub output tools

This package turns the computational repositories in the public `coszo-hub`
organization into two complementary resources:

1. A stable Graph-RAG snapshot under `data/COSZOHub` with normalized metrics,
   graph entities/relationships, provenance, output schemas, and selected
   figures.
2. A live MCP server that rescans the current output directories whenever a
   question is asked. New files become queryable without rebuilding Graph-RAG.

`coszo-hub.github.io` is excluded because the same content is already present
in the COSZO website corpus.

## Growing output directories

Defaults point to repository snapshots at
`source_material/repositories/coszo-hub/<repository>`. Production systems can
point directly at the directories written by the online pipelines:

```sh
export COSZO_PRESSURE_OUTPUT_ROOT=/srv/coszo/absolute-seafloor-pressure/PREST-data-collection/output
export COSZO_VELOCITY_OUTPUT_ROOT=/srv/coszo/sea-water-velocity/VEL3D-data-collection/output
export COSZO_CHRONFIX_OUTPUT_ROOT=/srv/coszo/chronfix/output
export COSZO_DIVE_OUTPUT_ROOT=/srv/coszo/dive-index-hindcast/output
```

The server updates `runtime_data/COSZOHub/output_index.sqlite` incrementally.
It does not copy growing raw data into `data`. Query results include the source
path, observation date, modification time, repository, and packaged commit.

Existing public outputs, Chronfix models, diagnostic figures, Dive Index plots,
local instrument search, and M2M request planning are credential-free. Live OOI
inventory, vocabulary, deployment, stream, estimate, and request calls require
`OOI_USERNAME` and `OOI_TOKEN`. `ooi_m2m_status` reports readiness without
returning either value.

## General OOI M2M tools

The MCP server exposes ten instrument-agnostic tools in addition to the COSZO
output tools:

- `ooi_m2m_status` and `ooi_m2m_search_instruments`
- `ooi_m2m_vocabulary`, `ooi_m2m_deployments`, and `ooi_m2m_list_streams`
- `ooi_m2m_plan_request` and `ooi_m2m_request_data`
- `ooi_m2m_request_status`, `ooi_m2m_list_result_files`, and
  `ooi_m2m_download_results`

`ooi_m2m_plan_request` performs no network call. It validates the reference
designator, method, stream, UTC interval, and configured 31-day request bound.
`ooi_m2m_request_data` submits an estimate by default; pass
`estimate_only=false` to start asynchronous data generation. The returned local
request ID is used for status, listing, and download calls.

Request records and downloaded NetCDF/provenance/annotation files are stored at
`runtime_data/OOIM2M/requests/<local-request-id>`. Request records contain no
credentials. Downloads are confined to that request directory, use approved
OOI HTTPS hosts, and are bounded by `OOI_M2M_MAX_DOWNLOAD_BYTES` (2 GiB by
default). Configure request and network limits with:

```sh
export OOI_M2M_MAX_REQUEST_DAYS=31
export OOI_M2M_MAX_DOWNLOAD_BYTES=2147483648
export OOI_M2M_TIMEOUT_SECONDS=30
```

The adapter is not limited to PREST. Its local search defaults to the RCA/COSZO
instrument corpus, while valid OOI reference designators can be supplied for
any instrument. [OOI_M2M_SOURCES.md](OOI_M2M_SOURCES.md) records the exact
OOINet and ooi-harvester source versions that informed the implementation.

## EarthScope FDSN tools

Six public-data tools use the current `service.earthscope.org` FDSN services:

- `earthscope_fdsn_status`
- `earthscope_search_channels`
- `earthscope_plan_waveform`
- `earthscope_download_waveform`
- `earthscope_download_stationxml`
- `earthscope_query_availability`

Public station metadata and waveform requests need no credentials. Waveform
requests require one exact network/station and are capped at 24 hours by
default, following EarthScope guidance. MiniSEED and StationXML results are
written under `runtime_data/EarthScope/requests/<local-request-id>` with a JSON
manifest, source URL, retrieval time, byte count, and SHA-256.

The availability service may return HTTP 410 during EarthScope's 2026 cloud
transition. The availability tool reports that state clearly; station and
dataselect calls continue independently. These tools are for bounded historical
or near-real-time retrieval. Use SeedLink for continuous real-time streaming.

```sh
export EARTHSCOPE_MAX_REQUEST_HOURS=24
export EARTHSCOPE_MAX_DOWNLOAD_BYTES=536870912
export EARTHSCOPE_TIMEOUT_SECONDS=120
```

## UW RCA PI portal tools

Six credential-free tools cover the ten audited Principal Investigator (PI)
datasets published at `piweb.ooirsn.uw.edu`:

- `pi_portal_status` and `pi_portal_list_instruments`
- `pi_portal_browse` and `pi_portal_find_files`
- `pi_portal_plan_download` and `pi_portal_download_files`

The static Graph-RAG corpus is the first source for availability questions: it
links each instrument to its RCA site and to every known download endpoint.
The live tools are used after that answer when a user wants to inspect current
directories or retrieve selected files. Covered collections include MARUM
sonars, camera and CTD-DO data; COVIS raw, browse, engineering and processed
products; the 2021, 2024 and 2025–2026 DAS experiments; SCPR; and A-0-A raw,
command, engineering, processed ASCII and processed NetCDF data.

The portal currently responds over public HTTP and uses no credentials. The
adapter allows only the exact `piweb.ooirsn.uw.edu` host, rejects path traversal
and credential-bearing URLs, confines files to
`runtime_data/PIPortal/requests/<local-request-id>`, and records source URLs,
retrieval times, sizes and SHA-256 hashes in a private manifest. Discovery and
downloads have explicit bounds. An unfiltered recursive search of the large,
flat COVIS raw archive is rejected; provide a filename, extension, or date
filter. Small retries handle intermittent connection refusals without changing
response-size limits.

```sh
export PI_PORTAL_MAX_INDEX_BYTES=10485760
export PI_PORTAL_MAX_DOWNLOAD_FILES=10
export PI_PORTAL_MAX_DOWNLOAD_BYTES=536870912
export PI_PORTAL_TIMEOUT_SECONDS=60
export PI_PORTAL_MAX_RETRIES=2
export PI_PORTAL_RETRY_BACKOFF_SECONDS=0.5
```

## HYS14 clock routing

The bundled Chronfix correction belongs to one instrument: the OOI HYS14
Hydrate Ridge ocean-bottom seismometer. The model was derived and validated
with the 8 Hz vertical channel `OO.HYS14..MHZ`; because the error belongs to
the instrument clock, the same correction applies to BHZ, HHZ, and every other
channel recorded by that OBS. Any question mentioning HYS14, RS01SUM1, or
Hydrate Summit receives this context automatically. PREST pressure, VEL3D
current-meter, other-instrument, and already-corrected UTC timestamps are never
changed by this rule.

Each correction call reads the three model files again. When
`COSZO_CHRONFIX_OUTPUT_ROOT` points to an online output directory, that live
directory is the source of truth. Otherwise the server periodically runs a
fast-forward pull on the public Chronfix checkout. Results include each model
file's SHA-256, modification time, and a combined bundle fingerprint so an
answer records exactly which correction version it used. Set
`COSZO_CHRONFIX_REFRESH_TTL_SECONDS` to control the pull interval (default 300).

## Run and test

```sh
src/coszo_hub_tools/run_mcp.sh
python3 -m unittest src/coszo_hub_tools/test_coszo_hub_agent_tools.py -v
python3 -m unittest src/coszo_hub_tools/test_ooi_m2m_agent_tools.py -v
python3 -m unittest src/coszo_hub_tools/test_earthscope_fdsn_agent_tools.py -v
python3 -m unittest src/coszo_hub_tools/test_pi_portal_agent_tools.py -v
```

Rebuild the static corpus after intentionally taking a new snapshot:

```sh
python3 src/coszo_hub_tools/build_coszo_hub_graph.py \
  --repository-root source_material/repositories/coszo-hub \
  --output-dir data/COSZOHub
```
