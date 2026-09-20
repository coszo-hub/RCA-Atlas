# COSZO / RCA website corpus pipeline

`crawl.py` builds the website corpus used by the RCA Graph-RAG project.

Stages:

1. `discover` indexes public WordPress APIs, sitemaps, and the static COSZO site.
2. `build` extracts clean content and keeps COSZO and Regional Cabled Array material plus directly linked technical resources.
3. `package` writes the ingestible JSONL, Markdown text, captioned figures, graph relationships, manifest, and validation report.

Source URLs are retained so the agent can cite claims, collapse aliases, and refresh changed pages. Other OOI arrays are excluded by page-level relevance tests and explicit array-name filters. Pages that discuss RCA alongside another array retain only target-relevant text where it can be separated safely.

The recovery helper documents a one-time split-batch recovery for an Interactive Oceans API response that timed out. Network response cache and discovery/selection logs are kept with this source pipeline, outside the runtime data folder.

Run with the bundled Python environment used by the project:

```sh
python crawl.py discover
python crawl.py build
python crawl.py package
```

The package is accepted only when `validation_report.json` reports `passed`.
