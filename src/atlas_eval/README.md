# RCA Atlas evaluation harness

`atlas_eval` holds one eval set per RCA Atlas capability, a runner that records every case
with provenance, statistics with 95% intervals, and a report generator. The method write-up
is [`EVALUATION_METHOD.md`](EVALUATION_METHOD.md). The latest report is
[`results/2026-10-08-baseline/report.md`](results/2026-10-08-baseline/report.md).

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
(case, output, scores), `provenance/` (dataset hash, commit, context), `figures/`,
`report.md`, and `summary.json`.
