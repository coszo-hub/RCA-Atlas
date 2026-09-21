# RCA/COSZO data corpus and Graph-RAG preparation method

## Purpose

This note describes how every collection currently under `data/` was acquired,
selected, normalized, chunked, connected as a graph, validated, and paired with
live tools where the source changes over time. It is the project-wide method.

The corpus is scoped to the Ocean Observatories Initiative Regional Cabled
Array (RCA), COSZO, directly supporting technical material, and the Axial
Seamount earthquake products used by this agent. Website pages devoted only to
other OOI arrays were excluded. A few cross-array or external records remain
when they are direct evidence for an RCA/COSZO instrument, method, publication,
or computational output; those records retain their scope labels.

## Directory contract

The project separates material by function:

```text
data/             normalized Graph-RAG and multimodal retrieval inputs
source_material/  original PDFs, spreadsheets, XML, repository snapshots,
                  raw downloads, and the inbox for future additions
runtime_data/     versioned retrieval builds, operational databases, full
                  exports, and live caches
src/              extraction, conversion, validation, and MCP tool code
```

Only Markdown, JSON, JSONL, PNG, and JPEG files belong in `data/`. Original
PDFs, spreadsheets, StationXML, HTML snapshots, CSV files, archives, and
databases were moved out so a loader cannot accidentally embed opaque source
files or runtime state. `data/cleanup_validation.json` records the last format
audit, while `source_material/move_manifest.jsonl` records moved paths, file
sizes, and SHA-256 checksums.

New source documents should be placed in
`source_material/inbox/<collection>/`, processed by the corresponding builder
under `src/`, and published into `data/` only after validation passes. Originals
then remain under `source_material/original_documents/` or the appropriate raw
source directory.

## Common Graph-RAG design

The collections share these rules even though their source formats differ:

1. **One canonical retrieval layer.** Embed the `text` field in the collection's
   `chunks.jsonl`. Do not also embed complete documents, pages, or Markdown
   review copies as separate retrieval documents. Those files provide metadata,
   full context, display, and provenance.
2. **Stable, namespaced identifiers.** Documents, pages, chunks, entities,
   figures, observations, and sources use deterministic IDs derived from source
   identity, content, or a stable domain key. Namespacing prevents collisions
   when the collections are merged.
3. **Explicit graph inputs.** Node files describe sources, documents, pages,
   chunks, figures, instruments, observations, capabilities, and named
   entities. Relationship files connect those records with predicates such as
   `HAS_CHUNK`, `HAS_PAGE`, `MENTIONS`, `LOCATED_AT`, `AUTHORED_BY`,
   `HAS_STATUS_OBSERVATION`, or `PRODUCES`.
4. **Evidence stays attached.** Source URL, original filename, page locator,
   repository commit, retrieval time, SHA-256, source row, DOI, or observation
   time is retained wherever available. URLs are kept because they are needed
   to cite an answer, refresh changing sources, reproduce extraction, and
   collapse aliases. Local files do not replace that provenance.
5. **Structured facts stay atomic.** Daily counts, channel epochs, telemetry,
   metric rows, status observations, and event records are stored as structured
   records. Large tables are not flattened into prose chunks that could blend
   values from different dates or instruments.
6. **Images remain addressable.** Image metadata links a semantic text record
   to local pixels or an on-demand source URL. OCR and supplied captions are
   kept separately from curated descriptions so the origin of visual text is
   clear.
7. **Untrusted-source marking.** Retrieved text and metadata are marked as
   source data and must never be interpreted as agent instructions.
8. **Snapshot plus live tools.** Stable knowledge is indexed in Graph-RAG.
   Operational values that can change after a build are queried through MCP
   tools, with timestamped snapshot fallback where available.

## Unified runtime corpus catalog

The first Graph-RAG runtime step is implemented by
`src/graphrag_runtime/discover_corpora.py`. It discovers every
`data/**/manifest.json` and normalizes the different collection-manifest
dialects into `runtime_data/GraphRAG/corpus_catalog.json`. Source collections
are not rewritten.

For each collection the catalog records its root and manifest, the single
canonical embedding input, graph node inputs, graph edge inputs, exact
structured inputs, auxiliary non-embedded inputs, tool definitions, runtime
references, image counts, record counts, byte sizes, and SHA-256 hashes. It
validates that every JSONL row parses as an object and that every embedding
record has nonempty `text`. The catalog fingerprint changes whenever a
manifest or ingestion input changes, allowing later embedding and graph builds
to skip an unchanged corpus safely.

The current catalog contains 13 collections, 6,565 canonical embedding chunks,
23,404 graph-node records across 62 files, 30,242 graph relationships, 76,984
structured records, 56 auxiliary visual records excluded from duplicate
embedding, 4,855 local images, and six tool-definition files. Runtime loading
will embed only the declared chunk inputs, load all graph nodes before graph
edges, register structured inputs for exact queries, and keep live tools as a
separate action layer.

Rebuild the catalog after any collection changes:

```sh
python3 src/graphrag_runtime/discover_corpora.py \
  --project-root "/Users/quakehunter/Documents/RCN Agent "
```

## Production Graph-RAG runtime

The unified runtime is under `src/graphrag_runtime/`. It uses PostgreSQL with
pgvector for public deployment; SQLite remains appropriate only for isolated
local fixtures and operational caches. PostgreSQL stays on a private network
behind a bounded FastAPI service. The public API database role has no access to
base tables and may execute only parameterized search, traversal, and tool
routing functions. API keys are stored as SHA-256 digests, and production
ingress provides TLS, rate limits, request limits, and audit logs.

`normalize_corpus.py` reads the catalog and creates an immutable load package
without changing any collection. It preserves all 23,404 physical node rows,
including duplicate representations from different files, while producing
21,938 logical nodes keyed by `(collection_id, local_id)`. This namespace is
required because 71 raw IDs occur in more than one collection. It also retains
all 30,242 physical edge rows and creates 29,538 unique traversal facts. Every
one of the 60,484 edge endpoints resolves. Structured sidecars remain atomic
rather than being converted to prose.

The 6,565 canonical chunks are embedded locally with the public
`BAAI/bge-small-en-v1.5` model through FastEmbed. The vectors are normalized
384-dimensional `float32` values. The build records the model revision,
artifact hash, text hash, dimensions, and normalized flag so stale or mixed
embeddings cannot be activated. The model is cached once and can run fully
offline afterward.

Retrieval combines pgvector cosine rank with PostgreSQL full-text rank through
reciprocal-rank fusion. A bounded recursive query can expand the selected
nodes by at most three graph hops. Evidence responses retain collection, node,
chunk, source URL, and locator. Tool manifests are indexed separately: the
first response comes from corpus evidence, while changing data sources are
recommended as agent tools. Tool routing never executes the tool itself.

Each rebuild loads under an immutable build ID, validates source hashes,
record counts, links, edge endpoints, full-text rows, embedding dimensions and
text hashes, and only then switches a single active-build pointer in one
transaction. Readers see a complete old or complete new build, and the prior
build can be retained for rollback. Current normalized outputs live under
`runtime_data/GraphRAG/normalized`; model vectors and their mapping live under
`runtime_data/GraphRAG/embeddings`.

## Collection-to-runtime map

| Collection | Primary retrieval input | Main graph/structured records | Refresh model |
|---|---|---|---|
| `RCA Information` | `chunks.jsonl` | documents, entities, relationships, source document | rebuild from pinned upstream snapshot |
| `Literature` | `chunks.jsonl` | works, citation occurrences, authors/topics, glossary | rerun literature acquisition and graph build |
| `Websites` | `chunks.jsonl` | pages, figures, links, entities | recrawl public sites and repackage |
| `Instruments` | `chunks.jsonl` | instruments, types, sources, infrastructure | rebuild after upstream corpus changes |
| `coszo` | `graphrag/chunks.jsonl` | PDF sources, documents, pages, figures, entities | rebuild from document inbox/originals |
| `Datasheets` | `graphrag/chunks.jsonl` | PDF sources, pages, figures, products | rebuild from document inbox/originals |
| `Figures` | `graphrag/chunks.jsonl` | image sources, visual records, entities | rebuild after adding curated images/descriptions |
| `StationMetadata` | `chunks.jsonl` | stations, channel epochs, source documents | rebuild from StationXML |
| `QAQC` | `graphrag/chunks.jsonl` | capabilities, HITL notes, tool manifest | live public plot lookup; optional plot generation |
| `Nereus` | `graphrag/chunks.jsonl` | RCA entities, observations, notes, telemetry | live allowlisted GraphQL with snapshot fallback |
| `AxialEarthquakes` | `graphrag/chunks.jsonl` | summaries, figures, sources; full events in runtime DB | live daily/event/figure queries plus snapshot |
| `COSZOHub` | `chunks.jsonl` | repositories, tools, metrics, diagnostics, artifacts | live rescan of growing output directories |
| `PIPortal` | `chunks.jsonl` | PI instruments, physical sites, download endpoints, tools, routing policy | corpus-first availability answer; user-invoked live browse/download |

The `manifest.json` in each collection is authoritative for the node files,
edge file, embedding input, record counts, source revision, and known
limitations. Counts below describe the current 2026-09-19 snapshot and will
change when a collection is rebuilt.

## RCA Information (upstream Arcada provenance)

**Name and source.** RCA Atlas presents this collection as **RCA Information**.
Its stable internal collection ID remains `arcada`, and its upstream source is
preserved as Arcada for reproducibility and attribution; neither its original
identifiers nor its source URLs are renamed.

**Source and selection.** The source is
`https://github.com/mhemmett/arcada/`, pinned at commit
`14294bca45ce5f65fd6541bea68ab40fbc870659`. The conversion starts from the
repository's built `public/chunks.json` and retains all 802 rows covering RCA
instruments, papers, site context, and data-access guidance. Six duplicate
placeholder PI rows were assigned unique graph IDs and documented repairs;
none of the source rows was discarded. The native snapshot, catalogs,
embeddings, MiniSearch index, README, and license are kept under
`src/arcada_pipeline/source_snapshot/` for provenance.

**Normalization and chunking.** Original Arcada chunk text and its overlapping
paper boundaries were preserved rather than rechunked. IDs were namespaced,
text was normalized, and source and normalized hashes were recorded. The 802
chunks were grouped under 260 stable parent documents: 120 instruments, 134
papers, three site-context documents, and three data-access guides. Complete
document review copies were written to `text/`, but `chunks.jsonl` remains the
only embedding input.

**Graph construction.** Shared RCA/COSZO locations and projects use IDs
compatible with the other corpora. Edges connect documents to chunks, source,
content type, location, named concepts, and Arcada instrument identifiers.
Eleven linked identifiers absent from the source chunks were retained as
explicit unresolved instrument-reference nodes rather than dropped or guessed.
DOIs, journal/year, source URLs, FDSN links, OOI links, repository commit, and
the original source metadata remain attached.

**Validation.** The build checks that all 802 rows are retained, IDs are unique,
relationship endpoints resolve, each document has contiguous chunks, chunk
text is nonempty, placeholders and HTML are removed, and every Markdown review
copy exists. Current output: 260 documents, 802 chunks, 69 entities, and 3,211
relationships. Builder: `src/arcada_pipeline/build_arcada_graph.py`.

## Literature

**Source and selection.** The starting bibliography was extracted from every
relevant citation section in `COSZO Project DataMSRI.pdf`, including “Products
Most Closely Related to the Proposed Project,” “Other Significant Products,”
and “References Cited.” It was expanded with the public OOI Publications
Zotero collections `RMTSE2IH` and `E5UH7L89`. All source occurrences were
retained even when several occurrences resolved to the same work. The current
package contains 398 citation-occurrence evidence records resolving to 336
canonical works.

**Metadata and abstract acquisition.** Citation strings were parsed into
candidate title, author, year, and DOI fields. Records were resolved against
the Zotero metadata, DOI/publisher pages, Crossref or other public scholarly
metadata endpoints, and public full-text locations when available. Every
accepted value retains its source URL, retrieval status, attempts, and review
notes in `literature.jsonl`. DOI matches take precedence for deduplication;
normalized title and bibliographic evidence are used for non-DOI records.
Collection overlap remains provenance rather than a duplicate work. There are
291 works with abstracts; records without a reliable abstract still retain a
bibliographic retrieval chunk instead of fabricated text.

**Normalization and chunking.** Each work becomes a deterministic Markdown
record containing its title, citation, abstract when available, and a distinct
source description when present. It is split at 520 words with 50 words of
overlap. The current 336 works produce 353 bounded chunks. `literature.jsonl`
is the unchanged canonical record layer; `documents.jsonl` is its graph
projection; `chunks.jsonl` is the only embedding input. Eight definitions from
the RCA glossary PDF were extracted as structured glossary terms and short
retrieval chunks.

**Graph construction.** Nodes represent works, verified structured authors,
resource types, literal research topics and places, COSZO/RCA, source
documents, Zotero collections, proposal sections, and glossary terms. Edges
include `HAS_CHUNK`, `CITES`, `LISTED_IN`, `AUTHORED_BY`, `HAS_RESOURCE_TYPE`,
`MENTIONS`, and glossary/resource relationships. Author entities are created
only from structured names; inconsistent citation strings are not used to
invent author identities or work-to-work citation edges.

**Validation.** The build parses every JSONL record, verifies the canonical
source hash, preserves all 398 occurrences, checks IDs and graph endpoints,
requires a nonempty bounded chunk for every work, verifies Markdown hashes,
checks normalized DOI uniqueness, and confirms all eight glossary terms.
Acquisition history, audits, review queues, and prior records are kept under
`src/literature_pipeline/archive`, `provenance`, and `reports`, outside the
runtime corpus. Builder: `src/literature_pipeline/code/build_graph_corpus.py`.

**On-demand full-text evidence.** Abstract chunks remain the first retrieval
layer. When an abstract is relevant but cannot support the requested detail,
the agent may call `literature_full_text_evidence` with the enforced routing
reason `abstract_relevant_but_insufficient`. It resolves canonical work IDs,
citation-occurrence aliases, or normalized DOIs; checks a content-addressed
runtime cache first; and only then attempts an accessible copy from the
recorded full-text candidate or DOI-based open-access resolvers. It does not
bypass authentication or paywalls. PDF extraction retains one-based page
locators and applies bounded OCR to sparse pages; substantive HTML retains
section headings. The response is capped to question-matched passages rather
than the whole work. Raw files, extraction metadata, and chunks live under
`runtime_data/Literature/full_text_cache` and are never promoted into `data`
without a separate reviewed corpus rebuild. The read-only
`literature_full_text_status` tool checks cache and candidate state without a
network request. Code: `src/literature_fulltext/`; registration:
`data/Literature/tool_manifest.json`.

## Websites

**Source and scope selection.** Public content was discovered through WordPress
APIs, sitemaps, and ordinary HTML from `coszo.org`,
`oceanobservatories.org`, and `interactiveoceans.washington.edu`. Page-level
rules required explicit COSZO/RCA language, an RCA site or instrument, or a
direct link from accepted RCA content. Pages devoted to Pioneer, Endurance,
Station Papa, Irminger, Global, NEPTUNE/Endeavour, and other arrays were
excluded. In mixed-array articles, paragraphs devoted only to another array
were removed where they could be separated safely. Generic OOI instrument and
data-product pages were retained only when directly linked from accepted RCA
pages.

**Extraction and normalization.** Navigation, headers, footers, forms,
sidebars, comments, cookie elements, scripts, styles, and related-post blocks
were removed. Headings, paragraphs, lists, table rows, preformatted text,
quotes, and figure captions were converted into stable plain-text blocks.
Exact-text duplicate pages were collapsed to a canonical URL while aliases
were retained. The current corpus contains 1,289 pages: 933 Interactive
Oceans, 315 OOI, and 41 COSZO.

**Chunking.** Page text is divided first at headings. Long sections are split
into 520-word units with 50-word overlap. Adjacent units are packed into
heading-aware chunks no larger than 600 words, retaining heading names, source
spans, zero-based order, page ID, and URL. This produced 2,981 chunks. Full
page text and Markdown review copies remain available, but only
`chunks.jsonl.text` should be embedded.

**Figures and links.** Image occurrences preserve page context, supplied
caption, alt text, source URL, dimensions, hash, and retrieval status. A
captioned image is downloaded when it is at least 180 by 120 pixels. Uncaptioned
images remain metadata-only because there is no reliable semantic description;
the pipeline does not invent one. The current index has 6,706 figure records,
including 2,583 downloaded images and 12 failed legacy URLs. It also retains
121 directly linked technical documents for later document extraction.

**Graph construction and validation.** Pages link to chunks, figures, other
accepted pages, and five curated RCA/COSZO place/project entities. Every edge
is traceable to a source link or literal name match. Validation checks unique
IDs, complete relationship endpoints, nonempty chunks at or below 600 words,
and every referenced local Markdown or image file. The crawl and packaging
method is in `src/website_pipeline/crawl.py`; the coverage audit is in
`src/website_pipeline/AUDIT.md`.

## Instruments

**Source and reconciliation.** The inventory compiles instrument-level facts
already present in Arcada, Websites, Literature, COSZO documents and workbook
material, and StationXML. It keeps distinct record statuses for Arcada catalog
instances, COSZO site-specific instruments, confirmed RCA PI instruments,
time-bounded experiments, unresolved references, and workbook-defined project
assets. A catalog mention is not treated as proof of current operation.
Science junction boxes are modeled separately in `infrastructure.jsonl`.

**Normalization and chunking.** Names, aliases, reference designators, station
and node codes, site, type, manufacturer/model, components, coordinates,
depth, source URLs, evidence, project, and record status were normalized into
168 instrument records and 42 type summaries. Each instrument receives one
self-contained retrieval chunk so an answer does not combine the status or
location of different devices.

**Graph construction.** Instrument nodes connect to project, location, site,
node, normalized type, source evidence, and related records. COSZO workbook
totals and website descriptions are both preserved when their scopes differ;
the Oregon Shelf APG and current-meter rows remain explicitly
workbook-specified. The PI portal audit added the previously missing MARUM
CTD-DO instrument `CTDPFA110` and corrected A-0-A source/alias metadata while
preserving its established graph ID. Current output: 168 instruments, four
infrastructure records, 70 entities, 28 sources, 168 chunks, and 1,037
relationships.

**Validation.** The builder checks ID and endpoint integrity, one chunk per
instrument, retention of all 120 Arcada instrument/deployment records, all 25
COSZO site-specific records, source evidence on every record, and separation
of infrastructure from instrument totals. Builder:
`src/instrument_inventory/build_instrument_inventory.py`.

## COSZO PDF documents (`data/coszo`)

**Source preparation.** Ten project PDFs were processed, including tagged
text PDFs, image-heavy documents, scans, and composite packets. Originals are
kept under `source_material/original_documents/coszo`; only their extracted
text, graph records, and rendered images remain in `data/coszo/graphrag`.

**Page extraction.** Every one of the 947 pages was rendered to a page image.
Native PDF text was extracted first. Sparse pages, scans, and visual documents
were OCRed with Tesseract. A page uses OCR when native text is absent or too
sparse; visual documents can use a hybrid of native text and OCR labels when
the two contain materially different content. Native text, OCR text, selected
text, method, confidence, page number, locator, dimensions, image hash, and
render DPI remain separate in `pages.jsonl`.

**Chunking.** Chunk boundaries never cross a PDF page. Pages up to 650 words
remain whole. Longer pages target 450 words with 60-word overlap and prefer a
nearby punctuation boundary. This produced 981 chunks. Page order and chunk
order are explicit graph edges, so a retriever can expand around a hit without
losing the source page.

**Figures and graph construction.** Visual pages and detected figures are
represented by 517 figure records linked to the source document and page.
Literal mentions connect chunks to shared projects, sites, instrument types,
and exact instrument identifiers from the Instruments corpus. Composite
documents use parent/part edges. Duplicate content is kept for provenance and
linked with duplicate/update relationships rather than silently removed.

**Validation.** The package checks source/page counts, local page and figure
images, page coverage by a chunk or visual record, unique IDs, graph endpoints,
hashes, and duplicate links. Current output: 10 sources, 40 logical documents,
947 pages, 981 chunks, 517 figures, 21 local/shared entities, and 4,833
relationships. Builder: `src/coszo_pdf_pipeline/build_coszo_pdf_graph.py`.

## Datasheets

**Source preparation.** Nine technical PDFs were classified with curated
document and product metadata. Originals are kept under
`source_material/original_documents/Datasheets`; the Graph-RAG package is in
`data/Datasheets/graphrag`.

**Extraction and chunking.** All 451 pages were rendered. Native text was
extracted from every page; 37 sparse or schematic pages were also OCRed.
Bookmarked outline titles become section labels. Chunk boundaries are page
bounded: pages at or below 600 words remain whole, while longer pages target
450 words with 60-word overlap. The result is 492 chunks with exact PDF/page
locators. Every page retains its native text, OCR text, selected text, method,
confidence, and image.

**Figures and graph construction.** Pages containing schematics, raster
content, visual keywords, or sparse text receive a visual record and local
page image; 292 pages qualified. Graph entities describe the documented
products, software, standards, and linked COSZO/RCA instruments. Curated edges
distinguish current products, candidate replacements, companion manuals,
algorithm provenance, accepted sensor models, historical context, and
instrument components.

**Validation.** The builder checks that all nine PDFs and all pages are
included, every page image and visual record exists, every page has a chunk or
visual representation, intentional blank pages remain represented, IDs are
unique, and edge endpoints resolve. Builder:
`src/figures_datasheets_pipeline/build_datasheets_graph.py`.

## Figures

**Source and description.** The 15 curated standalone project images include
site maps, annotated node-location variants, scientific maps, instrument
plates, diagrams, and field photographs. Each image was visually inspected and
given a concise factual description and visual type. Tesseract separately
recovers visible labels. The original image is retained unchanged.

**Chunking and multimodal linkage.** One retrieval chunk is created per image.
It combines the verified title, visual type, curated description, and a bounded
OCR-label excerpt. The chunk and figure record carry the local `image_path`,
so text retrieval can hand the exact pixels to a multimodal model.

**Graph construction.** Literal description/OCR matches connect figures to
COSZO, RCA, sites, instruments, and infrastructure. Version families for PN1B,
PN1C, and PN1D are linked with `SAME_VISUAL_AS` and
`ANNOTATED_VARIANT_OF`. Perceptual/manual matches also connect copies and
thumbnails found in the Websites corpus.

**Validation.** Every supported source image must have a curated description,
OCR output, matching SHA-256, local file, and resolved graph endpoints. Current
output: 15 sources, 15 figure nodes, 15 chunks, 18 entities, and 86 edges.
Builder: `src/figures_datasheets_pipeline/build_figures_graph.py`.

## Station metadata

**Source and normalization.** Nineteen OOI StationXML files were parsed into
station records and channel-epoch records. Raw XML is archived under
`source_material/stationxml`. Station and channel fields retain network,
station, location, channel code, start/end epoch, coordinates, orientation,
sample rate, sensor description, instrument sensitivity, units, source file,
and source hash.

**Deduplication and chunking.** Repeated channel epochs are merged only when
network, station, location, channel, start time, and end time are identical;
all contributing source IDs remain attached. The structured layer contains 10
stations and 388 channel epochs. One summary chunk per station lists its
location, channel codes, epoch count, and sensor descriptions. Detailed
channel values remain atomic in `channels.jsonl`.

**Graph construction.** Stations and channels become 398 entity nodes, with a
`CHANNEL_OF` edge for each channel epoch. Source-document nodes record the
archived XML and SHA-256. The normalizer is part of
`src/data_maintenance/clean_data_folder.py`.

## QA/QC

**Static graph layer.** The QA/QC package describes the public dashboard,
upstream `rca-data-tools` capability, supported plot contract, instrument
resolution, HITL notes, and ten MCP capabilities. Short capability chunks let
the agent retrieve which operation can answer a QA/QC question. The current
snapshot also preserves 531 human-in-the-loop notes and a catalog summary of
58,291 RCA plot records.

**Live layer.** For a question, `qaqc_question_context` combines the local
instrument inventory, current public plot candidates, and dated HITL notes.
The other tools search plots, fetch a selected figure, inspect instrument
context, report runtime readiness, and plan or generate missing plots. Existing
public plot lookup does not require credentials. Plot presence alone is not
treated as a QA pass.

**Optional generation.** The pinned upstream QA/QC generation package and its
license are retained under `src/agentic_qaqc/vendor`. Generation dependencies
and OOI access are required to compute new plots; cloud/S3 workflows may also
need Prefect and AWS configuration. Execution remains disabled unless
`QAQC_AGENT_ALLOW_PIPELINE=1` is set, preserving this future capability without
requiring it for current retrieval.

**Graph and validation.** Sources, services, entities, and capabilities are
connected through `EXPOSES`, `GENERATES`, `IMPLEMENTS`, `RETRIEVES_FROM`,
`CALLS`, and `USES_CAPABILITY`. The current graph has 11 chunks, seven
entities, ten capabilities, and 17 relationships. Code and routing guidance:
`src/agentic_qaqc/README.md`.

## Nereus

**Source and scope.** The Nereus integration uses public allowlisted GraphQL
operations recovered from the current Nereus frontend bundle. It does not
scrape rendered pages and does not require an account. The build selects RCA
sites, nodes, deployments, assets, instruments, operational state, monitoring
notes, status history, power/current values, and engineering fields. Private
network-address fields are omitted.

**Normalization and chunking.** The timestamped snapshot contains 639 entity
records, 594 status observations, 171 operational notes, 17 engineering
telemetry records, and 126 instrument crosswalk rows. A concise chunk is built
for each useful RCA entity or operational record, while time-stamped values
remain structured. Exact reference-designator matches connect 97 Nereus
instruments to the local Instruments graph.

**Graph construction.** Edges represent site/node hierarchy, asset use,
current/latest deployments, hosted instruments, observations, notes, and
telemetry. The 493 chunks summarize retrievable context; structured status and
telemetry remain separately filterable.

**Live layer and validation.** Ten MCP tools query current inventory,
instrument and node status, notes, telemetry, histories, and power plots, with
the packaged snapshot as an offline fallback. Responses carry retrieval times
because the state is time sensitive. The builder validates source files,
counts, IDs, endpoints, crosswalks, and tool manifest. Code:
`src/nereus_pipeline/`.

## Axial Seamount earthquakes

**Source acquisition.** Public University of Washington Axial catalog files,
arrivals, focal-mechanism products, maps, histograms, RSAM plots, and summary
pages were downloaded or indexed. The historical snapshot contains 317,696
valid catalog rows from 2015-01-22 through the build time. Upstream event IDs
are not unique for all solutions, so every row receives a synthetic
`record_key`; exact counts count valid rows.

**Structured/event design.** Full event and focal-mechanism exports plus
`events.sqlite` live under `runtime_data/AxialEarthquakes/graphrag`. Individual
events are intentionally not embedded as prose. The data corpus contains 3,898
daily and 141 monthly summaries plus 173 short method, source, activity, and
visual chunks. This lets semantic retrieval explain the catalog while tools
perform exact date, magnitude, depth, station, or event queries.

**Visual design.** Current maps and plots are stored as a timestamped local
snapshot. The archive manifest indexes 8,566 dated caldera/regional map URLs,
and 9,023 focal-event product bundles retain detail, beachball, map, and
waveform URLs. Large repetitive archives are fetched by date or event ID rather
than copied into the embedding corpus. The 28 visual chunks are already
included in the 173 main chunks and must not be embedded a second time.

**Live layer.** Thirteen MCP tools provide catalog status, exact daily counts,
range search, event lookup, activity summaries, arrivals, focal mechanisms,
figure retrieval, generated maps, and question routing. `yesterday` and
calendar dates use UTC boundaries. A valid zero-event file returns zero; an
unavailable file returns an error. Current-day and recent questions use live
HTTP first and may use the labeled snapshot fallback.

**Graph and validation.** Source, site, catalog, method, and product entities
are connected to explanatory and visual chunks. Builds validate event parsing,
summary totals, time semantics, source provenance, figure manifests, local
snapshots, and tool schemas. Code: `src/axial_earthquakes/`.

## COSZO Hub computational outputs

**Source and scope.** Four public computational repositories were pinned and
packaged: `absolute-seafloor-pressure`, `chronfix`, `dive-index-hindcast`, and
`sea-water-velocity`. `coszo-hub.github.io` was excluded because its published
content duplicates the COSZO website corpus. Repository snapshots, raw CSV,
NumPy, MiniSEED, NetCDF, PDF, XML, and other original artifacts remain under
`source_material/repositories/coszo-hub/`.

Two additional repositories inform the general live OOI interface:
`reedan88/OOINet` at commit
`2168c825d832cbb913f138b59fd8f2a82dc36dfc` (GPL-3.0) and
`ooi-data/ooi-harvester` at commit
`f4d4e467624006ea315bc823595e7951de368d1f` (MIT). Complete pinned snapshots
and their original license files are kept under
`source_material/repositories/ooi-m2m/`. They are software references rather
than retrieval documents. The ingestible corpus contains only compact source,
tool, and lineage records.

**Chunking and structured data.** The static graph uses one narrative chunk per
repository, short concept chunks for services/algorithms/formats/instruments,
and one discoverability chunk per MCP tool. Growing numerical tables are kept
as atomic typed rows: the current snapshot contains 70,262 metric records,
975 diagnostic text/log records, and 980 figure metadata records. Large tables
are never turned into blended prose chunks.

**Figures and graph construction.** Twenty-four high-value figures are copied
locally: Chronfix examples and validation, VEL3D summaries, and all Dive Index
report pages. Other daily figures remain in the source output trees and are
retrieved on demand. Entities represent repositories, artifacts, instruments,
algorithms, services, formats, credentials, streams, tools, and routing
policies. Relationships preserve which repository produces an artifact, which
instrument it serves, and which service or credential a process uses.

**Growing outputs and live tools.** Nineteen COSZO MCP tools rescan configured
output directories and incrementally update
`runtime_data/COSZOHub/output_index.sqlite`. Production paths can be supplied
with `COSZO_PRESSURE_OUTPUT_ROOT`, `COSZO_VELOCITY_OUTPUT_ROOT`,
`COSZO_CHRONFIX_OUTPUT_ROOT`, and `COSZO_DIVE_OUTPUT_ROOT`. New output files
then become queryable without rebuilding the vector corpus. Existing outputs
and public models are credential-free.

Ten additional OOI M2M tools let a future agent search the local instrument
inventory, retrieve live vocabulary/deployments/methods/streams, validate and
submit bounded NetCDF estimates or requests, poll asynchronous status, list
result files, and download a bounded selection with SHA-256 provenance. The
adapter accepts any valid OOI reference designator and is not restricted to
PREST; local discovery defaults to the RCA/COSZO instrument corpus. Request
planning and local search are credential-free. Live API actions require
`OOI_USERNAME` and `OOI_TOKEN`, which are never returned or persisted. Request
state and downloaded science files go under `runtime_data/OOIM2M/requests/`,
outside the retrieval corpus.

Six EarthScope FDSN tools provide current public station/channel search,
bounded MiniSEED request planning and download, StationXML download, and an
availability query that reports HTTP 410 explicitly while that legacy service
is unavailable during the 2026 cloud transition. Public data needs no
credentials. Waveform pulls require one exact station and default to a 24-hour
maximum; continuous real-time access belongs on SeedLink. Downloaded files and
hash manifests go under `runtime_data/EarthScope/requests/`. Four official
EarthScope documentation/transition sources are represented as graph
provenance rather than copied website content.

Six public PI portal tools expose the ten audited RCA PI collections and 31
download endpoints. The static `PIPortal` graph answers availability and
routing first; after the user asks for current files or a download, the same
MCP server performs a bounded live browse, search, plan, or download without
credentials. Results and manifests go under `runtime_data/PIPortal/requests/`.

**HYS14 Chronfix rule.** The bundled correction belongs to the HYS14 Hydrate
Ridge ocean-bottom seismometer clock. Although it was derived and validated
with `OO.HYS14..MHZ`, it applies to all channels recorded by that OBS, including
BHZ and HHZ. It does not apply to PREST pressure, VEL3D, another instrument, or
already-corrected UTC. Every correction reloads the current model files and
returns hashes and a combined bundle fingerprint; a live configured directory
is authoritative, otherwise the public checkout is refreshed by fast-forward
pull on a TTL.

**Validation.** The build validates JSONL, deterministic IDs, graph endpoints,
approved `data` file types, tool schemas, representative metric queries,
figure rendering, gap detection, HYS14 routing, cross-channel correction, and
model-refresh behavior. M2M tests additionally cover secret exclusion, request
bounds, stream discovery, durable state, async status, catalog parsing, host
and path guards, and bounded downloads using a simulated OOI service. Current
EarthScope tests cover offline planning, exact-station and time bounds, FDSN
text parsing, MiniSEED and StationXML persistence, hashes, URL guards, and the
availability-service transition response. Current output: four computational
repositories, two software reference nodes, four official EarthScope sources,
41 tools, 69 retrieval chunks, 2,067 entities, 2,091 relationships, 70,262 metrics, 975
diagnostics, and 980 figure records. Operational setup and implementation code
are under `src/coszo_hub_tools/`.

## RCA Principal Investigator data portal

**Source and scope.** The PI portal corpus covers the ten public RCA PI
instrument or experiment collections observed under
`piweb.ooirsn.uw.edu`: A-0-A pressure, SCPR pressure, COVIS, the 2021
OptaSense/Silixa DAS and DTS experiment, the 2024 DAS experiment, the
2025-2026 multi-span DAS experiment, the MARUM camera, MARUM CTD-DO,
MARUM overview sonar, and MARUM quantification sonar. Official OOI PI pages
supply instrument identity and physical deployment context; the live public
directory tree supplies the download endpoints and observed layouts. Arcada's
catalog was treated as prior evidence and corrected where its older registry
omitted collections or collapsed provider-specific formats.

**Corpus-first graph design.** Every PI instrument has a bounded retrieval
chunk whose first statement lists all known download sources. Instrument nodes
connect to physical site nodes with `LOCATED_AT` and to one or more endpoint
nodes with `DOWNLOADABLE_FROM`. Separate endpoint nodes preserve meaningful
branches such as A-0-A raw, command, ASCII, and NetCDF products; COVIS raw,
browse, engineering, and processed products; OptaSense and Silixa DAS/DTS;
camera stills and videos; SCPR pressure channels; and MultiDAS versus OptoDAS.
Known instrument and location IDs are reused from `data/Instruments` so merged
graphs can traverse from an RCA instrument to both its deployment site and its
download services. The newly confirmed CTDPFA110 record was also added to the
shared instrument inventory.

**Agentic retrieval.** Availability questions are answered from the static
corpus first: the response names the known source or sources, file formats,
layout, and physical site without making a network request. If the user then
asks to inspect current dates, find matching files, or download selected data,
the agent follows the endpoint relationship and invokes the public PI portal
tools. The tools list the audited registry, browse one directory, perform a
depth- and count-bounded search, validate a download plan, or download a
bounded selection. Results and SHA-256 manifests go under
`runtime_data/PIPortal/requests/`; raw science files never enter `data`.

The routing sequence is explicit:

1. Retrieve the instrument availability chunk from
   `data/PIPortal/chunks.jsonl` and answer with every applicable endpoint.
2. Traverse `DOWNLOADABLE_FROM` to the endpoint records and `LOCATED_AT` to
   the physical RCA site. Keep these two kinds of location distinct.
3. Use `pi_portal_list_instruments` for the audited local registry or
   `pi_portal_status` for runtime readiness; neither performs a live request.
4. After the user asks to inspect current holdings, call `pi_portal_browse` or
   `pi_portal_find_files` on the selected endpoint.
5. After the user asks to retrieve selected files, call
   `pi_portal_plan_download` first and then `pi_portal_download_files` with
   the returned relative paths. The download tool writes only to runtime data.

For example, “Where can I download COVIS data?” is answered entirely from the
corpus with its raw, browse, engineering, and processed endpoints. “Show the
available COVIS files for a date” invokes bounded live discovery, and
“download these selected files” invokes planning followed by the bounded
download tool. Live access is therefore an agent action reached through graph
relationships rather than a prerequisite for the first answer.

**Access controls and validation.** The portal currently responds over public
HTTP and requires no credentials. The adapter permits only the exact
`piweb.ooirsn.uw.edu` host, rejects credentials, query strings, fragments,
absolute paths, traversal, and redirects outside the host, and enforces page,
directory, file-count, timeout, retry, and byte limits. Large flat COVIS and
multi-terabyte DAS collections must be filtered before download. Tests use a
simulated directory server for listing, recursion, date filtering, alias
resolution, path and host guards, bounded persistence, and manifest hashes;
the live smoke test reads directory metadata or a small text file only. Code
and the reproducible graph builder are under `src/coszo_hub_tools/`. The
current corpus contains 10 instrument or experiment nodes, 31 endpoint nodes,
six physical-site nodes, 12 source nodes, six tool nodes, 373 relationships,
and 17 retrieval chunks. Rebuild it with:

```sh
python3 src/coszo_hub_tools/build_pi_portal_graph.py \
  --instrument-corpus data/Instruments/instruments.jsonl \
  --output data/PIPortal
```

## Network-information exclusion

The ingestible corpus retains public source URLs because they provide
provenance and route agent tools to public data services. Private, loopback,
link-local, and reserved network addresses; MAC addresses; internal hostnames;
credential-bearing URLs; and embedded secret-like values are excluded. Public
documentation placeholders such as `API_USERNAME` and `API_TOKEN` remain as
examples and are classified separately from real credentials.

Nereus requires recursive sanitization because operational-note prose can
contain an address even after structured `ipAddress` fields have been removed.
The live adapter now applies that sanitizer before returning or caching any
response, snapshots apply the same sanitizer, and the Nereus corpus builder
validates the resulting text. Its MCP schemas do not expose a network-detail
override. PDF page images and figure copies are also inspected through their
OCR metadata; when private addresses occur in a visual, the pixels and the OCR
text are redacted together and their SHA-256 references are refreshed.

Run the sanitizer after any source refresh and before catalog discovery:

```sh
python3 src/data_maintenance/sanitize_sensitive_network_info.py \
  --project-root "/Users/quakehunter/Documents/RCN Agent "
```

Then run the audit as a release gate:

```sh
python3 src/data_maintenance/audit_sensitive_network_info.py \
  --root data \
  --root runtime_data/GraphRAG/corpus_catalog.json \
  --output runtime_data/GraphRAG/network_information_audit.json
```

The audit report stores only redacted previews and SHA-256 values for findings;
it does not copy suspected secrets. A release passes only when
`sensitive_finding_count` is zero. Original source documents remain isolated
under `source_material/` and are never included in Graph-RAG discovery.

## Rebuild and addition workflow

For future additions, use this sequence:

1. Place the original in `source_material/inbox/Literature`, `Datasheets`,
   `coszo`, or `StationMetadata`, or refresh the relevant public/repository
   source with its acquisition script.
2. Record source identity before transformation: URL or repository, retrieval
   time, commit when applicable, filename, byte size, and SHA-256.
3. Run the collection-specific builder under `src/`. Keep source-type
   boundaries: heading-aware for HTML, page-bounded for PDFs, one visual record
   per image, one row per time-series observation, and one epoch per channel.
4. Review extraction quality. Scanned/sparse PDFs need OCR inspection; new
   standalone figures need a verified description; new instruments need an
   explicit record status and evidence.
5. Require the collection's validation report to pass. Check JSONL parsing,
   unique IDs, relationship endpoints, chunk bounds, local referenced assets,
   hashes, source retention, and expected record counts.
6. Run `sanitize_sensitive_network_info.py`, then require
   `audit_sensitive_network_info.py` to report zero sensitive findings.
7. Run the global data-folder audit:

   ```sh
   python3 src/data_maintenance/clean_data_folder.py \
     --project-root "/Users/quakehunter/Documents/RCN Agent "
   ```

   This is a dry run unless `--apply` is added. Review planned moves before
   applying them.
8. Ingest only the collection's declared chunk file into the vector index. Load
   the manifest-declared node and relationship files into the graph store.
   Register structured row stores and MCP tools separately.
9. Preserve the previous manifest, provenance, and review reports when a rebuild
   replaces a snapshot. Answers about live state should use the tools and cite
   their retrieval timestamp; the static graph supplies meaning, relationships,
   and historical fallback.

## Current corpus snapshot

| Collection | Files | JSONL rows |
|---|---:|---:|
| Arcada | 269 | 4,343 |
| AxialEarthquakes | 58 | 21,968 |
| COSZOHub | 34 | 76,489 |
| Datasheets | 764 | 3,629 |
| Figures | 24 | 149 |
| Instruments | 12 | 1,517 |
| Literature | 349 | 3,806 |
| Nereus | 15 | 4,313 |
| PIPortal | 10 | 457 |
| QAQC | 11 | 581 |
| StationMetadata | 8 | 1,213 |
| Websites | 3,882 | 22,545 |
| coszo | 1,486 | 7,349 |

The collection directories currently contain 6,926 files and 148,359 JSONL
records. Root-level control files include this note, `README.md`, and
`cleanup_validation.json`. Record totals do not represent independent facts: some files
are nodes, edges, evidence occurrences, summaries, or figure metadata, and
should be loaded according to their manifest rather than concatenated blindly.
