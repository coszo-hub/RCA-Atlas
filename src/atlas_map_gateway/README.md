# Atlas gateway

A local service for live lookups. The atlas website calls it through Vite's `/api` proxy.

    uv pip install --python .venv/bin/python -r src/atlas_map_gateway/requirements.txt
    PYTHONPATH=src .venv/bin/uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787

Needs the bundle from `atlas_map_data`. Chat needs the Graph-RAG API running; set `ATLAS_API_URL` and `ATLAS_API_KEY`, or rely on `GRAPHRAG_API_PORT` and `GRAPHRAG_API_KEY` in the repo `.env`.

| Route | Source | Cache |
|---|---|---|
| `GET /status/{refdes}` | Nereus | 2 min |
| `GET /series/{refdes}/variables` | ERDDAP | 1 h |
| `GET /series/{refdes}?var&start&end` | ERDDAP (≤31 days, ≤2,000 points) | 5 min |
| `GET /plots/{refdes}` | RCA QA/QC | 30 min |
| `GET /waveform/{NET.STA}?minutes` | EarthScope (≤60 min) | 5 min |
| `GET /files/{instrumentKey}?path&endpoint` | PI portal (`endpoint` required when the instrument has several) | 5 min |
| `POST /chat` | Graph-RAG `/v1/answer` | none |

Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_gateway/tests -t src -v`
