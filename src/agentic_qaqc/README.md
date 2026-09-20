# Agentic QA/QC Graph-RAG integration

This integration joins stable Graph-RAG context with live RCA QA/QC evidence.

The graph layer describes the tools and their provenance. The runtime layer queries the current QAQC dashboard plot index and human-in-the-loop notes, resolves instruments through the local inventory, returns exact plot URLs or MCP image content, and can invoke a pinned `rca-data-tools` QAQC backend.

## Agent routing

For a QA/QC question:

1. Call `qaqc_question_context` with the user’s question. It combines instrument identity, current plot candidates, and current HITL notes.
2. Use `qaqc_search_plots` for narrower filtering. Call `qaqc_get_plot` with `include_image=true` when the agent must inspect or present a selected figure; use `output_path` to save it locally.
3. State the date recorded in HITL notes and cite returned live URLs. Plot existence does not prove a pass state.
4. Use `qaqc_pipeline_plan` to preview generation. Use `qaqc_generate_plots` only when existing products are insufficient. Its `execute` argument defaults to false, and execution also requires the runtime switch below.

## CLI

```bash
python3 qaqc_agent_tools.py \
  --instrument-root "/path/to/data/Instruments" \
  health

python3 qaqc_agent_tools.py \
  --instrument-root "/path/to/data/Instruments" \
  context "What is the QAQC status of RS01SLBS-MJ01A-12-VEL3DB101 this month?"
```

## MCP server

Run `src/agentic_qaqc/run_mcp.sh` from the project root as a stdio MCP server. The launcher derives the project paths automatically. They can be overridden with:

```text
QAQC_INSTRUMENT_ROOT=/path/to/data/Instruments
QAQC_INDEX_CACHE=/path/to/a/writable/qaqc-index.json
QAQC_HITL_SNAPSHOT=/path/to/data/QAQC/graphrag/hitl_snapshot.jsonl
QAQC_PYTHON=/path/to/python3
```

The server exposes ten tools documented in `data/QAQC/graphrag/tool_manifest.json`.

## Optional plot generation

The live lookup tools use only the Python standard library. A source snapshot of the MIT-licensed `rca-data-tools` QAQC package is pinned under `vendor/` with its license and upstream dependency manifest. Actual plot generation requires the packages in `requirements-generation.txt` plus OOI data access. Cloud runs or S3 synchronization additionally require Prefect configuration and AWS credentials. Execution is disabled by default; `QAQC_AGENT_ALLOW_PIPELINE=1` is required before `qaqc_generate_plots` can run. Call `qaqc_runtime_status` to inspect readiness.

Install generation dependencies into the agent environment with:

```bash
python3 -m pip install -r requirements-generation.txt
```

The QAQC dashboard repository does not currently declare a license. This integration therefore reimplements the documented filename contract and uses public HTTP interfaces rather than copying dashboard source.
