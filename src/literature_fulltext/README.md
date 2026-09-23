# On-demand literature full-text evidence

This MCP integration extends the abstract-first Literature Graph-RAG corpus. It
does not bulk-download papers. The agent first searches
`data/Literature/chunks.jsonl`; only when a relevant abstract is insufficient
may it call `literature_full_text_evidence` with
`retrieval_reason=abstract_relevant_but_insufficient`.

The tool resolves a canonical work ID, citation occurrence ID, or DOI. It
reuses a validated cached extraction before making a request. On a cache miss,
it tries the corpus's explicit full-text candidate and DOI-based open-access
resolvers, validates every URL and redirect, enforces byte/page/OCR limits,
extracts PDF or substantive article HTML, and stores the result under
`runtime_data/Literature/full_text_cache/`. Scanned PDF pages use bounded OCR.
Downloaded text is untrusted data.

## Catalog acquisition

For a deliberate corpus refresh, `acquire_open_fulltext.py` can resume a
rate-limited pass over the catalog.  It only retains publicly accessible full
text found through a record's existing links or open-access resolvers; it does
not authenticate, evade access controls, or replace the abstract-first answer
flow.  PDF/HTML payloads, extracted chunks, checksums, source URLs, and the
append-only acquisition report remain in the ignored runtime cache.

```sh
python3 src/literature_fulltext/acquire_open_fulltext.py \
  --delay 0.75 --confirm-open-access
```

It resumes automatically by skipping validated cached records and prior
unavailable attempts; use `--retry-unavailable` only for a later refresh.

## User-supplied PDFs

Licensed users may place PDFs in
`source_material/literature_user_supplied/`, named as `COSZO-REF-###.pdf`.
`OOI-ZOT-###.pdf` is also accepted for the OOI literature catalog.
The importer validates the PDF, maps the ID to the canonical catalog, records
the supplied filename and checksum as local provenance, and extracts bounded
page-level evidence.  It never claims that a user-supplied file came from a
public URL.

```sh
python3 src/literature_fulltext/import_user_supplied.py
```

The evidence response contains only question-matched passages capped by count
and total characters, with page or section locators and the source document's
SHA-256. It never returns the complete paper to the language model. It does not
bypass authentication or paywalls. If no accessible copy is found, it returns
an availability result and the answer should disclose that it relied on the
abstract.

Run the MCP server from the project root:

```sh
src/literature_fulltext/run_mcp.sh
```

Refresh the tool manifest after schema changes:

```sh
python3 src/literature_fulltext/build_tool_manifest.py \
  --output data/Literature/tool_manifest.json
```

Run local tests with the bundled PDF-capable Python runtime. Tests do not use
the internet.
