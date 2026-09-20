# Ingestible corpus data

This directory contains the prepared RCA/COSZO retrieval, graph, structured,
and multimodal corpora. The complete dataset-by-dataset preparation method is
in [`CORPUS_METHOD.md`](CORPUS_METHOD.md).

Only Markdown, JSON, JSONL, PNG, and JPEG files belong here. Original PDFs,
spreadsheets, XML, raw downloads, and repository snapshots live in
`../source_material`; runtime databases and caches live in `../runtime_data`;
pipeline and MCP code lives in `../src`.

Do not add new originals directly to this directory. Place them in
`../source_material/inbox/<collection>`, run the relevant builder described in
`CORPUS_METHOD.md`, and publish the generated package only after its validation
report passes.

For vector ingestion, use the collection's declared `chunks.jsonl` input. Do
not embed both chunks and their parent document/page/Markdown copies. Load the
manifest-declared node files and relationship file into the graph layer, and
use the live tools for current operational values.

`cleanup_validation.json` records the last global file-format audit.
