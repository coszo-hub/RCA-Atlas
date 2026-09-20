# Axial Seamount earthquake retrieval and Graph-RAG data

This package combines a historical structured snapshot with credential-free live tools for the University of Washington Axial Seamount Earthquake Catalog.

## Answering day-count questions

Use `axial_count_events`. Its default day is `yesterday`, and all calendar-day boundaries are UTC. For example:

```json
{"name":"axial_count_events","arguments":{"day":"yesterday"}}
```

The tool fetches `hypo71/hypo71_YYYYMMDD.dat`, parses valid catalog rows, and reports the exact row count, source URL, retrieval time, filters, and whether the requested day is partial. It accepts `today`, `yesterday`, or an ISO date such as `2026-09-18`. A magnitude or depth threshold can be supplied. If live retrieval fails in `auto` mode, it uses the bundled SQLite snapshot and labels the result `snapshot_fallback`.

Axial daily filenames are UTC dates. The `07:00:00` displayed on the archive index is a listing timestamp and is not used as a day boundary. Zero-event files remain valid zero counts; an unavailable file returns an error rather than zero.

## Data design

`data/AxialEarthquakes/graphrag` contains Graph-RAG inputs:

- `daily_summaries.jsonl` and `monthly_summaries.jsonl`: activity aggregates.
- `chunks.jsonl`, `entities.jsonl`, and `relationships.jsonl`: embedding and graph inputs.
- `figures/manifest.jsonl`: live figure products and dated URL patterns.
- `figures/current/`: a timestamped snapshot of current maps, histograms, focal-mechanism maps, and RSAM figures; the tools still fetch live versions when answering.
- `source/`: compressed/raw provenance snapshots.
- `manifest.json`, `validation_report.json`, and `tool_manifest.json`.

`runtime_data/AxialEarthquakes/graphrag` contains the indexed `events.sqlite` query store and compressed full event/focal-mechanism exports. They remain outside the embedding corpus because the live tools query them directly.

Each earthquake row has a synthetic `record_key`. The upstream `event_id` is preserved but cannot be used as a unique primary key because the full source contains multiple solutions for some IDs. Exact counts therefore count valid catalog rows.

The graph chunks explain the catalog, methods, fields, RSAM, focal mechanisms, and monthly activity. Individual numerical events stay in SQLite/JSONL so an LLM does not have to retrieve approximate counts from embedded prose.

## MCP server

Run from the project root:

```bash
src/axial_earthquakes/run_mcp.sh
```

The thirteen tools cover catalog status, exact daily counts, range searches, individual events, activity summaries, station arrivals, focal mechanisms, monthly focal summaries, focal-event beachball/map/waveform products, live source figures, generated event maps, and natural-language routing. `axial_get_figure` returns JPEG source figures as MCP image content; `axial_get_focal_event_product` returns the selected PNG; `axial_plot_events` creates a figure from exact event rows.

The visual archive indexes every dated caldera and regional map without bulk-copying thousands of redundant JPEGs. `figures/archive_manifest.jsonl` gives each map its exact UTC date and URL. `figures/focal_event_products.jsonl` records the detail page, beachball, map, and waveform URLs for every current focal-event product. These large archives are retrieved live on demand by date or event ID.

No credentials are required. The site currently serves catalog data over HTTP, so every result retains the source URL and UTC retrieval time.

## Refresh the snapshot

```bash
python3 src/axial_earthquakes/snapshot_axial.py --output-dir tmp/axial-source
python3 src/axial_earthquakes/build_axial_corpus.py \
  --source-dir tmp/axial-source \
  --output-dir data/AxialEarthquakes/graphrag \
  --runtime-dir runtime_data/AxialEarthquakes/graphrag \
  --source-archive-dir source_material/AxialEarthquakes/source_snapshot
python3 src/axial_earthquakes/snapshot_visual_pages.py \
  --index tmp/axial-source/focal-mechanisms.html \
  --output-dir tmp/axial-source
python3 src/axial_earthquakes/build_visual_archive.py \
  --source-dir tmp/axial-source \
  --corpus-dir data/AxialEarthquakes/graphrag \
  --source-archive-dir source_material/AxialEarthquakes/source_snapshot
```

Current day and recent questions should use the live tools. The snapshot is the historical query store and fallback.
