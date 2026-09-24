#!/usr/bin/env python3
"""Normalize the heterogeneous RCA/COSZO corpora into PostgreSQL load files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PRIMARY_ID_BY_FILE = {
    "capabilities.jsonl": "capability_id",
    "channels.jsonl": "channel_id",
    "chunks.jsonl": "chunk_id",
    "documents.jsonl": "document_id",
    "endpoints.jsonl": "endpoint_id",
    "entities.jsonl": "entity_id",
    "figures.jsonl": "figure_id",
    "infrastructure.jsonl": "infrastructure_id",
    "instruments.jsonl": "instrument_id",
    "observations.jsonl": "observation_id",
    "pages.jsonl": "page_id",
    "repositories.jsonl": "id",
    "sites.jsonl": "site_id",
    "source_documents.jsonl": "source_document_id",
    "sources.jsonl": "source_id",
    "stations.jsonl": "station_id",
    "tools.jsonl": "tool_id",
}

ID_FALLBACKS = (
    "id", "chunk_id", "entity_id", "document_id", "source_id", "source_document_id",
    "figure_id", "page_id", "instrument_id", "endpoint_id", "site_id", "tool_id",
    "capability_id", "station_id", "channel_id", "observation_id", "infrastructure_id",
)
EDGE_SOURCE_FIELDS = ("source_id", "from", "source_entity_id")
EDGE_TARGET_FIELDS = ("target_id", "to", "target_entity_id")
EDGE_PREDICATE_FIELDS = ("predicate", "relationship_type", "type")
EDGE_ID_FIELDS = ("relationship_id", "id", "edge_id")
DISPLAY_FIELDS = ("title", "name", "label", "filename", "channel")
ALIAS_FIELDS = (
    "aliases", "canonical_id", "shared_canonical_id", "all_known_shared_instrument_ids",
    "reference_designator", "instrument_id", "doi", "fdsn_id",
)
LINK_FIELDS = {
    "document_id": "DOCUMENT",
    "parent_id": "PARENT",
    "page_id": "PAGE",
    "source_id": "SOURCE",
    "source_ids": "SOURCE",
    "entity_id": "ENTITY",
    "entity_ids": "ENTITY",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def corpus_path(project_root: Path, relative: str) -> Path:
    path = (project_root / relative).resolve()
    try:
        path.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"Catalog path escapes project root: {relative}") from error
    if not path.is_file():
        raise ValueError(f"Catalog input is missing or not a file: {relative}")
    return path


def rows(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_no}")
            yield line_no, value


def first_value(record: dict[str, Any], fields: Iterable[str]) -> Any:
    for field in fields:
        value = record.get(field)
        if value is not None and value != "":
            return value
    return None


def first_string(value: Any) -> str | None:
    if isinstance(value, list):
        value = next((item for item in value if item is not None and str(item).strip()), None)
    return None if value is None else str(value)


def primary_id(collection_id: str, filename: str, record: dict[str, Any]) -> str:
    # The two corpora use `id` consistently for all addressable records.
    if collection_id == "coszo_hub":
        value = record.get("id")
    elif filename in {"tools.jsonl", "tool_manifest.json"}:
        # Tool names are stable identifiers and may be relationship endpoints
        # (for example, a PI-portal download tool ACCESSIBLE_WITH an endpoint).
        value = record.get("tool_id") or record.get("name")
    elif filename == "chunks.jsonl" and collection_id == "coszo_hub":
        value = record.get("id")
    elif filename == "source_documents.jsonl" and collection_id in {"arcada", "literature"}:
        value = record.get("source_document_id")
    elif filename == "instruments.jsonl" and collection_id == "pi_portal":
        value = record.get("instrument_id")
    else:
        value = record.get(PRIMARY_ID_BY_FILE.get(filename, ""))
    if value is None:
        value = first_value(record, ID_FALLBACKS)
    if value is None:
        raise ValueError(f"No primary ID for {collection_id}/{filename}: {record}")
    return str(value)


def edge_parts(record: dict[str, Any]) -> tuple[str, str, str, str | None]:
    source = first_value(record, EDGE_SOURCE_FIELDS)
    target = first_value(record, EDGE_TARGET_FIELDS)
    predicate = first_value(record, EDGE_PREDICATE_FIELDS)
    raw_id = first_value(record, EDGE_ID_FIELDS)
    if source is None or target is None or predicate is None:
        raise ValueError(f"Incomplete edge: {record}")
    return str(source), str(target), str(predicate), None if raw_id is None else str(raw_id)


def display_name(record: dict[str, Any], local_id: str) -> str:
    value = first_value(record, DISPLAY_FIELDS)
    return str(value) if value is not None else local_id


def aliases(record: dict[str, Any], local_id: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = [(local_id, "local_id")]
    for field in ALIAS_FIELDS:
        value = record.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is not None and str(item).strip():
                result.append((str(item).strip(), field))
    seen: set[tuple[str, str]] = set()
    return [item for item in result if not (item in seen or seen.add(item))]


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(canonical_json(value) + "\n")
            count += 1
    return count


def normalize(project_root: Path, catalog_path: Path, output: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    fingerprint = catalog["build_fingerprint_sha256"]
    # Use the full catalog digest. Truncating it would make independently built
    # snapshots share a database identity after a (however unlikely) prefix collision.
    build_id = fingerprint
    temp = output.with_name(output.name + ".building")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)

    collection_rows: list[dict[str, Any]] = []
    source_file_rows: list[dict[str, Any]] = []
    node_record_rows: list[dict[str, Any]] = []
    logical_nodes: dict[tuple[str, str], dict[str, Any]] = {}
    node_kinds: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    identifier_rows: set[tuple[str, str, str, str]] = set()
    chunk_rows: list[dict[str, Any]] = []
    chunk_link_rows: set[tuple[str, str, str, str]] = set()
    edge_record_rows: list[dict[str, Any]] = []
    edge_facts: set[tuple[str, str, str, str]] = set()
    structured_rows: list[dict[str, Any]] = []
    tool_rows: dict[tuple[str, str], dict[str, Any]] = {}

    for collection in catalog["collections"]:
        cid = collection["collection_id"]
        collection_rows.append({
            "build_id": build_id, "collection_id": cid, "name": collection["name"],
            "root_path": collection["root_path"], "scope": collection.get("scope"),
            "manifest": collection.get("manifest", {}),
        })
        embedding_paths = {item["path"] for item in collection["embedding_inputs"]}
        node_paths = {item["path"] for item in collection["graph_node_inputs"]}
        edge_paths = {item["path"] for item in collection["graph_edge_inputs"]}
        structured_paths = {item["path"] for item in collection.get("structured_inputs", [])}
        tool_paths = {item["path"] for item in collection.get("tool_definitions", [])}
        all_descriptors: dict[str, dict[str, Any]] = {}
        roles_by_path: defaultdict[str, set[str]] = defaultdict(set)
        for group in ("embedding_inputs", "graph_node_inputs", "graph_edge_inputs", "structured_inputs",
                      "auxiliary_inputs", "tool_definitions"):
            for item in collection.get(group, []):
                all_descriptors[item["path"]] = item
                roles_by_path[item["path"]].add(group.removesuffix("_inputs").removesuffix("_definitions"))
        for relative, descriptor in sorted(all_descriptors.items()):
            path = corpus_path(project_root, relative)
            file_id = f"{cid}:{relative}"
            actual_size = path.stat().st_size
            actual_sha256 = sha256_file(path)
            if actual_size != descriptor["byte_size"]:
                raise ValueError(
                    f"Catalog byte-size mismatch for {relative}: expected {descriptor['byte_size']}, got {actual_size}"
                )
            if actual_sha256 != descriptor["sha256"]:
                raise ValueError(
                    f"Catalog SHA-256 mismatch for {relative}: expected {descriptor['sha256']}, got {actual_sha256}"
                )
            if descriptor.get("records") is not None:
                if path.suffix != ".jsonl":
                    raise ValueError(f"Catalog declares record count for non-JSONL input: {relative}")
                actual_records = sum(1 for _ in rows(path))
                if actual_records != descriptor["records"]:
                    raise ValueError(
                        f"Catalog record-count mismatch for {relative}: expected {descriptor['records']}, got {actual_records}"
                    )
            source_file_rows.append({
                "build_id": build_id, "file_id": file_id, "collection_id": cid,
                "relative_path": relative, "roles": sorted(roles_by_path[relative]), "sha256": descriptor["sha256"],
                "byte_size": descriptor["byte_size"], "record_count": descriptor.get("records"),
            })
            if path.suffix == ".jsonl" and relative in node_paths:
                for line_no, record in rows(path):
                    local_id = primary_id(cid, path.name, record)
                    kind = path.stem
                    payload = canonical_json(record)
                    node_record_rows.append({
                        "build_id": build_id, "file_id": file_id, "line_no": line_no,
                        "collection_id": cid, "local_id": local_id, "record_kind": kind,
                        "payload_sha256": sha256_text(payload), "payload": record,
                        "source_is_untrusted_data": record.get("source_is_untrusted_data", True),
                    })
                    key = (cid, local_id)
                    node_kinds[key].add(kind)
                    if key not in logical_nodes:
                        logical_nodes[key] = {
                            "build_id": build_id, "collection_id": cid, "local_id": local_id,
                            "display_name": display_name(record, local_id), "summary": record.get("summary") or record.get("description"),
                            "source_url": record.get("source_url") or record.get("url"),
                            "representative_payload": record,
                        }
                    for alias, alias_type in aliases(record, local_id):
                        identifier_rows.add((cid, local_id, alias, alias_type))
                    if relative in embedding_paths:
                        text = str(record.get("text") or "").strip()
                        if not text:
                            raise ValueError(f"Blank embedding text at {relative}:{line_no}")
                        title = str(record.get("title") or logical_nodes[key]["display_name"])
                        chunk_rows.append({
                            "build_id": build_id, "collection_id": cid, "chunk_id": local_id,
                            "node_local_id": local_id, "title": title, "section_heading": record.get("section_heading"),
                            "body": text, "source_url": first_string(record.get("source_url") or record.get("source_urls")),
                            "locator": record.get("locator"), "text_sha256": sha256_text(text), "metadata": record,
                        })
                        for field, link_type in LINK_FIELDS.items():
                            value = record.get(field)
                            values = value if isinstance(value, list) else [value]
                            for target in values:
                                if target is not None and str(target) != local_id:
                                    chunk_link_rows.add((cid, local_id, link_type, str(target)))
            if path.suffix == ".jsonl" and relative in edge_paths:
                for line_no, record in rows(path):
                    source, target, predicate, raw_id = edge_parts(record)
                    payload = canonical_json(record)
                    edge_record_rows.append({
                        "build_id": build_id, "file_id": file_id, "line_no": line_no,
                        "collection_id": cid, "raw_edge_id": raw_id, "source_local_id": source,
                        "predicate": predicate, "target_local_id": target,
                        "payload_sha256": sha256_text(payload), "payload": record,
                    })
                    edge_facts.add((cid, source, predicate, target))
            if path.suffix == ".jsonl" and relative in structured_paths:
                for line_no, record in rows(path):
                    record_id = str(first_value(record, ID_FALLBACKS) or f"line:{line_no}")
                    structured_rows.append({
                        "build_id": build_id, "file_id": file_id, "line_no": line_no,
                        "collection_id": cid, "record_id": record_id,
                        "subject_id": first_value(record, ("subject_id", "entity_id", "station", "site_id", "reference_designator")),
                        "observed_at": first_value(record, ("observed_at", "time_utc", "date", "period_utc", "retrieved_at")),
                        "payload": record,
                    })
            if relative in tool_paths:
                if path.suffix == ".jsonl":
                    candidates = [record for _, record in rows(path)]
                else:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    candidates = loaded.get("tools", []) if isinstance(loaded, dict) else loaded
                for tool in candidates:
                    name = str(tool.get("name") or tool.get("id") or tool.get("tool_id"))
                    if not name:
                        continue
                    tool_rows[(cid, name)] = {
                        "build_id": build_id, "collection_id": cid, "name": name,
                        "description": tool.get("description") or tool.get("summary") or "",
                        "input_schema": tool.get("inputSchema") or tool.get("input_schema") or {},
                        "runtime": tool.get("runtime"), "manifest_path": relative, "metadata": tool,
                    }

    node_rows = []
    for key, row in sorted(logical_nodes.items()):
        row = dict(row)
        row["record_kinds"] = sorted(node_kinds[key])
        node_rows.append(row)

    node_keys = set(logical_nodes)
    unresolved_edges = [fact for fact in edge_facts if (fact[0], fact[1]) not in node_keys or (fact[0], fact[3]) not in node_keys]
    if unresolved_edges:
        raise ValueError(f"Unresolved edge endpoints: {unresolved_edges[:5]}")
    unresolved_chunk_links = [link for link in chunk_link_rows if (link[0], link[3]) not in node_keys]
    if unresolved_chunk_links:
        raise ValueError(f"Unresolved chunk links: {unresolved_chunk_links[:5]}")

    counts = {
        "collections": write_jsonl(temp / "collections.jsonl", collection_rows),
        "source_files": write_jsonl(temp / "source_files.jsonl", source_file_rows),
        "node_records": write_jsonl(temp / "node_records.jsonl", node_record_rows),
        "nodes": write_jsonl(temp / "nodes.jsonl", node_rows),
        "node_identifiers": write_jsonl(temp / "node_identifiers.jsonl", (
            {"build_id": build_id, "collection_id": c, "local_id": n, "identifier": a, "identifier_type": t}
            for c, n, a, t in sorted(identifier_rows)
        )),
        "chunks": write_jsonl(temp / "chunks.jsonl", chunk_rows),
        "chunk_links": write_jsonl(temp / "chunk_links.jsonl", (
            {"build_id": build_id, "collection_id": c, "chunk_id": ch, "link_type": lt, "target_local_id": target}
            for c, ch, lt, target in sorted(chunk_link_rows)
        )),
        "edge_records": write_jsonl(temp / "edge_records.jsonl", edge_record_rows),
        "edge_facts": write_jsonl(temp / "edge_facts.jsonl", (
            {"build_id": build_id, "collection_id": c, "source_local_id": s, "predicate": p, "target_local_id": t}
            for c, s, p, t in sorted(edge_facts)
        )),
        "structured_records": write_jsonl(temp / "structured_records.jsonl", structured_rows),
        "tools": write_jsonl(temp / "tools.jsonl", (tool_rows[key] for key in sorted(tool_rows))),
    }
    expected = catalog["totals"]
    assertions = {
        "collections_match": counts["collections"] == expected["collections"],
        "node_records_match": counts["node_records"] == expected["graph_node_records"],
        "chunks_match": counts["chunks"] == expected["embedding_chunks"],
        "edge_records_match": counts["edge_records"] == expected["graph_edge_records"],
        "structured_records_match": counts["structured_records"] == expected["structured_records"],
        "edge_endpoints_resolved": not unresolved_edges,
        "chunk_links_resolved": not unresolved_chunk_links,
    }
    if not all(assertions.values()):
        raise ValueError(f"Normalization validation failed: {assertions}; counts={counts}; expected={expected}")
    manifest = {
        "schema_version": "1.0", "build_id": build_id, "catalog_fingerprint_sha256": fingerprint,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "counts": counts,
        "assertions": assertions, "passed": True,
    }
    (temp / "build_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output.exists():
        shutil.rmtree(output)
    os.replace(temp, output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    catalog = args.catalog or args.project_root / "runtime_data/GraphRAG/corpus_catalog.json"
    output = args.output or args.project_root / "runtime_data/GraphRAG/normalized"
    result = normalize(args.project_root, catalog, output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
