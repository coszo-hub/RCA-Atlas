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
| `Arcada` | `chunks.jsonl` | documents, entities, relationships, source document | rebuild from pinned repository snapshot |
| `Literature` | `chunks.jsonl` | works, citation occurrences, authors/topics, glossary | rerun literature acquisition and graph build |
| `LiteratureFullText` | `chunks.jsonl` (a retrieval layer) | papers, passages, site/instrument mentions | `build_fulltext_corpus.py` from the full-text cache |
| `Websites` | `chunks.jsonl` | pages, figures, links, entities | recrawl public sites and repackage |
| `Instruments` | `chunks.jsonl` | instruments, types, sources, infrastructure | rebuild after upstream corpus changes |
| `coszo` | `graphrag/chunks.jsonl` | PDF sources, documents, pages, figures, entities | rebuild from document inbox/originals |
| `Datasheets` | `graphrag/chunks.jsonl` | PDF sources, pages, figures, products | rebuild from document inbox/originals |
| `Figures` | `graphrag/chunks.jsonl` | image sources, visual records, entities | rebuild after adding curated images/descriptions |
| `StationMetadata` | `chunks.jsonl` | stations, channel epochs, source documents | `build_station_metadata.py` (EarthScope StationXML) |
| `OOIAssetManagement` | `chunks.jsonl` | instruments, deployments, cruises, calibrations | `build_asset_metadata.py` (OOI asset-management) |
| `QAQC` | `graphrag/chunks.jsonl` | capabilities, HITL notes, tool manifest | live public plot lookup; optional plot generation |
| `Nereus` | `graphrag/chunks.jsonl` | RCA entities, observations, notes, telemetry | live allowlisted GraphQL with snapshot fallback |
| `AxialEarthquakes` | `graphrag/chunks.jsonl` | summaries, figures, sources; full events in runtime DB | live daily/event/figure queries plus snapshot |
| `COSZOHub` | `chunks.jsonl` | repositories, tools, metrics, diagnostics, artifacts | live rescan of growing output directories |
| `PIPortal` | `chunks.jsonl` | PI instruments, physical sites, download endpoints, tools, routing policy | corpus-first availability answer; user-invoked live browse/download |

The `manifest.json` in each collection is authoritative for the node files,
edge file, embedding input, record counts, source revision, and known
limitations. Counts below describe the current 2026-09-19 snapshot and will
change when a collection is rebuilt.

## Arcada

**Source and selection.** The source is
`https://github.com/mhemmett/arcada/`, pinned at commit
`14294bca45ce5f65fd6541bea68ab40fbc870659`. The conversion starts from the
repository's built `public/chunks.json` and retains all 802 rows covering RCA
instruments, papers, site context, and data-access guidance. Six duplicate
placeholder PI rows were assigned unique graph IDs and documented repairs;
none of the source rows was discarded. The native snapshot, catalogs,
embeddings, MiniSearch index, README, and license are kept under
`src/arcada_pipeline/source_snapshot/` for provenance.

**EarthScope station correction.** Arcada gives all 14 OO EarthScope stations
one template: broadband (or high-frequency) with BHZ, BHN and BHE. EarthScope's
channel metadata shows eight short-period Güralp CMG-6TF stations (AXAS1,
AXAS2, AXEC1, AXEC3, AXID1, HYS11, HYS12, HYS13) with EH/SH channels, five
broadband CMG-1T stations (AXBA1, AXCC1, AXEC2, HYS14, HYSB1), and the AXCC2
tiltmeter, closed on 2021-08-27. The build rewrites only those 28 rows'
Description and Channels lines from `src/arcada_pipeline/earthscope_stations.json`,
a dated snapshot made by `refresh_earthscope_stations.py`, and records each
original text hash in `source_row_repair` and `build_audit.json`.

**Corrections from independent sources.** Arcada was a preliminary database,
not double checked. `audit_arcada.py` checks it against sources it did not
produce and writes `corrections.json`, which the build applies, keeping each
row's original text hash and listing every change in `build_audit.json`
(433 rows):

- Titles: nine papers take the publisher's title from the literature catalog
  (PDF imports cut titles at ~100 characters; one repeated its title, one
  carried a footnote marker).
- Abstracts: two papers carried another paper's abstract (the autoencoder
  imagery paper, 10.1002/rob.21961, a COVIS paper's, with its keywords; the
  Axial tsunami paper, 10.1029/2020GL087372, an AMOC review's) and take their
  own, from their first page. Two Frontiers papers whose first chunk is PDF
  front matter are led by the publisher's abstract.
- Paper-to-instrument links: the "Relevant instruments" lists were assigned by
  keyword (a sonar keyword linked every ASHES instrument; the tsunami and
  imagery papers carried the same list). A link is kept only where the paper's
  own text (its Arcada chunks and its full text) names the instrument by an
  unambiguous code, or names its type and site in one passage; instruments the
  text names by code are added. 709 links were removed across
  109 papers; 83 remain.
- Instruments: positions over 1.5 km from their OOI site and depths over 20 m
  off take OOI's site pages (63 records). All 30 Axial
  profiler instruments sat 21 km away near the International District; the
  Slope Base profilers 2 km and International District 2 2.5 km off;
  International District 1 was at 1,555 m (1,516 m). A profiler's Depth line
  says where it is (the 200 m platform; the profilers move through the water
  column), while `depth_m` stays the site's water depth, as the atlas reads it.
  The DAS experiments' placeholder position (45.0, -128.0) is cleared.
- Site pages and guides: the three site-context records held only the OOI
  website's navigation menu, cut before the page's text; each now says what it
  is (the page's text is in the Websites collection). The seismic guide's
  station list (HYSB1 is at Oregon Slope Base) and sample rates (HH* 200 Hz,
  EH*/SH* at the short-period stations) follow EarthScope's metadata; the PI
  portal guide's folders (2021 DAS OptaSense and Silixa, 2025-26 MultiDAS and
  OptoDAS, SCPR) and layouts follow the PI portal audit.

Not changed: Southern Hydrate Ridge Summit's 775 m (OOI's page gives 772, 775
and 811 m), a historical deep-profiler designator absent from today's
inventory, two papers without a DOI, and the M2M guide's method for
deep-profiler streams, which no local source confirms or contradicts.

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
copy exists. Current output: 260 documents, 802 chunks, 71 entities, and 2,528
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

## Literature full text (a retrieval layer)

`data/LiteratureFullText` is built by `src/literature_fulltext/build_fulltext_corpus.py`
from the validated full-text cache: 301 papers (174 supplied under license,
the rest open access), 15,332 page-level passages. Reference-list pages and
fragments under 40 words are left out (3,265 and 4,276 pages). Each paper keeps
its literature-catalog ID and DOI link, so a passage cites the same source, by
the same number, as the paper's abstract.

It is a layer, not a peer of the other collections. The search leaves any
`*_fulltext` collection, and any chunk marked `retrieval_layer`, out unless a
request names it (`migrations/003_retrieval_layers.sql`, `004_paper_passages.sql`).
RCA Information's 18 full-text papers keep one chunk each in the main search;
their other 475 chunks are marked as layer passages at normalization
(`src/graphrag_runtime/retrieval_layers.py`), so one long paper no longer fills
a literature answer's evidence. When the main evidence holds a paper, the
Worker asks `paper_passages` for that paper's passages only (by DOI or catalog
ID, the passage's `paper_keys`), ranked by the question's meaning and by its
words weighted by how rare they are among those passages. A paper the evidence
only names by DOI (an OOI page adapted from a paper) is searched too, and a
question asking two things is searched part by part. The Worker skips passages
that mostly repeat the evidence (a first page restating the abstract) and keeps
four passages a paper and eight in all (a lone paper may take all eight), after
the main evidence and in 11,000 characters of their own; with passages, the
main evidence gets 12,000 characters (18,000 without). The prompt so stays near
26,000 characters, about 5,800 tokens: Groq's free tier refuses any request
over 8,000 tokens a minute, and the earlier 34,000-character prompts (7,700
tokens) were refused every time. Five passages instead of eight missed two
full-text facts. The builder strips publisher download stamps (Wiley, Science,
GeoScienceWorld) from the passages. PDF text is extracted in reading order
(`pdftotext` without `-layout`): `-layout` kept two-column pages' columns side
by side, so every line spliced the left column into the right;
`reextract_pdfs.py` re-extracts the cache. On all 33 literature eval questions
with GPT-5.4 mini, every asked fact (79 of 79) is answered.

Map: each paper carries `places`, the atlas sites (or reference designators)
its passages name most, specific sites first; a paper on Axial or Hydrate Ridge
as a whole is placed at the summit caldera or Southern Hydrate Ridge. The
Worker adds them to the paper's hits, where the map finds site names.

Papers that used a sensor ("which papers used AXEC1 and AXEC2?"): no abstract
names a sensor, and RCA Information's `LINKS_INSTRUMENT` edges are not usage
(they link 79 papers to AXEC2, among them an imagery paper and a DAS paper,
where the full text of nine names it). The answer rests on the papers' own
text. Passages `MENTIONS` the OO seismic stations by station code (167 edges,
`EARTHSCOPE-OO-AXEC2`) as well as the sites, systems and reference
designators. The Worker finds the instrument records the question names (its
codes, its acronyms such as BOTPT, else the type asked), takes the codes papers
write (station code, reference designator, instrument code such as CTDPFB304,
node such as MJ01A, a title acronym such as COVIS), and asks
`graphrag_api.papers_naming` (`migrations/005_papers_naming.sql`) for the
papers whose full text names them, by whole word, one best passage each. It
adds passages found by the instrument's name, which must name the place the
question gives. The model separates papers that used the instrument's data
from papers that only mention it.

Passages are never shown to readers. The Worker sends no excerpt for any paper
(abstract or full text); the answer cites the paper, whose DOI link leads to
the full text. It may use the paper's own wording.

Graph: each paper `HAS_FULLTEXT_PASSAGE` its passages, and a passage `MENTIONS`
the RCA sites, named systems (COVIS, BOTPT, the Regional Cabled Array) and
reference designators it names, by literal match only, with the words and page
on the edge. A caldera or vent-field name counts only where the passage also
names Axial. The entities carry the names and reference designators other
collections use, so they resolve across collections by identifier.

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

**Errata.** Where a page misstates the paper it cites, `errata.jsonl` (kept in
git) replaces the wrong phrase in that chunk with the paper's value. Each entry
names its chunk, the exact wrong and right text, the authority (title and DOI)
and the reason. The normalizer and the embedding build both apply them, and the
build stops if an entry's wrong text no longer appears exactly once in its
chunk. The corrected chunk's metadata keeps the entry, so the change is
traceable. There are four entries: the stacked-sills lens spacing on "Discovery
of the Roots of the Axial Seamount" (Carbotte et al., 2020: 300–450 m, not
400–500 m), and the Southern Hydrate Ridge plume height on "Explosive Bubble
Plume Emissions" (Philip et al., 2016: plume tops at 320–620 m below sea level
over seeps at about 780 m, not ~480 m above the seafloor), and the Axial Base
shallow profiler mooring's parts on its own site page, which repeats the Slope
Base mooring's codes (SF01A, PC01A) where its instrument table and OOI's
vocabulary give SF03A and PC03A, and the International District 2 page's
sentence on its neighbour, which calls it International District 2 and ASHES
where OOI's vocabulary puts MJ03C at International District 1 (International
District 2 is on MJ03D, ASHES on MJ03B). The answer prompt
also labels evidence as scientific literature or website, and prefers the
literature where they disagree.

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
preserving its established graph ID. Arcada catalogs only RS sites, so the
Coastal Endurance cabled benthic experiment packages the RCA powers are added
from the archived official OOI site inventories (`OOISiteInventory/`): the
Oregon Offshore package (CE04OSBP, off PN1C, nine instruments) and the Oregon
Shelf package (CE02SHBP, off PN1D, eleven), each with OOI's depth, node, and
make and model, at the platform position OOI ERDDAP publishes, with record
status `official_inventory_instance`. The planned COSZO Oregon Offshore and
Oregon Shelf instruments remain separate records; the Oregon Shelf package
shares its location, "Oregon Shelf", with the planned station on the same spot.
Their names follow the RCA's own records ("3D Current Meter", "Broadband
Hydrophone", "pH Sensor"), with OOI's class wording kept as an alias. Two
current RCA instruments that OOI publishes data for but Arcada predates are
added with status `ooi_data_instance` (OOI asset management, ERDDAP): the Axial
shallow profiler's replacement vertical ADCP `VADCPB301` (August 2024) and the
International District fluid sampler's temperature probe `D1000A301`, each at
the position of the Arcada record on its platform port. The OOI page's
`RS01SBPD-DP01A-03-FLNTUA104` is kept as an alias of Arcada's `04-FLNTUA104`.
Each record on a node the site inventories list says what it is mounted on,
from the inventory's node column (a record the page no longer lists takes its
node's): a profiler mooring's fixed 200 m platform (PC01A, PC03A) and moving
shallow profiler (SF01A, SF03A) hold instruments that otherwise share a name
("Shallow Profiler CTD Profiler"), and the deep profilers and seafloor junction
boxes are named the same way, each with a few words from OOI's site pages on
whether it moves.
Instruments OOI asset management lists that no other source catalogues are
added from it with status `ooi_asset_instance`, named as it names them (with
the RCA's own class wording, OOI's kept as an alias), at their latest
deployment's position and water depth: the Oregon Offshore cabled shallow and
deep profiler moorings the RCA powers (CE04OSPS, 16; CE04OSPD, 5) and the
Central Caldera's Pinnacle ADCP `PADCPA301` and acoustic transponders
`FETCHA301`. A code on the port of a catalogued instrument of the same class
(the Oregon Offshore package's test hydrophone `HYDBBA110`) is that
instrument's alias instead.

**Every ID an instrument goes by.** Each record lists, as aliases, every other
ID the corpus names it by, so that a record citing any of them reaches it: the
reference designator OOI asset management and Nereus use where it differs from
the record's (a PI instrument catalogued by its bare code, `CTDPFA110` or
`PI-CAMPIA101`; a page's spelling, `SCPRAAA301` for `SCPRAA301`, A-0-A's
`AOABPA301` for `A0ABPA301`), matched by instrument code at the same site; an
OBS's reference designator on its EarthScope station, the station nearest its
latest deployment (all within 26 m, one to one); a COSZO station's EarthScope
name on each instrument it holds; and each reference designator without its
port. The map indexes them all, and a reference designator no sensor carries
(a profiler's engineering stream) stands for its node's site. Of the 392
records in the asset-management, Nereus, inventory, station and RCA
Information collections that name one instrument in their title, all reach
that instrument on the map (385) or, for the engineering streams and two
instruments only Nereus lists, their site (7).
Current output: 213 instruments, four infrastructure records, 78 entities,
38 sources, 213 chunks, and 1,448 relationships.

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

**Source and normalization.** The RCA stations' (AX*, HY*) channel-level StationXML comes from EarthScope's FDSN
station service, saved under `source_material/stationxml/earthscope`; the four COSZO stations (CZ*) keep the COSZO
and Nanometrics StationXML in `source_material/stationxml`. `src/data_maintenance/build_station_metadata.py` rebuilds
the collection (`--refresh` fetches EarthScope again). Station and channel fields retain network, station, location,
channel code, start/end epoch, coordinates, orientation (azimuth, dip), sample rate, sensor description, instrument
sensitivity, units, source file, and source hash. The first build (until 2026-10-23) used 2017 StationXML that held
only some stations' pressure and tilt channels, so no seismometer channel, sensor or azimuth was in the corpus.

**Deduplication and chunking.** Repeated channel epochs are merged only when
network, station, location, channel, start time, and end time are identical;
all contributing source IDs remain attached. The structured layer contains 18
stations and 663 channel epochs. One summary chunk per station lists, for each period its channels ran together,
the sensor, channels with sample rates, and which horizontal components point where. One more chunk sets out every
station's seismometer orientation for questions across the network that no single station's chunk answers: which
seismometers are rotated from north (not an error, since the recorded azimuth rotates them back), and which have an
orientation issue, metadata one sensor cannot have (its channels at different azimuths, or a north and east channel of
one band not 90° apart). AXID1 and HYS11 list their EHN channel at 0° and their other north
channels at 35°, as EarthScope gives them. One sensor records all of a station's channels, so this is inconsistent
metadata, not two orientations (HYS11's EHE is at 125°, which puts its EHN's 0° out of line); the chunks keep each
channel's value and say so. Detailed
channel values remain atomic in `channels.jsonl`.

**Graph construction.** Stations and channels become 398 entity nodes, with a
`CHANNEL_OF` edge for each channel epoch. Source-document nodes record the
archived XML and SHA-256. The normalizer is part of
`src/data_maintenance/clean_data_folder.py`.

## OOI asset-management

**Source.** OOI's public asset-management repository on GitHub (sparse clone in
`source_material/repositories/asset-management`, commit `279ace5`, 2026-10-20): the deployment sheets of the RCA's
cabled sites (`RS*`, `CE02SHBP`, `CE04OSBP`, `CE04OSPS`, `CE04OSPD`), the asset records (make, model, serial number,
firmware), the cruise list, the vocabulary, and the calibration files of every sensor those deployments name.
`src/ooi_asset_management/build_asset_metadata.py` builds the collection; its README gives the clone commands.

**Records.** 166 instruments, 1,413 deployments and 25 nodes. Each instrument's chunk gives its make and model, every
deployment (dates, sensor asset, serial number, firmware, deploy and recovery cruise, position, depth) and when it
was last recovered; a second chunk gives the calibration coefficients in force for each deployment (the sensor's
latest calibration dated on or before the deployment's start; long arrays are summarized). Summary chunks answer
questions across instruments: each type's instances by make and model, each site's instruments by how often they
were redeployed, each year's cruises with what they deployed and recovered, and depth bands. OOI seldom records a
recovery cruise; a deployment that ended during a cabled-array cruise is said to have been recovered on it, marked
as inferred. Firmware is recorded for 8 of the 369 sensor assets, so most records say it is not recorded.

**Timelines and nodes.** Each instrument chunk opens with its changes over time: each deployment against the one
before (sensor and serial, make, model and firmware, node box, calibration, position, depth, days out of the water).
Each node (junction box, profiler pod or platform, deep-profiler vehicle) has a chunk with the asset and serial on it
over time, from the node.uid of the instruments deployed on it. Four node assets are on two nodes at once for more
than 30 days in OOI's sheets; both nodes' chunks say so.

**Serial numbers from other sources.** Papers, web pages and documents give serial numbers OOI does not: the
cabled SCPR's gauges (Paroscientific 44.4K SN 136576 and 46K SN 132123; Sasagawa et al. 2023), SCPR unit 001's gauges
at Axial in 2013-2014 (410K SN 116504 and 118710; Sasagawa et al. 2016, Sasagawa and Zumberge 2013), the A-0-A's
transducers (the OOI page prints SN136580 for both), the 2017 change-out of Axial Base's LJ03A (SN011 and SN007, a
VISIONS'17 blog) and a COSZO test record's medium-power junction box 024. They are curated in
`src/ooi_asset_management/source_serials.json` with the exact quotes; the build checks each quote against its corpus
chunk. Each is its own chunk cited to its own source. Nereus's asset serials were compared and agree with OOI for
141 of the 144 assets both list (the other three are blank in OOI), so they add nothing.

**Retrieval.** These few hundred chunks rank below web pages on the same instrument, and search's lexical half does
not match hyphenated reference designators. The builder writes a directory (`src/atlas_worker/src/asset_directory.json`)
that the Worker bundles; a question about serial numbers, deployments, recoveries, cruises, calibrations, makes or
depth gets the named instrument's chunks, or the type, site, cruise-year or depth chunks, by id (`/v1/chunks`,
migration 006) at the head of its evidence. A place named without a platform means its seafloor instrument when it
has one ("the Axial Base CTD"); the profilers' are asked for as the shallow or deep profiler's.

**Catalog mismatches.** Thirteen reference designators in the instrument catalog, all from RCA Information, are not
in OOI asset-management, among them `RS03AXBS-LJ03A-12-HYDLFA301` (OOI: `RS03AXBS-MJ03A-05-HYDLFA301`),
`RS03ASHS-MJ03B-15-OBSSPA301` (OOI: `RS03ASHS-MJ03B-06-OBSSPA301`), `RS01SBPD-DP01A-03-FLCDRA104` and `-04-FLNTUA104`
(OOI: `…102`), and BOTPTs at Axial Base and Southern Hydrate Ridge that OOI does not list.

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
| Arcada | 268 | 3,662 |
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
