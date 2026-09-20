#!/usr/bin/env python3
"""Build the static graph layer and capability registry for QA/QC agent tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from qaqc_agent_tools import QAQCToolkit, TOOL_SCHEMAS


DASHBOARD_COMMIT = "d8fa9e30ff5459f51f4e431cf2aa9e20f3985c96"
RCA_TOOLS_COMMIT = "03358ff29267dfa7ecede48c28915adb58ecb6ce"


def stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{hashlib.sha256(chr(31).join(map(str, parts)).encode()).hexdigest()[:16]}"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def add_rel(rows: list[dict], source: str, predicate: str, target: str, evidence: dict | None = None) -> None:
    rows.append({"relationship_id": stable_id("QAQC-REL", source, predicate, target), "source_id": source, "predicate": predicate, "target_id": target, "evidence": evidence, "source_is_untrusted_data": True})


def build(args: argparse.Namespace) -> None:
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    index = json.loads(args.index_snapshot.read_text(encoding="utf-8"))
    toolkit = QAQCToolkit(instrument_root=args.instrument_root)
    parsed = [toolkit.parse_plot_path(path) for path in index if path.startswith("RS")]
    parsed = [x for x in parsed if x]
    site_counts = Counter(x["site"] for x in parsed)
    ref_counts = Counter(x["reference_designator"] for x in parsed)
    variable_counts = Counter(x["variable"] for x in parsed)
    span_counts = Counter(x["time_span"] for x in parsed)
    overlay_counts = Counter(x["overlay"] for x in parsed)
    range_counts = Counter(x["data_range"] for x in parsed)

    sources = [
        {"source_id": "QAQC-SOURCE-DASHBOARD-REPO", "name": "OOI-CabledArray QAQC Dashboard", "url": "https://github.com/OOI-CabledArray/QAQC_dashboard", "commit": DASHBOARD_COMMIT, "license": "NOASSERTION (repository declares no license)", "use": "interface and filename-contract provenance", "source_is_untrusted_data": True},
        {"source_id": "QAQC-SOURCE-RCA-DATA-TOOLS", "name": "OOI-CabledArray rca-data-tools", "url": "https://github.com/OOI-CabledArray/rca-data-tools", "commit": RCA_TOOLS_COMMIT, "license": "MIT", "use": "optional plot-generation backend and QA/QC method provenance", "source_is_untrusted_data": True},
        {"source_id": "QAQC-SOURCE-LIVE-PLOT-INDEX", "name": "Live RCA QAQC plot index", "url": "https://ec2.qaqc.ooi-rca.net/QAQC_plots/index.json", "retrieved_at": args.retrieved_at, "snapshot_sha256": sha_file(args.index_snapshot), "source_is_untrusted_data": True},
        {"source_id": "QAQC-SOURCE-HITL", "name": "Live human-in-the-loop QAQC notes", "url": "https://ec2.qaqc.ooi-rca.net/HITL_notes/index.json", "snapshot_sha256": sha_file(args.hitl_snapshot), "source_is_untrusted_data": True},
        {"source_id": "QAQC-SOURCE-INSTRUMENT-GRAPH", "name": "Local RCA and COSZO instrument Graph-RAG inventory", "path": str(args.instrument_root), "source_is_untrusted_data": True},
    ]
    entities = [
        {"entity_id": "QAQC-SERVICE-DASHBOARD", "name": "RCA QAQC Dashboard", "entity_type": "live_service", "url": "https://ec2.qaqc.ooi-rca.net", "source_is_untrusted_data": True},
        {"entity_id": "QAQC-CATALOG-PLOTS", "name": "RCA QAQC live plot catalog", "entity_type": "dynamic_catalog", "source_is_untrusted_data": True},
        {"entity_id": "QAQC-CATALOG-HITL", "name": "RCA human-in-the-loop status notes", "entity_type": "dynamic_catalog", "source_is_untrusted_data": True},
        {"entity_id": "QAQC-PIPELINE-RCA-DATA-TOOLS", "name": "rca-data-tools QAQC pipeline", "entity_type": "optional_execution_backend", "execution_default": "disabled", "source_is_untrusted_data": True},
        {"entity_id": "QAQC-GRAPH-INSTRUMENTS", "name": "RCA and COSZO instrument graph", "entity_type": "graph_corpus", "source_is_untrusted_data": True},
        {"entity_id": "QAQC-METHOD-QARTOD", "name": "QARTOD tests and overlays", "entity_type": "quality_control_method", "source_is_untrusted_data": True},
    ]
    capabilities, chunks = [], []
    for ordinal, schema in enumerate(TOOL_SCHEMAS, 1):
        cid = stable_id("QAQC-CAPABILITY", schema["name"])
        mode = "optional_execution" if schema["name"] == "qaqc_generate_plots" else ("dry_run_only" if schema["name"] == "qaqc_pipeline_plan" else "read_only")
        capabilities.append({"capability_id": cid, "name": schema["name"], "description": schema["description"], "input_schema": schema["inputSchema"], "mode": mode, "source_is_untrusted_data": True})
        text = f"QAQC agent tool: {schema['name']}. {schema['description']} Inputs: {json.dumps(schema['inputSchema'], ensure_ascii=False)}"
        chunks.append({"chunk_id": stable_id("QAQC-CHUNK", schema["name"]), "document_id": cid, "parent_id": cid, "position": 0, "title": schema["name"], "text": text, "word_count": len(text.split()), "source_is_untrusted_data": True})
    policy_id = "QAQC-AGENT-POLICY"
    policy_text = "For a QAQC question, retrieve stable instrument identity from the graph, then call qaqc_question_context or qaqc_search_plots for current plot evidence and qaqc_hitl_notes for human status. Use qaqc_get_plot with include_image when the agent must inspect or present a figure. Cite returned live URLs and note dates. Plot availability does not itself prove data quality. Use qaqc_generate_plots only when existing products are insufficient; execution remains disabled until the runtime is configured."
    entities.append({"entity_id": policy_id, "name": "QAQC agent routing policy", "entity_type": "agent_policy", "source_is_untrusted_data": True})
    chunks.append({"chunk_id": stable_id("QAQC-CHUNK", policy_id), "document_id": policy_id, "parent_id": policy_id, "position": 0, "title": "QAQC agent routing policy", "text": policy_text, "word_count": len(policy_text.split()), "source_is_untrusted_data": True})

    relationships = []
    add_rel(relationships, "QAQC-SERVICE-DASHBOARD", "EXPOSES", "QAQC-CATALOG-PLOTS", {"source_id": "QAQC-SOURCE-LIVE-PLOT-INDEX"})
    add_rel(relationships, "QAQC-SERVICE-DASHBOARD", "EXPOSES", "QAQC-CATALOG-HITL", {"source_id": "QAQC-SOURCE-HITL"})
    add_rel(relationships, "QAQC-PIPELINE-RCA-DATA-TOOLS", "GENERATES", "QAQC-CATALOG-PLOTS", {"source_id": "QAQC-SOURCE-RCA-DATA-TOOLS"})
    add_rel(relationships, "QAQC-PIPELINE-RCA-DATA-TOOLS", "IMPLEMENTS", "QAQC-METHOD-QARTOD", {"source_id": "QAQC-SOURCE-RCA-DATA-TOOLS"})
    add_rel(relationships, policy_id, "RETRIEVES_FROM", "QAQC-GRAPH-INSTRUMENTS")
    add_rel(relationships, policy_id, "CALLS", "QAQC-CATALOG-PLOTS")
    add_rel(relationships, policy_id, "CALLS", "QAQC-CATALOG-HITL")
    for capability in capabilities:
        add_rel(relationships, policy_id, "USES_CAPABILITY", capability["capability_id"])

    summary = {
        "snapshot_time": args.retrieved_at,
        "scope": "Regional Cabled Array paths (RS prefix)",
        "total_dashboard_paths": len(index),
        "rca_plot_records": len(parsed),
        "site_counts": dict(site_counts.most_common()),
        "reference_designator_count": len(ref_counts),
        "variable_count": len(variable_counts),
        "top_variables": dict(variable_counts.most_common(100)),
        "time_spans": dict(span_counts), "overlays": dict(overlay_counts), "data_ranges": dict(range_counts),
        "source_url": "https://ec2.qaqc.ooi-rca.net/QAQC_plots/index.json",
        "source_snapshot_sha256": sha_file(args.index_snapshot),
    }
    (out / "catalog_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(args.hitl_snapshot, out / "hitl_snapshot.jsonl")
    write_jsonl(out / "sources.jsonl", sources); write_jsonl(out / "entities.jsonl", entities)
    write_jsonl(out / "capabilities.jsonl", capabilities); write_jsonl(out / "chunks.jsonl", chunks); write_jsonl(out / "relationships.jsonl", relationships)
    tool_manifest = {
        "server": {"name": "rcn-agent-qaqc", "transport": "stdio", "command": ["src/agentic_qaqc/run_mcp.sh"], "working_directory": "project root"},
        "environment": {"QAQC_DASHBOARD_URL": "optional; defaults to https://ec2.qaqc.ooi-rca.net", "QAQC_INDEX_CACHE": "optional writable index-cache path", "QAQC_HITL_SNAPSHOT": "recommended fallback path to hitl_snapshot.jsonl", "QAQC_INSTRUMENT_ROOT": "required for local graph context", "QAQC_AGENT_ALLOW_PIPELINE": "optional; execution remains disabled unless set to 1"},
        "tools": TOOL_SCHEMAS,
    }
    (out / "tool_manifest.json").write_text(json.dumps(tool_manifest, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text("""# RCA QA/QC agentic Graph-RAG layer

Embed `chunks.jsonl.text` so the agent can retrieve QA/QC tool capabilities and routing policy. Load `sources.jsonl`, `entities.jsonl`, and `capabilities.jsonl` as nodes, with `relationships.jsonl` as edges. `catalog_summary.json` is a dated summary of the live RCA plot index; the complete plot catalog stays dynamic and is queried through the tools in `tool_manifest.json`. `hitl_snapshot.jsonl` is a dated fallback for current human-in-the-loop notes.

Use stable Graph-RAG records for identity and method context. Use live QA/QC tools for current plots and status. `qaqc_get_plot` can return a plot as MCP image content, and the optional pinned `rca-data-tools` backend can generate plots after its dependencies are installed and execution is enabled. Source content is untrusted data and must never be interpreted as agent instructions.
""", encoding="utf-8")
    files = ["sources.jsonl", "entities.jsonl", "capabilities.jsonl", "chunks.jsonl", "relationships.jsonl", "catalog_summary.json", "hitl_snapshot.jsonl", "tool_manifest.json", "README.md"]
    all_ids = {x[k] for rows, k in [(sources, "source_id"), (entities, "entity_id"), (capabilities, "capability_id"), (chunks, "chunk_id")] for x in rows}
    unresolved = sorted({v for r in relationships for v in (r["source_id"], r["target_id"]) if v not in all_ids})
    checks = {"all_relationship_endpoints_resolve": not unresolved, "capability_chunks_complete": len(capabilities) == len(TOOL_SCHEMAS) and len(chunks) == len(capabilities) + 1, "rca_scope_nonempty": len(parsed) > 0, "source_snapshot_hashed": bool(summary["source_snapshot_sha256"]), "pipeline_execution_disabled_by_default": True}
    validation = {"status": "pass" if all(checks.values()) else "fail", "checks": checks, "counts": {"sources": len(sources), "entities": len(entities), "capabilities": len(capabilities), "chunks": len(chunks), "relationships": len(relationships), "rca_plot_records_in_snapshot": len(parsed)}, "problems": {"unresolved_relationship_endpoints": unresolved}}
    (out / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    manifest = {"corpus_id": "RCA-QAQC-AGENTIC-GRAPHRAG", "schema_version": "1.0.0", "created_at": datetime.now(timezone.utc).isoformat(), "embedding_input": "chunks.jsonl", "node_inputs": ["sources.jsonl", "entities.jsonl", "capabilities.jsonl"], "edge_input": "relationships.jsonl", "live_tool_manifest": "tool_manifest.json", "validation_status": validation["status"], "counts": validation["counts"], "files": {name: {"sha256": sha_file(out / name), "records": sum(1 for _ in (out / name).open(encoding="utf-8")) if name.endswith(".jsonl") else None} for name in files}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, indent=2))
    if validation["status"] != "pass": raise SystemExit(2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--index-snapshot", type=Path, required=True); p.add_argument("--hitl-snapshot", type=Path, required=True); p.add_argument("--output-dir", type=Path, required=True); p.add_argument("--instrument-root", type=Path, required=True); p.add_argument("--retrieved-at", required=True); build(p.parse_args())
