"""Convert Arcada's built RAG chunks into a validated Graph-RAG corpus."""
from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_URL = "https://github.com/mhemmett/arcada/"
KNOWN_SITES = [
    ("Regional Cabled Array", r"Regional Cabled Array|Regional Scale Nodes|\bRCA\b|\bRSN\b"),
    ("Axial Seamount", r"Axial (?:Seamount|Volcano|Caldera)"),
    ("Southern Hydrate Ridge", r"(?:Southern )?Hydrate Ridge"),
    ("Oregon Slope Base", r"(?:Oregon )?Slope Base"),
    ("COSZO", r"\bCOSZO\b|Cascadia Offshore Subduction Zone Observatory"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hid(prefix: str, value: str, length: int = 20) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def entity_id(name: str) -> str:
    """Match the Literature and Websites entity convention."""
    return "ENTITY-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def read_json(path: Path):
    return json.loads(path.read_text())


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def clean_text(value: str) -> str:
    value = value or ""
    if re.search(r"</?(?:p|div|span|sup|sub|em|strong|br|a|h[1-6])\b", value, re.I):
        value = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\x00", " ")
    lines = [" ".join(line.split()) for line in value.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def prepare_rows(raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep every source row while repairing the six placeholder-only duplicates."""
    grouped: dict[str, list[tuple[int, dict]]] = collections.defaultdict(list)
    for index, row in enumerate(raw_rows):
        grouped[row["id"]].append((index, row))
    prepared = []
    repairs = []
    for source_id, candidates in grouped.items():
        def score(item):
            index, row = item
            complete = sum(row.get(k) not in (None, "", []) for k in ("type", "source", "location", "keywords"))
            bad = 1 if "undefined" in (row.get("text") or "").casefold() else 0
            return (complete - bad * 20, len(row.get("text") or ""), -index)
        canonical_index, canonical = max(candidates, key=score)
        for index, row in candidates:
            copy = dict(row)
            copy["_source_row_index"] = index
            copy["_source_record_key"] = source_id if len(candidates) == 1 else f"{source_id}::source-row-{index}"
            copy["_original_metadata"] = {k: v for k, v in row.items() if k != "text"}
            copy["_source_text_sha256"] = hashlib.sha256((row.get("text") or "").encode()).hexdigest()
            if index != canonical_index and "undefined" in (row.get("text") or "").casefold():
                inferred_fields = []
                for key in ("type", "source", "location", "keywords", "fdsn_url", "pi_base_url", "ooi_page"):
                    if copy.get(key) in (None, "", []) and canonical.get(key) not in (None, "", []):
                        copy[key] = canonical[key]
                        inferred_fields.append(key)
                description = (
                    "Alternate Arcada catalog record for the same instrument. The source row supplied a distinct title "
                    "but no separate description; instrument details are carried by the canonical record in this document."
                )
                keywords = ", ".join(str(x) for x in (copy.get("keywords") or []))
                copy["text"] = "\n".join([
                    f"Name: {copy.get('title') or canonical.get('title') or source_id}",
                    f"Type: {copy.get('type') or 'instrument'}",
                    f"Location: {copy.get('location') or 'not specified'}",
                    f"Source: {copy.get('source') or 'Arcada catalog'}",
                    f"Description: {description}",
                    f"Keywords: {keywords}",
                ])
                copy["_repair"] = {
                    "reason": "placeholder_only_duplicate_source_row",
                    "canonical_source_row_index": canonical_index,
                    "inferred_fields": inferred_fields,
                    "original_text_sha256": hashlib.sha256((row.get("text") or "").encode()).hexdigest(),
                }
                repairs.append({
                    "source_row_index": index,
                    "source_chunk_id": source_id,
                    "reason": "placeholder_only_duplicate_source_row_repaired_and_retained",
                    "canonical_source_row_index": canonical_index,
                    "graph_source_record_key": copy["_source_record_key"],
                    "inferred_fields": inferred_fields,
                })
            prepared.append(copy)
    prepared.sort(key=lambda row: row["_source_row_index"])
    return prepared, repairs


def parent_key(row: dict) -> str:
    source_id = row["id"]
    if row.get("source") == "pdf":
        return re.sub(r"::chunk\d+$", "", source_id)
    return re.sub(r"::(?:desc|params)$", "", source_id)


def document_kind(row: dict) -> str:
    if row.get("type") == "paper":
        return "paper"
    if row.get("type") == "site-context":
        return "site_context"
    if row.get("type") == "script":
        return "data_access_guide"
    return "instrument"


def normalized_doi(row: dict) -> str | None:
    doi = (row.get("doi") or "").strip()
    if not doi and row.get("type") == "paper":
        match = re.match(r"paper::(10\.\d{4,9}/.+?)(?:::chunk\d+)?$", row.get("id", ""), re.I)
        if match:
            doi = match.group(1)
    return doi.lower() or None


def source_url(row: dict) -> str | None:
    for key in ("fdsn_url", "pi_base_url", "ooi_page"):
        if row.get(key):
            return row[key]
    doi = normalized_doi(row)
    return f"https://doi.org/{doi}" if doi else None


def chunk_sort_key(row: dict):
    match = re.search(r"::chunk(\d+)$", row["id"])
    if match:
        return (0, int(match.group(1)))
    if row["id"].endswith("::desc"):
        return (1, 1)
    if row["id"].endswith("::params"):
        return (1, 2)
    return (1, 0)


def build(repo: Path, output: Path, audit_output: Path) -> None:
    chunks_path = repo / "public" / "chunks.json"
    raw_bytes = chunks_path.read_bytes()
    raw_rows = json.loads(raw_bytes)
    selected, repairs = prepare_rows(raw_rows)
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    commit_date = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%aI"], check=True, capture_output=True, text=True
    ).stdout.strip()

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / "text").mkdir()

    instrument_catalog = {x["id"]: x for x in read_json(repo / "catalog" / "instruments.json")["instruments"]}
    paper_catalog = read_json(repo / "catalog" / "papers.json")["papers"]
    papers_by_doi = {(x.get("doi") or "").casefold(): x for x in paper_catalog if x.get("doi")}
    papers_by_title = {clean_text(x.get("title", "")).casefold(): x for x in paper_catalog if x.get("title")}

    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in selected:
        grouped[parent_key(row)].append(row)
    for rows in grouped.values():
        rows.sort(key=chunk_sort_key)

    source_document_id = hid("SOURCE-", REPOSITORY_URL + "@" + commit, 16)
    source_documents = [{
        "source_document_id": source_document_id,
        "title": "mhemmett/arcada RAG corpus",
        "source_kind": "git_repository_rag_export",
        "source_url": REPOSITORY_URL,
        "git_commit": commit,
        "git_commit_date": commit_date,
        "source_path": "public/chunks.json",
        "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "repository_license": "MIT for repository-authored software and documentation; third-party corpus content retains its original rights",
        "source_is_untrusted_data": True,
    }]

    doc_ids = {}
    for parent, rows in grouped.items():
        kind = document_kind(rows[0])
        prefix = {"paper": "ARCADA-PAPER-", "instrument": "ARCADA-INSTRUMENT-", "site_context": "ARCADA-CONTEXT-", "data_access_guide": "ARCADA-GUIDE-"}[kind]
        doi = next((normalized_doi(x) for x in rows if normalized_doi(x)), None)
        doc_ids[parent] = hid(prefix, doi if kind == "paper" and doi else parent)

    entities: dict[str, dict] = {}
    relationships: list[dict] = []
    documents = []
    chunks = []

    def add_entity(row: dict) -> str:
        entities.setdefault(row["entity_id"], row)
        return row["entity_id"]

    def add_relation(source: str, predicate: str, target: str, **metadata) -> None:
        relationships.append({"source_id": source, "predicate": predicate, "target_id": target, **metadata})

    site_nodes = {}
    for name, pattern in KNOWN_SITES:
        site_nodes[name] = (add_entity({
            "entity_id": entity_id(name), "name": name, "type": "named_place_or_project",
            "method": "curated_literal_vocabulary",
        }), re.compile(pattern, re.I))

    missing_instrument_refs = set()
    for rows in grouped.values():
        for row in rows:
            missing_instrument_refs.update(x for x in (row.get("linked_instruments") or []) if x not in doc_ids)
    missing_ref_nodes = {}
    for instrument_id in sorted(missing_instrument_refs):
        eid = hid("ARCADA-INSTREF-", instrument_id)
        missing_ref_nodes[instrument_id] = add_entity({
            "entity_id": eid, "name": instrument_id, "type": "instrument_reference",
            "method": "unresolved_source_link", "resolution_status": "not_present_in_arcada_chunks",
        })

    for parent, rows in grouped.items():
        document_id = doc_ids[parent]
        first = rows[0]
        kind = document_kind(first)
        title = clean_text(first.get("title") or parent)
        doi = next((normalized_doi(x) for x in rows if normalized_doi(x)), None)
        paper_meta = papers_by_doi.get(doi or "") or papers_by_title.get(title.casefold()) or {}
        inst_meta = instrument_catalog.get(parent, {}) if kind == "instrument" else {}
        location = first.get("location") or inst_meta.get("location")
        document_source_url = next((source_url(x) for x in rows if source_url(x)), None)
        linked_instruments = sorted({x for row in rows for x in (row.get("linked_instruments") or [])})
        keywords = sorted({str(x) for row in rows for x in (row.get("keywords") or []) if str(x).strip()}, key=str.casefold)
        assembled = "\n\n".join(clean_text(row.get("text", "")) for row in rows).strip() + "\n"
        text_path = f"text/{document_id}.md"
        (output / text_path).write_text(f"# {title}\n\n" + assembled)
        documents.append({
            "document_id": document_id,
            "source_document_id": source_document_id,
            "source_record_id": parent,
            "document_type": kind,
            "title": title,
            "instrument_type": first.get("type") if kind == "instrument" else None,
            "source_system": first.get("source"),
            "location": location,
            "latitude": inst_meta.get("latitude"),
            "longitude": inst_meta.get("longitude"),
            "depth_m": inst_meta.get("depth_m"),
            "site": inst_meta.get("site"),
            "node": inst_meta.get("node"),
            "instrument": inst_meta.get("instrument"),
            "stream": inst_meta.get("stream"),
            "units": inst_meta.get("units"),
            "sample_rate_hz": inst_meta.get("sample_rate_hz"),
            "start_date": inst_meta.get("start_date"),
            "end_date": inst_meta.get("end_date"),
            "doi": doi,
            "year": first.get("year") or paper_meta.get("year"),
            "journal": first.get("journal") or paper_meta.get("journal"),
            "first_author": first.get("first_author") or paper_meta.get("first_author"),
            "source_url": document_source_url,
            "keywords": keywords,
            "linked_instrument_ids": linked_instruments,
            "source_chunk_ids": [x["id"] for x in rows],
            "source_record_keys": [x["_source_record_key"] for x in rows],
            "text_path": text_path,
            "content_sha256": hashlib.sha256(assembled.encode()).hexdigest(),
            "repository_url": REPOSITORY_URL,
            "repository_commit": commit,
            "source_is_untrusted_data": True,
        })
        add_relation(document_id, "DERIVED_FROM", source_document_id, source_path="public/chunks.json", repository_commit=commit)

        type_name = first.get("type")
        if type_name:
            type_node = add_entity({
                "entity_id": entity_id(type_name), "name": type_name, "type": "arcada_content_type",
                "method": "source_metadata",
            })
            add_relation(document_id, "HAS_TYPE", type_node)
        if first.get("source"):
            source_name = first["source"]
            source_node = add_entity({
                "entity_id": entity_id(source_name), "name": source_name, "type": "data_source",
                "method": "source_metadata",
            })
            add_relation(document_id, "FROM_SOURCE", source_node)
        if location:
            location_node = add_entity({
                "entity_id": entity_id(location), "name": location, "type": "location",
                "method": "source_metadata",
            })
            add_relation(document_id, "LOCATED_AT", location_node)

        haystack = " ".join([title, location or "", assembled])
        for site_name, (site_id, pattern) in site_nodes.items():
            hit = pattern.search(haystack)
            if hit:
                add_relation(
                    document_id, "MENTIONS", site_id,
                    evidence=haystack[max(0, hit.start() - 80):hit.end() + 120].strip(), method="literal_name_match",
                )
        for instrument_id in linked_instruments:
            target = doc_ids.get(instrument_id) or missing_ref_nodes[instrument_id]
            add_relation(document_id, "LINKS_INSTRUMENT", target, source_instrument_id=instrument_id, method="source_metadata")

        for position, row in enumerate(rows):
            chunk_id = hid("ARCADA-CHUNK-", row["_source_record_key"])
            text = clean_text(row.get("text", ""))
            chunks.append({
                "chunk_id": chunk_id,
                "document_id": document_id,
                "parent_id": document_id,
                "source_chunk_id": row["id"],
                "source_record_key": row["_source_record_key"],
                "source_row_index": row["_source_row_index"],
                "source_row_repair": row.get("_repair"),
                "source_row_type": row.get("type"),
                "source_system": row.get("source"),
                "title": clean_text(row.get("title") or title),
                "position": position,
                "word_count": len(text.split()),
                "text": text,
                "location": row.get("location"),
                "keywords": row.get("keywords") or [],
                "source_url": source_url(row),
                "doi": normalized_doi(row) or doi,
                "year": row.get("year") or paper_meta.get("year"),
                "journal": row.get("journal") or paper_meta.get("journal"),
                "first_author": row.get("first_author") or paper_meta.get("first_author"),
                "linked_instrument_ids": row.get("linked_instruments") or [],
                "fdsn_url": row.get("fdsn_url"),
                "pi_base_url": row.get("pi_base_url"),
                "ooi_page": row.get("ooi_page"),
                "source_metadata_original": row["_original_metadata"],
                "source_text_sha256": row["_source_text_sha256"],
                "normalized_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "repository_url": REPOSITORY_URL,
                "repository_commit": commit,
                "source_is_untrusted_data": True,
            })
            add_relation(document_id, "HAS_CHUNK", chunk_id)
            if position:
                prior = hid("ARCADA-CHUNK-", rows[position - 1]["_source_record_key"])
                add_relation(prior, "NEXT_CHUNK", chunk_id)

    unique_relations = {json.dumps(x, sort_keys=True, ensure_ascii=False): x for x in relationships}
    relationships = list(unique_relations.values())
    entity_rows = sorted(entities.values(), key=lambda x: x["entity_id"])
    documents.sort(key=lambda x: x["document_id"])

    write_jsonl(output / "documents.jsonl", documents)
    write_jsonl(output / "chunks.jsonl", chunks)
    write_jsonl(output / "entities.jsonl", entity_rows)
    write_jsonl(output / "relationships.jsonl", relationships)
    write_jsonl(output / "source_documents.jsonl", source_documents)

    node_ids = {x["document_id"] for x in documents} | {x["chunk_id"] for x in chunks} | {x["entity_id"] for x in entity_rows} | {source_document_id}
    errors = []
    for label, ids in [
        ("document", [x["document_id"] for x in documents]),
        ("chunk", [x["chunk_id"] for x in chunks]),
        ("entity", [x["entity_id"] for x in entity_rows]),
    ]:
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate {label} ids")
    if len(raw_rows) != 802:
        errors.append(f"expected 802 source rows, found {len(raw_rows)}")
    if len(selected) != 802 or len(repairs) != 6:
        errors.append(f"expected 802 retained and 6 repaired rows, found {len(selected)} and {len(repairs)}")
    if hashlib.sha256(chunks_path.read_bytes()).hexdigest() != hashlib.sha256(raw_bytes).hexdigest():
        errors.append("source chunks changed during build")
    for relation in relationships:
        if relation["source_id"] not in node_ids:
            errors.append("dangling source " + relation["source_id"])
        if relation["target_id"] not in node_ids:
            errors.append("dangling target " + relation["target_id"])
    by_document = collections.defaultdict(list)
    for chunk in chunks:
        by_document[chunk["document_id"]].append(chunk)
        if not chunk["text"].strip():
            errors.append("empty chunk " + chunk["chunk_id"])
        if chunk["word_count"] != len(chunk["text"].split()):
            errors.append("word count mismatch " + chunk["chunk_id"])
        if "undefined" in chunk["text"].casefold():
            errors.append("undefined placeholder in " + chunk["chunk_id"])
        if re.search(r"</?(?:p|div|span|sup|sub|em|strong|br|a|h[1-6])\b", chunk["text"], re.I):
            errors.append("HTML tag remains in " + chunk["chunk_id"])
    for document in documents:
        positions = sorted(x["position"] for x in by_document[document["document_id"]])
        if positions != list(range(len(positions))):
            errors.append("non-contiguous chunk positions " + document["document_id"])
        path = output / document["text_path"]
        if not path.exists():
            errors.append("missing document text " + document["document_id"])
    for entity in entity_rows:
        if entity["entity_id"].startswith("ENTITY-") and entity["entity_id"] != entity_id(entity["name"]):
            errors.append("entity id mismatch " + entity["name"])

    validation = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "checks": [
            "source revision and SHA recorded", "all 802 source rows retained",
            "six placeholder-only duplicate rows repaired with an explicit audit trail",
            "unique namespaced node IDs", "relationship endpoint integrity",
            "every document has contiguous chunks", "nonempty normalized chunk text",
            "no undefined placeholders", "no HTML tags", "local text files exist",
            "website-compatible entity IDs", "unresolved instrument links represented as nodes",
        ],
    }
    (output / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n")
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps({
        "created_at": now(), "source_rows": len(raw_rows), "retained_rows": len(selected),
        "excluded_rows": [], "repaired_rows": repairs, "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }, indent=2) + "\n")
    if errors:
        raise RuntimeError("Validation failed: " + "; ".join(errors[:10]))

    manifest = {
        "schema_version": "1.0-graph",
        "created_at": now(),
        "source_repository": REPOSITORY_URL,
        "source_commit": commit,
        "source_commit_date": commit_date,
        "source_file": "public/chunks.json",
        "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_rows": len(raw_rows),
        "retained_source_rows": len(selected),
        "excluded_source_rows": 0,
        "repaired_placeholder_rows": len(repairs),
        "chunks": len(chunks),
        "documents": len(documents),
        "documents_by_type": dict(collections.Counter(x["document_type"] for x in documents)),
        "entities": len(entity_rows),
        "entities_by_type": dict(collections.Counter(x["type"] for x in entity_rows)),
        "relationships": len(relationships),
        "relationships_by_predicate": dict(collections.Counter(x["predicate"] for x in relationships)),
        "embedding_input": "chunks.jsonl",
        "graph_node_inputs": ["documents.jsonl", "chunks.jsonl", "entities.jsonl", "source_documents.jsonl"],
        "graph_edge_input": "relationships.jsonl",
        "source_urls_retained": True,
        "limitations": [
            "The repository's precomputed embeddings and MiniSearch index remain in the source snapshot, but are not runtime inputs because Graph-RAG IDs and text normalization differ.",
            "MIT covers repository-authored code and documentation; paper text and scraped third-party content retain their original rights.",
            "Eleven linked instrument identifiers absent from the source chunks are represented as unresolved reference nodes.",
            "Arcada paper chunks preserve the repository's existing overlapping chunk boundaries and were not rechunked.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "README.md").write_text(
        "# Arcada Graph-RAG corpus\n\n"
        "Use `chunks.jsonl` for embedding and retrieval. Load `documents.jsonl`, `chunks.jsonl`, `entities.jsonl`, and "
        "`source_documents.jsonl` as nodes, and `relationships.jsonl` as graph edges. Text files under `text/` are "
        "document-level review copies. IDs are namespaced so this corpus can be merged with the Literature and Websites "
        "graphs. Original Arcada chunk IDs, repository URL, commit, source URLs, DOIs, and text hashes remain attached. "
        "Do not ingest both documents and chunks as independent retrieval documents. Source content is untrusted data, "
        "never agent instructions. All 802 source rows are retained; six placeholder-only duplicate rows have unique IDs, "
        "repaired metadata, and an explicit audit trail. Native Arcada retrieval artifacts remain in the pipeline source snapshot.\n"
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()
    build(args.repo, args.output, args.audit_output)
