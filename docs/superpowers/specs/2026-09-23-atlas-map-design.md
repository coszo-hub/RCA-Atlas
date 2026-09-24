# Cascadia Offshore Sensor Atlas — design

Date: 2026-09-23
Status: draft for review
Scope: part 1 (sensor and data coverage map). The paper overlay is part 2 and gets its own spec.

## Purpose

The RCA and COSZO sensor networks are hard to see as a whole. Scientists cannot easily tell what is measured where, which sites are active, or how to get the data, and some regional stations with a lot of data get little research attention. The existing Atlas chat answers questions one at a time, but nobody gets an overview from it.

The atlas is a navigable 3D map of the seafloor off Oregon. It shows every catalogued sensor at its real location and depth, lets people open a site to see what is there, and shows live status and live readings where the source systems provide them. The chat stays available as a side panel.

**Users.** Scientists and program staff deciding where to look, what exists, and how to get it.

**Success.** Someone new to the array opens the atlas and within a minute understands what is measured where, what is running, and how to get the data. A scientist can go from "what's at Axial?" to a chart of yesterday's readings and a download link without leaving the page.

## Scope

In the first version:

- 3D seafloor relief from Axial Seamount to the Oregon coast, with a contour-line mode and a monochrome mode
- The RCA cable route
- Every sensor that has a location, grouped into sites and regions, with status
- Sensor-family filter, region navigation, search
- Site panel with an animated depth cross-section
- Sensor detail with live status, live data charts, and data access instructions
- Chat side panel that can be minimized, backed by the existing Atlas answer service
- Runs on a local machine

Not in the first version:

- Paper overlay and paper upload (part 2)
- Deployment history and a time slider
- Hosting on coszo.org
- Authenticated OOI M2M downloads (needs an OOI account)
- Any change to existing code under `src/` other than the three new folders

## What the data supports

These numbers come from the 2026-09-19 corpus snapshot in this repo.

**Sensors.** `data/Instruments/instruments.jsonl` lists 168 sensors. 152 have trusted coordinates. They form 28 sites in four regions:

| Region | Sensors | Notes |
|---|---:|---|
| Axial Seamount | 66 | caldera sites, vent fields, the base, 4 seismic stations |
| Oregon Slope Base | 37 | shallow and deep profilers, seafloor package |
| Hydrate Ridge | 34 | summit platforms, seismic stations, many new COSZO sensors |
| Oregon Shelf | 15 | COSZO sensors, many planned |

The other 16 sensors have no usable position: 13 have no coordinates, and three fiber-optic experiments (PI-DAS24, PI-DAS25, PI-DAS-OPTASENSE) carry a placeholder coordinate, 45.0, −128.0, that `corrections.json` clears. They are listed in the site panel of their named site where one exists (11 do); the other 5 are listed as unplaced. None appear on the map.

**Families.** About 40 instrument types map to six families. The mapping lives in one table in the build step. Counts are of located sensors.

| Family | Sensors | Types |
|---|---:|---|
| Water properties | 57 | CTD, oxygen, pH, pCO2, nitrate, fluorometers, spectrophotometers, mass spectrometers, thermistors, samplers |
| Pressure & strain | 28 | bottom pressure recorders, pressure gauges, self-calibrating pressure, strainmeters, HPIES |
| Currents & light | 24 | ADCP, velocimeters, 3D current meters, PAR, irradiance |
| Sound & imaging | 22 | hydrophones, cameras, sonar |
| Seismic | 21 | seismometers, OBS packages, geodetic modules, tiltmeters, pressure-tilt |
| Fiber-optic | 0 | DAS and DTS experiments along the cable. All four inventory entries lack a known position, so none are drawn; they are listed as unplaced |

**Status.** Nereus reports operational status for 126 reference designators. 97 of them match the inventory exactly. Sensors without a Nereus match are "planned" when the inventory marks them as new COSZO sensors, and "status unknown" otherwise. Nothing is inferred beyond that.

**Live sources.** Each was checked on 2026-09-23.

| Source | What it gives | Coverage | Browser can call directly |
|---|---|---|---|
| Nereus GraphQL | operational status, notes | ~97 sensors | yes (CORS open) |
| OOI ERDDAP (`erddap.dataexplorer.oceanobservatories.org`) | readings, public, no login; minute data from the previous day confirmed | 63 RCA datasets | no |
| RCA QA/QC plot site (`ec2.qaqc.ooi-rca.net`) | pre-rendered recent-data charts | 74 reference designators, 58,291 plots | images yes, index no |
| EarthScope FDSN | station metadata, waveforms | seismic stations | yes (CORS open) |
| PI data portal (`piweb.ooirsn.uw.edu`) | file listings and downloads | 10 PI instruments | no (plain HTTP, no CORS) |
| OOI M2M | full OOI data requests | ~92 sensors | no; needs credentials, out of scope |

All live calls go through our gateway, even the ones a browser could make directly. That keeps caching, rate limits, and error handling in one place.

**Data problems found while prototyping.** The build step must fix or flag these:

1. The Axial Base shallow and deep profilers (`RS03AXPS`, `RS03AXPD`, 24 sensors) are placed at 45.9316, -129.9808, in the caldera. Their listed depth is 2,607 m, but the seafloor at that point is 1,516 m. They belong near the Axial Base seafloor package at 45.8168, -129.754. A depth-versus-seafloor check found no other mismatches over 250 m.
2. Profiler sensors carry the site's water depth rather than their measurement depth. Their depth range comes from the node code: shallow profiler science pods (`SF`) move between about 5 and 200 m, 200 m platforms (`PC`) sit at 200 m, and deep profilers (`DP`) move between about 250 m and 150 m above the seafloor.
3. There was no cable geometry in the corpus. It now comes from public sources; see "Cable route".

A throwaway prototype, `.context/prototype/index.html`, which is not part of the build, validated the terrain look, the ring markers, the contour and mono modes, and the cable rendering. The spec's visual choices match it.

## Architecture

Three new folders. Nothing else in the repo changes.

```text
src/atlas_map_data/     build step: produces the atlas data bundle
src/atlas_map_gateway/  small local web service: live lookups and chat proxy
src/atlas_map/          the website (React + Vite + Three.js)
```

```text
data/ (corpus JSONL) ─┐
GMRT grids ───────────┼─► atlas_map_data ─► src/atlas_map/public/atlas/  (static bundle)
cable route file ─────┘

browser ─► atlas_map (static) ─► atlas_map_gateway ─┬─► Nereus, ERDDAP, QA/QC, EarthScope, PI portal
                                                    └─► existing Graph-RAG API /v1/answer (chat)
```

### Build step: `src/atlas_map_data/`

A Python script, `build_atlas_bundle.py`, reads the corpus and writes a static bundle that the website loads at startup. It has no network access except when it is asked to refresh the terrain or cable caches.

Inputs:

- `data/Instruments/instruments.jsonl`: identity, type, location, depth, source URLs, Arcada link
- `data/StationMetadata/stations.jsonl` and `channels.jsonl`: seismic station coordinates and channel epochs
- `data/Nereus/graphrag/entities.jsonl` and `instrument_crosswalk.jsonl`: status snapshot and the reference-designator match
- `data/PIPortal/*`: PI instruments, their physical sites, and download endpoints
- `data/QAQC/graphrag/catalog_summary.json`: which reference designators have plots
- an ERDDAP dataset list, fetched once and cached: which reference designators have public readings
- GMRT elevation grids (cached under `runtime_data/AtlasMap/terrain/`)
- the processed cable route, committed at `src/atlas_map_data/cable/rca_cable.geojson` with its build scripts (see "Cable route")

Outputs, under `src/atlas_map/public/atlas/`:

- `sensors.json`, one record per sensor:
  - `id`, `name`, `type`, `family`
  - `lat`, `lon`, `depth`, `depthRange`
  - `site`, `region`
  - `status`, `statusSource`, `statusAsOf`
  - `refdes`
  - `access`: a list of `{kind, label, url, how}` entries, with `kind` one of `erddap`, `qaqc`, `pi_portal`, `earthscope`, `ooi_explorer` or `documentation`
  - `arcadaId` (kept for part 2)
  - `sources` (provenance URLs)
  - `corrections` (a record of any fix the build applied)
- `sites.json`: site id, name, display label (unique), region, position, seafloor depth, sensor ids
- `regions.json`: four regions with camera views
- `cable.json`: cable polylines and node points, with source and accuracy
- `terrain/*.bin` and `terrain/terrain.json`: elevation grids as little-endian Int16 meters, plus bounds and cell size
- `auv/`: optional Axial summit tiles from MBARI's 1 m AUV survey, merged over a ship-survey background. These are level-of-detail tiles at 16 m, 4 m and 1 m (the 1 m tiles only near sites). Each tile is 257² Int16 decimeters relative to −1000 m, delta-encoded along each row, then gzipped. The tiles are built by a separate step that needs h5py and numpy. The site streams finer tiles as the camera approaches.

Rules:

- **Families** come from one explicit type-to-family table. An unknown type fails the build.
- **Sites.** A site is one physical location: every sensor within 150 m of another, whatever its OOI site code. For example, the Axial Base seafloor package, shallow profiler and deep profiler form one site of 33 sensors. The site is named after its seafloor platform, and the platforms it contains are kept as `parts` for the hover card and panel. Seismic stations with their own coordinates form their own sites. Site labels are unique: when a label repeats, it gets " · " plus the EarthScope station code for a single-station site, else the site's first node or site code, else an ordinal (for example "Southern Hydrate Ridge Summit · HYS13"). Names and ids are unchanged.
- **Status.** Use the Nereus status when the reference designator matches. Otherwise "planned" for sensors the inventory marks as a new COSZO sensor suite, otherwise "unknown".
- **Corrections** live in a small reviewed table (`corrections.json`) keyed by sensor or site, each with a reason. The build applies them and records them on the sensor. A correction may set `lat` and `lon` to null to clear an untrusted placeholder position; the sensor is then unlocated.

Validation. The build fails if any of these fails:

- Every located sensor has a family, a site and a region.
- Every status is a known value. An unrecognised Nereus status fails the build with the sensor and status named.
- Sensor counts reconcile with the inventory: located, unlocated and total.
- Every seafloor sensor's depth is within 250 m of the GMRT seafloor at its position. Mismatches must either appear in the corrections table or fail the build.
- Every `access` URL uses an allowed host.
- `sites.json` and `sensors.json` reference each other consistently.

### Terrain

- **Source.** GMRT GridServer, which is CC BY 4.0. It is credited on the map as "GMRT, Ryan et al. (2009)".
- **Overview grid.** 44.0–46.35°N, 130.6–123.7°W, at GMRT "med" resolution: 1,571 × 546 cells, about 350 m.
- **Detail patches.** Axial Seamount (45.78–46.08°N, 130.15–129.6°W) and Hydrate Ridge plus Slope Base (44.35–44.75°N, 125.5–124.9°W), at GMRT "high" resolution: about 45 m. The shelf uses the overview grid in the first version.
- **Seams.** Detail patches cut a hole in the overview and blend into it over the last 1 km, so no rectangle edge shows.
- **Survey-track artifacts** in the high-resolution data are softened in the shading only. Heights stay true.

### Cable route

The route was researched on 2026-09-23. The working file is `.context/cable/rca_cable.geojson`, and its build scripts are `build_geojson.py` and `skeleton.py` in the same folder.

- **Charted, about 85% of the length.** Source: NOAA/BOEM Marine Cadastre "Submarine Cable Areas", records 506 and 508, "RSN Backbone Cable", which are public domain and not for navigation. These are 61 m right-of-way strips; the centerline was traced from them with a medial-axis method. The route runs from the Pacific City landfall through PN1A, PN1B (with the Hydrate Ridge summit branch), PN1C and PN1D to the shelf, and along the north line through PN5A to the US EEZ limit. Segment lengths match OOI's published figures to within a few percent.
- **Approximate, about 88 km.** The EEZ limit to PN3A and PN3A to PN3B are straight lines, because no public geometry exists beyond the EEZ. PN3A uses the MJ03A junction box as a stand-in. PN3B is the center of its avoidance box, so it could be off by about 2 km.
- **Node positions** come from OOI mariner safety notices, OOI asset-management records, and the COSZO ship-time request in the corpus. They agree with the charted line to within about 0.4 km.
- **Left off the map:** undocumented stubs in the Marine Cadastre strips, and one of two parallel paths near PN5A. They stay in the data file with an "unidentified" label.
- **Better data is available on request.** The UW RCA team (ioceans@uw.edu) and the Oregon Fishermen's Cable Committee (staff@ofcc.com) share as-laid route files. Asking UW would replace the approximate Axial segments.

The build copies the processed route into the bundle as `cable.json`, so it doesn't need those external sites to be up. Charted segments draw as a solid line and approximate ones as a dashed line. The legend names the sources.

### Gateway: `src/atlas_map_gateway/`

A FastAPI app on `127.0.0.1:8787`. It imports his existing toolkits rather than reimplementing them:

- `NereusToolkit` (`src/nereus_pipeline/nereus_agent_tools.py`)
- `QAQCToolkit` (`src/agentic_qaqc/qaqc_agent_tools.py`)
- `PIPortalToolkit` (`src/coszo_hub_tools/pi_portal_agent_tools.py`)
- `EarthScopeFDSNToolkit` (`src/coszo_hub_tools/earthscope_fdsn_agent_tools.py`)

Each is called through its `dispatch(toolkit, name, arguments)` function, so the gateway inherits their host allowlists, bounds and sanitizers.

| Endpoint | Calls | Returns | Cache |
|---|---|---|---|
| `GET /status/{refdes}` | `nereus_instrument_status` | status, as-of time, latest operational note | 2 min |
| `GET /series/{refdes}/variables` | ERDDAP `info` | variables with units, time coverage | 1 h |
| `GET /series/{refdes}?var=&start=&end=` | ERDDAP `tabledap` CSV | time series thinned to ≤2,000 points (min/max per bucket), plus the full-resolution ERDDAP URL for download | 5 min |
| `GET /plots/{refdes}` | `qaqc_search_plots` | latest plot URLs by variable and time span | 30 min |
| `GET /waveform/{net}.{sta}?minutes=` | `earthscope_download_waveform` | decoded, thinned samples for up to 60 min | 5 min |
| `GET /files/{pi_instrument}?path=` | `pi_portal_browse` | one directory listing | 5 min |
| `POST /chat` | existing API `/v1/answer` | answer and citations, passed through unchanged | none |

ERDDAP is the only new client. It maps a reference designator to its dataset ID with the pattern `ooi-{refdes lowercased}`, for example `ooi-rs03axps-pc03a-4a-ctdpfa303`. The mapping is checked against the cached dataset list, so a missing dataset returns "no public feed" rather than an error.

Limits:

- Series requests are capped at 31 days per call.
- Waveform requests are capped at 60 minutes.
- Every upstream call has an 8-second timeout.
- Each upstream host is limited to 4 requests in flight.

The chat proxy holds the Graph-RAG API key server-side and forwards only the question and the fixed answer options. MiniSEED decoding uses ObsPy, a dependency of the gateway only.

### Website: `src/atlas_map/`

React 18, Vite, and Three.js, which are the same stack as `src/atlas_ui`. The 3D scene is a plain Three.js module owned by one React component, so the scene code stays independent of React. Site markers, labels and panels are HTML layered over the canvas, which keeps text crisp and hover simple.

Layout:

- **Center.** The 3D scene fills the window.
- **Left.** The chat panel, 380 px wide. It collapses to a small tab in the lower-left corner and remembers its state.
- **Right.** The site and sensor panel, 440 px wide. It slides in when a site is opened, and the scene stays visible and interactive beside it.
- **Top left.** Title and summary numbers: sensors, operating, sites.
- **Top right.** Terrain controls: Shape (Relief / Contours), Color (Depth / Mono), and vertical exaggeration.
- **Bottom center.** The family filter strip.
- **Bottom left.** Region navigation.
- **Bottom right.** Legend and credits.
- **Search** lives in the top bar and flies the camera to a sensor or site.

## Interaction design

### Scene

- **Navigation.**
  - Drag moves the view across the seafloor.
  - Ctrl-drag rotates and tilts around the view center. On a Mac, Cmd-drag and right-drag also rotate, and the Ctrl-click context menu is suppressed.
  - Scroll zooms toward the cursor.
  - Holding the arrow keys moves the camera smoothly: up and down move forward and back along the current heading, left and right move sideways. The speed scales with zoom, so a one-second hold covers about a third of the screen at any zoom level. Arrow keys are ignored while a text field or slider has focus.
  - On touch screens, one finger moves the view and two fingers zoom and rotate.
  - A one-line hint under the terrain controls lists these.
- **No motion without input.** The camera moves only on drag, scroll, arrow keys, or a requested flight. There is no cursor-follow movement.
- **Opening view.** The whole area from the coast to Axial, at 6× vertical exaggeration. Four region labels show sensor counts.
- **Region flights.** Clicking a region flies the camera there over 1.8 s, easing the exaggeration to 2.5–4×. Once the camera is close enough, site markers replace the region labels.
- **Three independent terrain switches:**
  - **View: 3D or 2D.** 3D raises the terrain by the vertical exaggeration. 2D flattens it over about 0.8 s and eases the camera straight overhead. Tilting is locked in 2D, water-column lines and labels hide, and the exaggeration slider is disabled. Switching back to 3D restores the previous tilt.
  - **Style: Relief or Contours.** Relief is a shaded surface with faint contour lines. Contours is a dark fill with bright lines at 50 m (patches) or 100 m (overview), and heavier lines every fifth interval. In 3D the contour fill keeps a faint shading so the landform still reads. All four combinations work: 3D relief, 3D contours, 2D shaded relief and 2D contour chart.
  - **Color: Depth or Mono**, as described below.
- **Color.** Depth uses a single-hue scale from pale stone at the shelf to deep slate at 4,800 m, with land in neutral gray. Mono uses grays only.
- **Vertical exaggeration.** A slider from 1× to 12×.

### Site markers

- **Ring.** Each site is a ring with one segment per sensor, colored by family. Segments are sorted by family, then status.
- **Status** is shown by the segment stroke, so color only ever means family:
  - operating: thick stroke
  - not deployed, retired, superseded, recovered or uncabled: thick stroke at 30% opacity
  - planned: thin stroke
  - unknown: thin dashed stroke
- **Operating halo.** Sites with at least one operating sensor get a faint halo that breathes on a 3.2 s cycle.
- **Vertical placement.** Every site marker sits on the seafloor at its true position, because that is where the platform or mooring is anchored. Nothing on the map floats. The height of the 3D scene is seafloor depth, and nothing else.
- **Water column (3D only).** A site with a mooring gets a thin dashed line from the seafloor up to the sea surface. The depths where sensors actually sample are drawn solid on top of it: the shallow profiler at 5–200 m, the 200 m platform, and the deep profiler at 250 m to about 150 m above the seafloor. One stacked label at the surface end reads, for example: "Sea surface 0 m / Shallow profiler 5–200 m / 200 m platform 200 m / Deep profiler 250–2,457 m / Seafloor 2,614 m". The legend explains the line.
- **Anchoring.** Markers and labels are projected every frame with the exact camera used for that frame's render, so they never drift. A marker hidden behind terrain from the current viewpoint fades to 12% opacity and loses its label and hover. This is tested by walking the sight line across the elevation grid.
- **Labels** show the site name and sensor count. Where labels would collide, the site with more sensors keeps its label.
- **Hover** shows the site name, seafloor depth, a family breakdown, the water-column reach, and up to 14 sensors grouped by platform, with status and depth or depth range.

### Cable and primary nodes

- **Cable hover** shows the segment (for example, "North backbone · Pacific City landfall → PN5A area · 268 km"), whether the route is charted or approximate and why, and a one-line explanation of the two backbone lines.
- **Primary nodes** are small square markers labeled with their code (PN1A–PN1D, PN3A, PN3B, PN5A).
  - **Hover** explains what a primary node is, lists catalogued sites within 30 km with their sensor counts, and gives the position accuracy and source.
  - **Click** flies the camera to the node.
  - **PN5A (Mid-Plate)** also carries OOI's own description: a placeholder node with minimal electronics for future expansion, and no sensors.
  - **Up close,** node codes hide so site labels take priority; the square stays.

### Family filter

- Six chips, each with a glyph, name and count.
- Clicking a chip focuses that family. Other families' segments fade to 7%, sites with none of the family fade, and the terrain desaturates.
- Shift-click adds families to the focus. Clicking the focused chip again clears the focus.
- Color follows the family and never changes with the filter.
- Six hues cannot all be told apart by colorblind readers when they are scattered across a map; the palette validator confirms this. So every family also has a distinct glyph (circle, triangle, square, diamond, hexagon, bar), which appears in the chips, the legend, tooltips and the cross-section. Identity never depends on color alone.

### Site panel: depth cross-section

- **The slice.** A side-on view from the sea surface to below the seafloor, 2 km across, centered on the site. The seafloor profile is sampled from the terrain grid, and the depth axis is in meters.
- **Opening animation.** The seafloor line draws left to right (500 ms). Then sensors settle into place family by family (60 ms stagger, 300 ms each). Water-column sensors that move are drawn as a vertical range bar covering their depth range.
- **Marker style.** Sensors are drawn as glyphs in family color with the same status styling as the rings. Co-located sensors fan out horizontally and keep their true depth.
- **Hover** shows name, type, depth or depth range, status with as-of time, and whether a live feed exists.
- **List.** Below the slice, the site's sensors are listed by family with the same information. It is sortable and keyboard-navigable.
- **Unlocated sensors.** Sensors without coordinates that name this site are listed here, marked "location not recorded".

### Sensor detail

Opening a sensor replaces the cross-section with the detail view. A back control returns to the site.

- **Header.** Name, family glyph, type, manufacturer and model when known, depth, and status. Status is re-fetched live on open, with its as-of time and its source.
- **Live data.** The view depends on which source covers the sensor:
  - **ERDDAP feed.** Pick a variable. Pick a range of 24 h, 7 d, 30 d, or custom (up to 31 days per request). The chart supports zooming with a crosshair tooltip. "Download this range" links to the full-resolution ERDDAP CSV.
  - **Seismic station.** The last 10 minutes of the vertical channel, zoomable, with a 1–60 minute selector.
  - **QA/QC plots only.** The most recent plots by variable, with a link to the plot archive.
  - **PI instrument.** A browsable listing of the newest directories and files, with links to open them.
  - **No live source.** "No live feed", with what is documented about the sensor and its planned deployment.
- **Get this data.** Every access route in plain language, with a link and a copyable snippet: an ERDDAP URL, Python using `erddapy`, or an EarthScope FDSN URL.
- **Sources.** Provenance links, plus any correction the build applied.

### Chat panel

- Uses the existing Atlas answer service through the gateway. Answers render with their citations.
- Shows suggested questions based on the current selection, for example "What research has used data from Axial Central Caldera?" and "What does a bottom pressure recorder measure?".
- The selection is not silently added to the user's question.
- Minimizing collapses the panel to a tab and keeps the conversation.

## Visual system

- **Surfaces.** Neutral near-black, not blue: `#121211` for the page and `#1a1a19` for panels, with hairline borders at 8–16% white.
- **Type.** IBM Plex Sans for interface text and IBM Plex Mono with tabular figures for numbers and IDs. Small uppercase labels are tracked at 0.06em.
- **Family colors,** stepped for the dark surface:
  - seismic `#d95926`
  - pressure `#c98500`
  - water properties `#3987e5`
  - currents `#199e70`
  - sound and imaging `#d55181`
  - fiber `#d9d6cc`
- **Status colors** are separate from family colors and always come with a word.
- **Glow.** None.
- **Motion.** Flights, the terrain flatten and the cross-section build are the only large motions. All motion respects `prefers-reduced-motion`.

## Errors and degraded states

- **Gateway unreachable.** The map still works from the static bundle. Live sections show "Live data unavailable. Showing snapshot from 2026-09-19."
- **Upstream timeout or error.** The section says which source failed and offers a retry. Other sections are unaffected.
- **Empty result.** The panel says "no readings in this range" and suggests the dataset's actual time coverage.
- **Status disagreement.** When the live status differs from the snapshot, the live value is shown with its as-of time.
- **Chat unavailable.** The panel says so. The map is unaffected.

## Testing

- **Build step.**
  - Unit tests for the family table, site clustering, status rules and corrections.
  - A full-build test on the repo's corpus asserting the reconciled counts (168 total, 152 located, 28 sites) and zero unexplained depth mismatches.
- **Gateway.**
  - Tests against recorded upstream responses for each endpoint, following the simulated-service pattern in the existing toolkit tests.
  - Tests for thinning, the range caps and the timeout path.
- **Website.**
  - Component tests for panel states: loading, live, no feed, error.
  - A Playwright run against a gateway serving recorded responses. The run loads the map, flies to Axial, opens a site, opens a sensor, draws a chart, filters a family and collapses the chat.
  - Screenshots of each major view, checked by eye at each milestone.
- **Performance target.** 60 fps orbiting on an Apple-silicon laptop, and first render in under 3 s from a local server.

## Running locally

```sh
PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle   # writes src/atlas_map/public/atlas/
PYTHONPATH=src .venv/bin/uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787   # live lookups and chat proxy
cd src/atlas_map && npm install && npm run dev               # http://127.0.0.1:5175
```

The chat needs the existing Graph-RAG API running, with `ATLAS_API_URL` and `ATLAS_API_KEY` set for the gateway.

## Risks and open questions

- **Status coverage.** Status covers only the Nereus-tracked sensors. COSZO sensors show "planned" or "unknown" until a status source exists for them.
- **ERDDAP coverage.** ERDDAP holds 63 RCA datasets against about 92 OOI sensors. The rest fall back to QA/QC plots or documentation.
- **Upstream politeness.** Nereus and the QA/QC site are operational systems run by the RCA team. Caching and per-host limits keep load low. Before any public deployment, we ask the RCA team about expected load.
- **Terrain detail.** GMRT high resolution is about 45 m. Vent-scale features at Axial are finer than that.
