# Literature pipeline support files

`../../data/Literature/literature.jsonl` remains the canonical, unchanged literature source. The graph conversion is additive:

- `documents.jsonl`: normalized graph metadata for 336 works
- `chunks.jsonl`: the only embedding/retrieval input
- `entities.jsonl`: verified authors, resource types, literal topics/sites, glossary terms, and referenced resources
- `relationships.jsonl`: graph edges with evidence and extraction methods
- `citations.jsonl`: all 398 source-occurrence evidence records
- `source_documents.jsonl`: proposal PDF, Zotero group, and glossary source nodes
- `glossary_terms.jsonl`: structured extraction of the eight glossary entries
- `text/`: deterministic Markdown representations of every literature work

`code/build_graph_corpus.py` reproduces these graph artifacts. It deliberately avoids guessing author identities or work-to-work citation edges from inconsistent citation strings. Author edges are emitted only for verified structured names; topical edges use curated literal matches with evidence.

The `archive/`, `provenance/`, and `reports/` directories preserve collection history and QA outside the runtime data folder.

The on-demand full-text integration is maintained separately under
`src/literature_fulltext/`. It resolves canonical work IDs, occurrence aliases,
and DOIs against `literature.jsonl` without modifying that file. The agent must
search the abstract corpus first. Only a relevant but insufficient abstract may
trigger `literature_full_text_evidence`; the tool validates public URLs and
redirects, enforces download/page/OCR limits, caches under
`runtime_data/Literature/full_text_cache`, and returns bounded passages with
page or section provenance. `data/Literature/tool_manifest.json` registers the
MCP server with Graph-RAG discovery.
