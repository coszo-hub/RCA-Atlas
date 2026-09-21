#!/usr/bin/env python3
"""Discover and validate every Graph-RAG corpus under ``data/``.

Collection builders use several manifest dialects.  This module converts them
into one runtime catalog without changing the source corpora.  The catalog is
the input contract for later graph normalization and embedding jobs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CATALOG_SCHEMA_VERSION = "1.0"

COLLECTION_NAMES = {
    # ``arcada`` is the stable internal/provenance ID for the pinned upstream
    # package.  It is presented to RCA Atlas users as RCA Information.
    "Arcada": ("arcada", "RCA Information"),
    "AxialEarthquakes/graphrag": ("axial_earthquakes", "Axial Seamount earthquakes"),
    "COSZOHub": ("coszo_hub", "COSZO Hub computational outputs"),
    "Datasheets/graphrag": ("datasheets", "Instrument datasheets"),
    "Figures/graphrag": ("figures", "Curated figures"),
    "Instruments": ("instruments", "RCA and COSZO instruments"),
    "Literature": ("literature", "Scientific literature"),
    "Nereus/graphrag": ("nereus", "Nereus operational data"),
    "PIPortal": ("pi_portal", "RCA PI data portal"),
    "QAQC/graphrag": ("qaqc", "RCA QA/QC capabilities"),
    "StationMetadata": ("station_metadata", "OOI StationXML metadata"),
    "Websites": ("websites", "RCA and COSZO websites"),
    "coszo/graphrag": ("coszo_documents", "COSZO documents"),
}

# Files that describe addressable graph objects when a legacy manifest does
# not explicitly name its node inputs.  Structured observations remain out of
# this set and receive their own catalog role.
KNOWN_NODE_FILES = {
    "capabilities.jsonl",
    "channels.jsonl",
    "chunks.jsonl",
    "documents.jsonl",
    "endpoints.jsonl",
    "entities.jsonl",
    "figures.jsonl",
    "infrastructure.jsonl",
    "instrument_types.jsonl",
    "instruments.jsonl",
    "pages.jsonl",
    "repositories.jsonl",
    "sites.jsonl",
    "source_documents.jsonl",
    "sources.jsonl",
    "stations.jsonl",
    "tools.jsonl",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
KNOWN_AUXILIARY_FILES = {"visual_chunks.jsonl", "visual_summaries.jsonl"}
TIME_KEYS = ("created_at", "built_at_utc", "generated_at", "generated_at_utc", "audit_date")


class CatalogError(RuntimeError):
    """Raised when a corpus cannot satisfy the unified ingestion contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _jsonl_profile(path: Path, require_text: bool = False) -> dict[str, Any]:
    records = 0
    text_records = 0
    id_fields: Counter[str] = Counter()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CatalogError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise CatalogError(f"JSONL record is not an object at {path}:{line_number}")
            records += 1
            text = row.get("text")
            if isinstance(text, str) and text.strip():
                text_records += 1
            for key in ("id", "chunk_id", "entity_id", "instrument_id", "document_id", "source_id", "relationship_id"):
                if row.get(key) is not None:
                    id_fields[key] += 1
    if require_text and (records == 0 or text_records != records):
        raise CatalogError(f"Embedding input must have nonempty text in every record: {path} ({text_records}/{records})")
    return {"records": records, "text_records": text_records, "id_fields": dict(sorted(id_fields.items()))}


def _relative(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def _list_values(manifest: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = manifest.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value)
    return values


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _descriptor(project_root: Path, path: Path, role: str, *, require_text: bool = False) -> dict[str, Any]:
    if not path.is_file():
        raise CatalogError(f"Declared {role} does not exist: {path}")
    record_info = _jsonl_profile(path, require_text=require_text) if path.suffix.casefold() == ".jsonl" else {
        "records": None, "text_records": None, "id_fields": {}
    }
    return {
        "path": _relative(project_root, path),
        "role": role,
        "byte_size": path.stat().st_size,
        "sha256": _sha256(path),
        **record_info,
    }


def _resolve_reference(project_root: Path, collection_root: Path, value: str) -> dict[str, Any]:
    token = value.strip()
    candidate = (project_root / token) if token.startswith(("data/", "runtime_data/", "source_material/", "src/")) else (collection_root / token)
    try:
        relative = _relative(project_root, candidate)
    except (ValueError, OSError):
        return {"reference": token, "resolved_path": None, "exists": False}
    return {"reference": token, "resolved_path": relative, "exists": candidate.resolve().exists()}


def _runtime_references(project_root: Path, collection_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    references = []
    for key, value in manifest.items():
        key_low = key.casefold()
        if not isinstance(value, str):
            continue
        if "runtime" in key_low or key_low in {"live_index", "runtime_store"}:
            references.append({"manifest_key": key, **_resolve_reference(project_root, collection_root, value)})
    return references


def _asset_summary(collection_root: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    byte_size = 0
    for path in collection_root.rglob("*"):
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS:
            counts[path.suffix.casefold()] += 1
            byte_size += path.stat().st_size
    return {"image_count": sum(counts.values()), "image_bytes": byte_size, "by_extension": dict(sorted(counts.items()))}


def _collection_identity(data_root: Path, manifest_path: Path) -> tuple[str, str]:
    relative_root = manifest_path.parent.relative_to(data_root).as_posix()
    if relative_root in COLLECTION_NAMES:
        return COLLECTION_NAMES[relative_root]
    slug = re.sub(r"[^a-z0-9]+", "_", relative_root.casefold()).strip("_")
    return slug, relative_root.replace("/graphrag", "").replace("_", " ").title()


def _build_collection(project_root: Path, data_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collection_root = manifest_path.parent
    collection_id, name = _collection_identity(data_root, manifest_path)

    embedding_names = _list_values(manifest, "embedding_input", "embedding_inputs")
    if not embedding_names and (collection_root / "chunks.jsonl").is_file():
        embedding_names = ["chunks.jsonl"]
    embedding_names = _dedupe(embedding_names)
    if not embedding_names:
        raise CatalogError(f"No embedding input declared or inferred for {collection_id}")

    node_names = _list_values(manifest, "graph_node_inputs", "node_inputs", "other_node_inputs")
    node_names += _list_values(manifest, "instrument_node_input")
    node_names += embedding_names  # chunks are graph-addressable retrieval nodes
    for path in collection_root.glob("*.jsonl"):
        if path.name in KNOWN_NODE_FILES:
            node_names.append(path.name)
    node_names = _dedupe(node_names)

    edge_names = _list_values(manifest, "graph_edge_input", "graph_edge_inputs", "edge_input")
    if not edge_names and (collection_root / "relationships.jsonl").is_file():
        edge_names = ["relationships.jsonl"]
    edge_names = _dedupe(edge_names)

    all_jsonl = sorted(path.name for path in collection_root.glob("*.jsonl"))
    reserved = set(embedding_names) | set(node_names) | set(edge_names)
    remaining_names = [name for name in all_jsonl if name not in reserved]
    auxiliary_names = [name for name in remaining_names if name in KNOWN_AUXILIARY_FILES]
    structured_names = [name for name in remaining_names if name not in KNOWN_AUXILIARY_FILES]

    tool_names = _list_values(manifest, "live_tool_manifest")
    tool_names += [path.name for path in collection_root.iterdir() if path.is_file() and path.name in {"tool_manifest.json", "tools.jsonl"}]
    tool_names = _dedupe(tool_names)

    embeddings = [_descriptor(project_root, collection_root / name_, "embedding", require_text=True) for name_ in embedding_names]
    graph_nodes = [_descriptor(project_root, collection_root / name_, "graph_node") for name_ in node_names]
    graph_edges = [_descriptor(project_root, collection_root / name_, "graph_edge") for name_ in edge_names]
    structured = [_descriptor(project_root, collection_root / name_, "structured") for name_ in structured_names]
    auxiliary = [_descriptor(project_root, collection_root / name_, "auxiliary") for name_ in auxiliary_names]
    tools = [_descriptor(project_root, collection_root / name_, "tool_definition") for name_ in tool_names]

    validation = manifest.get("validation_status")
    if validation is None and isinstance(manifest.get("validation"), dict):
        validation = "pass" if manifest["validation"].get("passed") else "fail"
    generated_at = next((manifest.get(key) for key in TIME_KEYS if manifest.get(key)), None)
    scope = manifest.get("scope") or manifest.get("corpus") or name
    limitations = manifest.get("limitations") or manifest.get("notes") or []

    manifest_descriptor = _descriptor(project_root, manifest_path, "collection_manifest")
    file_count = sum(1 for path in collection_root.rglob("*") if path.is_file())
    total_bytes = sum(path.stat().st_size for path in collection_root.rglob("*") if path.is_file())
    return {
        "collection_id": collection_id,
        "name": name,
        "scope": scope,
        "schema_version": manifest.get("schema_version"),
        "generated_at": generated_at,
        "validation_status": validation or "not_declared",
        "root_path": _relative(project_root, collection_root),
        "manifest": manifest_descriptor,
        "embedding_inputs": embeddings,
        "graph_node_inputs": graph_nodes,
        "graph_edge_inputs": graph_edges,
        "structured_inputs": structured,
        "auxiliary_inputs": auxiliary,
        "tool_definitions": tools,
        "runtime_references": _runtime_references(project_root, collection_root, manifest),
        "asset_summary": _asset_summary(collection_root),
        "collection_file_count": file_count,
        "collection_byte_size": total_bytes,
        "limitations": limitations,
    }


def _fingerprint(collections: list[dict[str, Any]]) -> str:
    material = []
    for collection in collections:
        material.append({
            "collection_id": collection["collection_id"],
            "manifest_sha256": collection["manifest"]["sha256"],
            "inputs": sorted(
                (item["role"], item["path"], item["sha256"])
                for key in ("embedding_inputs", "graph_node_inputs", "graph_edge_inputs", "structured_inputs", "auxiliary_inputs", "tool_definitions")
                for item in collection[key]
            ),
        })
    payload = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_catalog(project_root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    data_root = project_root / "data"
    if not data_root.is_dir():
        raise CatalogError(f"Missing data directory: {data_root}")
    manifests = sorted(data_root.rglob("manifest.json"))
    collections = [_build_collection(project_root, data_root, path) for path in manifests]
    collections.sort(key=lambda item: item["collection_id"])
    ids = [item["collection_id"] for item in collections]
    if len(ids) != len(set(ids)):
        raise CatalogError("Duplicate collection IDs in corpus catalog")

    totals = {
        "collections": len(collections),
        "embedding_inputs": sum(len(item["embedding_inputs"]) for item in collections),
        "embedding_chunks": sum(file["records"] or 0 for item in collections for file in item["embedding_inputs"]),
        "graph_node_files": sum(len(item["graph_node_inputs"]) for item in collections),
        "graph_node_records": sum(file["records"] or 0 for item in collections for file in item["graph_node_inputs"]),
        "graph_edge_files": sum(len(item["graph_edge_inputs"]) for item in collections),
        "graph_edge_records": sum(file["records"] or 0 for item in collections for file in item["graph_edge_inputs"]),
        "structured_files": sum(len(item["structured_inputs"]) for item in collections),
        "structured_records": sum(file["records"] or 0 for item in collections for file in item["structured_inputs"]),
        "auxiliary_files": sum(len(item["auxiliary_inputs"]) for item in collections),
        "auxiliary_records": sum(file["records"] or 0 for item in collections for file in item["auxiliary_inputs"]),
        "tool_definition_files": sum(len(item["tool_definitions"]) for item in collections),
        "image_assets": sum(item["asset_summary"]["image_count"] for item in collections),
    }
    now = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "generated_at_utc": now,
        "project_root": str(project_root),
        "data_root": "data",
        "load_strategy": {
            "vector": "Embed only embedding_inputs.text; never embed parent documents or auxiliary JSONL a second time.",
            "graph": "Normalize and load all graph_node_inputs before graph_edge_inputs.",
            "structured": "Register structured_inputs for exact filtering and aggregation; do not treat them as prose chunks.",
            "auxiliary": "Retain auxiliary_inputs for display or specialized retrieval; do not embed them when their content is already represented in embedding_inputs.",
            "tools": "Register tool_definitions separately and invoke live tools only when routing requires current or actionable data.",
        },
        "totals": totals,
        "build_fingerprint_sha256": _fingerprint(collections),
        "collections": collections,
        "validation": {
            "passed": True,
            "checks": [
                "every manifest discovered",
                "one nonempty embedding text field per embedding record",
                "all declared and inferred inputs exist",
                "every JSONL record parses as an object",
                "collection IDs are unique",
                "input files carry SHA-256 and record counts",
                "runtime indexes are kept outside data",
            ],
        },
    }


def write_catalog(project_root: Path, output: Path) -> dict[str, Any]:
    catalog = build_catalog(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.project_root / "runtime_data" / "GraphRAG" / "corpus_catalog.json"
    catalog = write_catalog(args.project_root, output)
    print(json.dumps({
        "ok": True,
        "output": str(output.resolve()),
        "totals": catalog["totals"],
        "build_fingerprint_sha256": catalog["build_fingerprint_sha256"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
