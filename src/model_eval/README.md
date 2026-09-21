# RCA Atlas Model Lab

The Model Lab evaluates answering models separately from retrieval and
embedding models. It never rebuilds embeddings when an answer model changes:
all answer-model comparisons receive an immutable `EvidencePackage` containing
the same stable chunks, entities, edges, figures, sources, and retrieval trace.

`config/providers.json` registers OpenAI, Anthropic, Moonshot, Google, and
generic OpenAI-compatible providers (including vLLM, SGLang, and Ollama).
Credentials are environment variables listed in the root `.env.example`; none
are stored here. Provider adapters fail closed when a required credential is
absent and are contract-tested with mock transports.

`config/embedding_indexes.json` keeps the deployed 384-dimensional
`BAAI/bge-small-en-v1.5` index and records candidate contextual-text, visual,
scientific-paper, and offline indexes. Routing is selective: figure questions
add visual retrieval, literature questions add scientific retrieval, and all
ordinary questions use text, keyword/identifier, and graph retrieval. Candidate
rankings are independently retrieved, fused with RRF (`k=60`), graph-expanded
(at most three hops), filtered, and reranked before an evidence package is
frozen.

The representative `datasets/rca_eval_v1.jsonl` set contains 50--100 questions
across instruments, locations, downloads, literature, figures, QA/QC,
Chronfix/HYS14, Axial events, tool routing, and full-text escalation. Records
written by `runner.py` are JSONL and include corpus/graph/index versions,
retrieved stable IDs, tool activity, answer/citations, token usage, latency,
cost, and automated or human scores.

Run local validation and a no-network cost projection:

```sh
PYTHONPATH=src python3.12 -m model_eval validate
PYTHONPATH=src python3.12 -m model_eval dry-run --models gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna
PYTHONPATH=src python3.12 -m model_eval cost-report results/evaluation.jsonl
```

Use `runner.run_frozen_answer_eval` for fair answer-only comparisons and
`GraphRAGOrchestrator` for a separately recorded end-to-end agent evaluation.
Per-request `Budget` limits output tokens, input context, tool calls, timeout,
and estimated spend. Query and content-hash embedding caches avoid repeat work.
Choose champions only from RCA Atlas results and retain challengers in
`config/champion_challenger.json`.
