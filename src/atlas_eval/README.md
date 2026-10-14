# RCA Atlas evaluation harness

`atlas_eval` holds one eval set per RCA Atlas capability, a runner that records every case
with provenance, statistics with 95% intervals, and a report generator. The method write-up
is [`EVALUATION_METHOD.md`](EVALUATION_METHOD.md). The latest report is
[`results/2026-10-08-baseline/report.md`](results/2026-10-08-baseline/report.md).

**Browse a run:** open `results/<run>/catalog.html` in any browser. It is one
self-contained file (figures and data embedded) with every suite's method,
metrics and figures; every case with its input, expected truth, the system's
output, scores and errors, filterable by suite, status and text; and the run's
environment (commit, Python and libraries, Node, Claude CLI, endpoint, answer and
judge models, dataset hashes, the agent's sandbox tools, and the task routes).
Build it with `python -m atlas_eval site results/<run>` (`report` builds it too).

| Suite | Needs | Dataset | Cases |
|---|---|---|---|
| `routing` | Node | `datasets/routing_v1.jsonl` | 156 labelled questions (dev/test) |
| `quake_questions` | Node | `datasets/quake_questions_v1.jsonl` | 26 |
| `retrieval` | live Worker | `../model_eval/datasets/rca_eval_v1*.jsonl` | 60 |
| `answers` | live Worker (+ `claude` CLI for the judge) | v1 + `datasets/answers_extra_v1.jsonl` | 72 |
| `quakes` | Node | `datasets/quakes_v1.jsonl` | 35 |
| `gaps` | — | `datasets/gaps_v1.jsonl` | 120 |
| `timing` | — | `datasets/timing_v1.jsonl` | 60 |
| `dvv` | — | `datasets/dvv_v1.jsonl` | 72 × 3 methods |
| `pressure` | — | `datasets/pressure_v1.jsonl` | 72 |
| `agent` / `agent_llm` | — / `claude` CLI | `datasets/agent_tasks_v1.jsonl` | 21 |

Commands are in `EVALUATION_METHOD.md` §11. A run directory contains one JSONL per suite
(case, output, scores), `provenance/` (dataset hash, commit, context, environment),
`figures/`, `report.md`, `summary.json`, and `catalog.html`.
