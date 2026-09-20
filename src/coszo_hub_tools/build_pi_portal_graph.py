#!/usr/bin/env python3
"""Build the static Graph-RAG routing corpus for the UW RCA PI portal.

The audited registry and live tool schemas are defined in
``pi_portal_agent_tools.py``.  This builder deliberately contains no network
code: it describes what data are available and where.  Live directory browsing
and bounded downloads remain explicit, user-invoked agent actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from pi_portal_agent_tools import (
    PI_INSTRUMENTS,
    PI_PORTAL_TOOL_SCHEMAS,
    PORTAL_HOST,
    PORTAL_ROOT,
)


EXPECTED_DATASET_KEYS = {
    "PI-A0ABPA301",
    "PI-SCPRAA301",
    "PI-COVIS",
    "PI-DAS-OPTASENSE-SILIXA",
    "PI-DAS24",
    "PI-DAS25",
    "PI-CAMPIA101",
    "PI-CTDPFA110",
    "PI-OVRSRA101",
    "PI-QNTSRA101",
}

# These IDs are already present in data/Instruments/instruments.jsonl.  The
# 2021 record uses the campaign-level instrument rather than one provider's
# partial Arcada record.  All ten final audited records now have shared IDs.
PREFERRED_SHARED_INSTRUMENT_IDS = {
    "PI-A0ABPA301": "INSTRUMENT-532da1331eb8530830",
    "PI-SCPRAA301": "INSTRUMENT-b1b4a4d854850f827d",
    "PI-COVIS": "INSTRUMENT-b1d858e0c31845d23e",
    "PI-DAS-OPTASENSE-SILIXA": "INSTRUMENT-981a1c15a947d3b1a1",
    "PI-DAS24": "INSTRUMENT-bf860ab80551b1f3c9",
    "PI-DAS25": "INSTRUMENT-8f08939e9167bac57c",
    "PI-CAMPIA101": "INSTRUMENT-1b4f79a7318105f747",
    "PI-CTDPFA110": "INSTRUMENT-cef8e76ca878e26b97",
    "PI-OVRSRA101": "INSTRUMENT-5d7ed7b890f1dcaead",
    "PI-QNTSRA101": "INSTRUMENT-833ab5c6a5f416bce0",
}

# Existing physical-location IDs from the shared Instruments graph.  Keeping
# distinct cable extents is useful: the 2021 campaign, DAS24, and DAS25 did not
# cover the same physical portion of the RCA fiber system.
SITE_DEFINITIONS = {
    "central-caldera": {
        "site_id": "ENTITY-d9e65f2c5695608",
        "name": "Axial Seamount Central Caldera",
        "aliases": ["Central Caldera, Axial Seamount", "RS03CCAL"],
        "latitude": 45.955,
        "longitude": -130.009,
    },
    "ashes": {
        "site_id": "ENTITY-d8299360a4fc5139",
        "name": "ASHES Hydrothermal Field, Axial Seamount",
        "aliases": ["ASHES", "RS03ASHS"],
        "latitude": 45.9337,
        "longitude": -130.0135,
    },
    "rca-fiber": {
        "site_id": "ENTITY-f8209671f3ebf6f3",
        "name": "RCA north and south fiber-optic cables",
        "aliases": ["RCA north and south backbone cables"],
        "latitude": None,
        "longitude": None,
    },
    "rca-south-to-repeater": {
        "site_id": "ENTITY-d1db038bfd5a8377",
        "name": "OOI Regional Cabled Array South Cable (shore to first optical repeater, ~95 km offshore)",
        "aliases": ["RCA south cable, shore to first repeater"],
        "latitude": None,
        "longitude": None,
    },
    "rca-full-cables": {
        "site_id": "ENTITY-f185063667dc9ed2",
        "name": "OOI Regional Cabled Array North and South Cables (full length)",
        "aliases": ["RCA north and south backbone cables"],
        "latitude": None,
        "longitude": None,
    },
    "hydrate-ridge-summit": {
        "site_id": "ENTITY-2227d074ea997677",
        "name": "Southern Hydrate Ridge Summit",
        "aliases": ["Summit-A vent, Southern Hydrate Ridge", "RS01SUM2"],
        "latitude": 44.5691,
        "longitude": -125.1479,
    },
}

SITE_KEY_BY_DATASET = {
    "PI-A0ABPA301": "central-caldera",
    "PI-SCPRAA301": "central-caldera",
    "PI-COVIS": "ashes",
    "PI-DAS-OPTASENSE-SILIXA": "rca-fiber",
    "PI-DAS24": "rca-south-to-repeater",
    "PI-DAS25": "rca-full-cables",
    "PI-CAMPIA101": "hydrate-ridge-summit",
    "PI-CTDPFA110": "hydrate-ridge-summit",
    "PI-OVRSRA101": "hydrate-ridge-summit",
    "PI-QNTSRA101": "hydrate-ridge-summit",
}

INSTRUMENT_TYPES = {
    "PI-A0ABPA301": "self_calibrating_pressure_sensor",
    "PI-SCPRAA301": "self_calibrating_pressure_recorder",
    "PI-COVIS": "sonar",
    "PI-DAS-OPTASENSE-SILIXA": "distributed_fiber_sensing_experiment",
    "PI-DAS24": "distributed_acoustic_sensing_experiment",
    "PI-DAS25": "distributed_acoustic_sensing_experiment",
    "PI-CAMPIA101": "camera",
    "PI-CTDPFA110": "ctd_dissolved_oxygen",
    "PI-OVRSRA101": "sonar",
    "PI-QNTSRA101": "sonar",
}

RCA_ENTITY = {
    "entity_id": "ENTITY-7b20fdc48eca4ee8",
    "name": "Regional Cabled Array",
    "entity_type": "observatory",
    "method": "shared_corpus_entity",
}

ROUTING_POLICY_ID = "PI-PORTAL-POLICY-STATIC-FIRST"
GRAPH_FILES = (
    "instruments.jsonl",
    "endpoints.jsonl",
    "sites.jsonl",
    "sources.jsonl",
    "tools.jsonl",
    "entities.jsonl",
    "relationships.jsonl",
    "chunks.jsonl",
)


def _stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:length]}"


def _slug(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return token or "unnamed"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _default_instrument_corpus() -> Path | None:
    configured = os.getenv("RCN_INSTRUMENT_CORPUS")
    candidates = [Path(configured)] if configured else []
    project = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            project / "data" / "Instruments" / "instruments.jsonl",
            Path.cwd() / "data" / "Instruments" / "instruments.jsonl",
        ]
    )
    return next((path for path in candidates if path.exists()), None)


def _resolve_instrument_ids(instrument_corpus: Path | None) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    rows = _load_jsonl(instrument_corpus)
    by_id = {row["instrument_id"]: row for row in rows if row.get("instrument_id")}
    # The audited registry is the crosswalk authority.  A supplied local
    # corpus enriches records but must not make stable shared IDs disappear
    # merely because that local snapshot predates the latest crosswalk.
    resolved = dict(PREFERRED_SHARED_INSTRUMENT_IDS)
    for key, dataset in PI_INSTRUMENTS.items():
        if key not in resolved:
            candidates = [item for item in dataset.get("existing_instrument_ids", []) if item]
            if candidates:
                resolved[key] = candidates[0]
    return resolved, by_id


def _endpoint_node_id(endpoint: dict[str, Any]) -> str:
    return _stable_id("PI-PORTAL-ENDPOINT", endpoint["url"])


def _tool_node_id(name: str) -> str:
    return f"PI-PORTAL-TOOL-{_slug(name).upper()}"


def _source_node_id(url_or_path: str) -> str:
    return _stable_id("PI-PORTAL-SOURCE", url_or_path)


def _edge(source_id: str, predicate: str, target_id: str, evidence_source_ids: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    row = {
        "relationship_id": _stable_id("PI-PORTAL-REL", source_id, predicate, target_id),
        "source_id": source_id,
        "predicate": predicate,
        "target_id": target_id,
        "evidence_source_ids": evidence_source_ids or [],
        "source_is_untrusted_data": True,
    }
    row.update(extra)
    return row


def _canonical_format_list(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _source_records(instrument_corpus: Path | None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    sources: list[dict[str, Any]] = []
    ids: dict[str, str] = {}

    portal_id = _source_node_id(PORTAL_ROOT)
    sources.append(
        {
            "source_id": portal_id,
            "title": "Audited UW RCA Principal Investigator data portal",
            "source_kind": "public_directory_service",
            "source_url": PORTAL_ROOT,
            "host": PORTAL_HOST,
            "role": "Authoritative public file-distribution host for the audited RCA PI datasets.",
            "audit_date": "2026-09-19",
            "source_is_untrusted_data": True,
        }
    )
    ids["portal"] = portal_id

    corpus_locator = str(instrument_corpus) if instrument_corpus else "../Instruments/instruments.jsonl"
    corpus_id = _source_node_id("shared-instruments-corpus")
    sources.append(
        {
            "source_id": corpus_id,
            "title": "Shared RCA and COSZO Instruments corpus",
            "source_kind": "local_graph_corpus",
            "source_path": corpus_locator,
            "role": "Supplies reusable instrument and physical-location node identities.",
            "source_is_untrusted_data": True,
        }
    )
    ids["instrument_corpus"] = corpus_id

    official: dict[str, list[str]] = {}
    for key, dataset in PI_INSTRUMENTS.items():
        official.setdefault(dataset["official_url"], []).append(key)
    for url in sorted(official):
        source_id = _source_node_id(url)
        keys = sorted(official[url])
        sources.append(
            {
                "source_id": source_id,
                "title": "Official OOI PI information: " + ", ".join(keys),
                "source_kind": "official_ooi_page",
                "source_url": url,
                "host": urlparse(url).hostname,
                "publisher": "Ocean Observatories Initiative",
                "dataset_keys": keys,
                "role": "Official context for the PI instrument or experiment.",
                "source_is_untrusted_data": True,
            }
        )
        ids[url] = source_id
    return sources, ids


def _instrument_chunk(record: dict[str, Any], endpoints: list[dict[str, Any]], site: dict[str, Any]) -> str:
    routes = "; ".join(f"{item['label']} ({item['url']})" for item in endpoints)
    formats = ", ".join(record["formats"])
    aliases = ", ".join(record["aliases"]) or "none recorded"
    caveats = " ".join(record["caveats"]) if record["caveats"] else "No additional caveat was recorded."
    return (
        f"Data for {record['name']} are available to download from {routes}. "
        f"Physical site: {record['physical_site']} (canonical graph site: {site['name']}; "
        f"OOI site {record.get('ooi_site') or 'not applicable'}, node {record.get('node') or 'not applicable'}). "
        f"Available formats: {formats}. Directory layout: {record['observed_layout']}; "
        f"audited path pattern: {record['path_pattern']}. Aliases: {aliases}. "
        f"Caveats: {caveats} Official OOI context: {record['official_url']}"
    )


def _validate(
    instruments: list[dict[str, Any]],
    endpoints: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    failures: list[str] = []
    if set(PI_INSTRUMENTS) != EXPECTED_DATASET_KEYS:
        failures.append("registry must contain exactly the ten audited logical datasets")
    if len(instruments) != 10:
        failures.append("instruments.jsonl must contain exactly ten records")

    node_ids: set[str] = set()
    node_groups = [
        (instruments, "instrument_id"),
        (endpoints, "endpoint_id"),
        (sites, "site_id"),
        (sources, "source_id"),
        (tools, "tool_id"),
        (entities, "entity_id"),
        (chunks, "chunk_id"),
    ]
    for rows, key in node_groups:
        for row in rows:
            identifier = row.get(key)
            if not identifier:
                failures.append(f"missing {key}")
            elif identifier in node_ids:
                failures.append(f"duplicate graph node ID: {identifier}")
            else:
                node_ids.add(identifier)

    relation_ids: set[str] = set()
    for row in relationships:
        rid = row.get("relationship_id")
        if rid in relation_ids:
            failures.append(f"duplicate relationship ID: {rid}")
        relation_ids.add(rid)
        if row.get("source_id") not in node_ids:
            failures.append(f"dangling relationship source: {row.get('source_id')}")
        if row.get("target_id") not in node_ids:
            failures.append(f"dangling relationship target: {row.get('target_id')}")

    by_instrument = {row["instrument_id"]: row for row in instruments}
    predicates = {(row["source_id"], row["predicate"], row["target_id"]) for row in relationships}
    chunks_by_parent = {row["parent_id"]: row for row in chunks if row.get("content_kind") == "instrument_download_routing"}
    endpoint_by_id = {row["endpoint_id"]: row for row in endpoints}
    for instrument_id, instrument in by_instrument.items():
        if instrument_id not in chunks_by_parent:
            failures.append(f"instrument lacks routing chunk: {instrument_id}")
        if not any(src == instrument_id and pred == "DOWNLOADABLE_FROM" for src, pred, _ in predicates):
            failures.append(f"instrument lacks DOWNLOADABLE_FROM: {instrument_id}")
        if not any(src == instrument_id and pred == "LOCATED_AT" for src, pred, _ in predicates):
            failures.append(f"instrument lacks LOCATED_AT: {instrument_id}")
        chunk = chunks_by_parent.get(instrument_id, {})
        text = chunk.get("text", "")
        if not text.startswith("Data for ") or "available to download from" not in text:
            failures.append(f"instrument chunk has wrong opening: {instrument_id}")
        for endpoint_id in instrument["endpoint_ids"]:
            endpoint = endpoint_by_id[endpoint_id]
            if endpoint["url"] not in text or endpoint["label"] not in text:
                failures.append(f"instrument chunk omits endpoint: {instrument_id}/{endpoint_id}")

    for endpoint in endpoints:
        parsed = urlparse(endpoint["url"])
        if parsed.hostname != PORTAL_HOST or parsed.scheme not in {"http", "https"}:
            failures.append(f"endpoint outside approved host: {endpoint['url']}")

    undefined = re.compile(r"\bundefined\b", re.I)
    for row in [*instruments, *endpoints, *sites, *sources, *tools, *entities, *relationships, *chunks]:
        if undefined.search(json.dumps(row, ensure_ascii=False)):
            failures.append("undefined placeholder present")
            break

    if failures:
        raise ValueError("PI portal Graph-RAG validation failed:\n- " + "\n- ".join(failures))
    return {
        "passed": True,
        "checks": [
            "exactly ten audited logical datasets",
            "unique deterministic graph node and relationship IDs",
            "all relationship endpoints resolve",
            "every instrument has DOWNLOADABLE_FROM, LOCATED_AT, and a routing chunk",
            "every instrument chunk opens with named download URLs",
            "all endpoints use the approved PI portal host",
            "no undefined placeholders",
        ],
    }


def build(output_dir: Path, instrument_corpus: Path | None = None) -> dict[str, Any]:
    if set(PI_INSTRUMENTS) != EXPECTED_DATASET_KEYS:
        missing = sorted(EXPECTED_DATASET_KEYS - set(PI_INSTRUMENTS))
        extra = sorted(set(PI_INSTRUMENTS) - EXPECTED_DATASET_KEYS)
        raise ValueError(f"PI registry mismatch; missing={missing}, extra={extra}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    instrument_corpus = instrument_corpus or _default_instrument_corpus()
    resolved_ids, shared_rows = _resolve_instrument_ids(instrument_corpus)
    sources, source_ids = _source_records(instrument_corpus)

    sites = []
    used_site_keys = sorted(set(SITE_KEY_BY_DATASET.values()))
    site_records: dict[str, dict[str, Any]] = {}
    for site_key in used_site_keys:
        definition = SITE_DEFINITIONS[site_key]
        members = sorted(key for key, value in SITE_KEY_BY_DATASET.items() if value == site_key)
        row = {
            **definition,
            "site_key": site_key,
            "entity_type": "physical_site",
            "dataset_keys": members,
            "external_dataset": "../Instruments/entities.jsonl",
            "source_is_untrusted_data": True,
        }
        sites.append(row)
        site_records[site_key] = row

    endpoints: list[dict[str, Any]] = []
    instruments: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for key in sorted(PI_INSTRUMENTS):
        dataset = PI_INSTRUMENTS[key]
        shared_id = resolved_ids.get(key)
        instrument_id = shared_id or _stable_id("PI-PORTAL-INSTRUMENT", key)
        site_key = SITE_KEY_BY_DATASET[key]
        site = site_records[site_key]
        endpoint_ids = []
        endpoint_rows = []
        for endpoint in dataset["endpoints"]:
            endpoint_id = _endpoint_node_id(endpoint)
            endpoint_ids.append(endpoint_id)
            endpoint_row = {
                "endpoint_id": endpoint_id,
                "endpoint_key": endpoint["endpoint_id"],
                "instrument_id": instrument_id,
                "instrument_key": key,
                "label": endpoint["label"],
                "url": endpoint["url"],
                "host": urlparse(endpoint["url"]).hostname,
                "scheme": urlparse(endpoint["url"]).scheme,
                "role": endpoint["role"],
                "formats": _canonical_format_list(endpoint["formats"]),
                "path_pattern": endpoint.get("path_pattern", dataset["path_pattern"]),
                "public": True,
                "credentials_required": False,
                "source_is_untrusted_data": True,
            }
            endpoints.append(endpoint_row)
            endpoint_rows.append(endpoint_row)

        shared_row = shared_rows.get(shared_id, {}) if shared_id else {}
        instrument = {
            "instrument_id": instrument_id,
            "portal_instrument_key": key,
            "canonical_id": dataset.get("canonical_id", key),
            "shared_canonical_id": shared_row.get("canonical_id"),
            "name": dataset["name"],
            "instrument_type": INSTRUMENT_TYPES[key],
            "aliases": list(dataset["aliases"]),
            "physical_site": dataset["site"],
            "site_id": site["site_id"],
            "ooi_site": dataset.get("ooi_site"),
            "node": dataset.get("node"),
            "depth_m": dataset.get("depth_m"),
            "formats": _canonical_format_list(dataset["formats"]),
            "path_pattern": dataset["path_pattern"],
            "observed_layout": dataset["observed_layout"],
            "caveats": list(dataset.get("caveats", [])),
            "official_url": dataset["official_url"],
            "portal_status": dataset["portal_status"],
            "endpoint_ids": endpoint_ids,
            "shared_instrument_id_reused": shared_id is not None,
            "all_known_shared_instrument_ids": list(dataset.get("existing_instrument_ids", [])),
            "external_dataset": "../Instruments/instruments.jsonl" if shared_id else None,
            "source_is_untrusted_data": True,
        }
        instruments.append(instrument)

        official_source_id = source_ids[dataset["official_url"]]
        for endpoint_row in endpoint_rows:
            relationships.append(_edge(instrument_id, "DOWNLOADABLE_FROM", endpoint_row["endpoint_id"], [source_ids["portal"]]))
            relationships.append(_edge(endpoint_row["endpoint_id"], "HOSTED_BY", source_ids["portal"], [source_ids["portal"]]))
        relationships.extend(
            [
                _edge(instrument_id, "LOCATED_AT", site["site_id"], [source_ids["instrument_corpus"], official_source_id]),
                _edge(instrument_id, "DOCUMENTED_BY", official_source_id, [official_source_id]),
                _edge(instrument_id, "PART_OF", RCA_ENTITY["entity_id"], [official_source_id]),
            ]
        )
        chunk_id = _stable_id("PI-PORTAL-CHUNK", instrument_id, "download-routing")
        chunks.append(
            {
                "chunk_id": chunk_id,
                "parent_id": instrument_id,
                "document_id": instrument_id,
                "position": 0,
                "title": f"{dataset['name']} data availability and routing",
                "content_kind": "instrument_download_routing",
                "text": _instrument_chunk(instrument, endpoint_rows, site),
                "word_count": 0,
                "source_ids": [source_ids["portal"], official_source_id, source_ids["instrument_corpus"]],
                "source_urls": [endpoint["url"] for endpoint in endpoint_rows] + [dataset["official_url"]],
                "source_is_untrusted_data": True,
            }
        )
        chunks[-1]["word_count"] = len(chunks[-1]["text"].split())
        relationships.append(_edge(instrument_id, "HAS_CHUNK", chunk_id, chunks[-1]["source_ids"]))

    tools: list[dict[str, Any]] = []
    schema_by_name = {schema["name"]: schema for schema in PI_PORTAL_TOOL_SCHEMAS}
    live_browse_names = {"pi_portal_browse", "pi_portal_find_files"}
    planning_names = {"pi_portal_plan_download"}
    download_names = {"pi_portal_download_files"}
    user_invoked_names = live_browse_names | planning_names | download_names
    for schema in PI_PORTAL_TOOL_SCHEMAS:
        name = schema["name"]
        if name in live_browse_names:
            mode = "live_browse"
        elif name in download_names:
            mode = "live_download"
        elif name in planning_names:
            mode = "download_plan"
        else:
            mode = "static_registry"
        tool = {
            "tool_id": _tool_node_id(name),
            "name": name,
            "description": schema["description"],
            "input_schema": schema["inputSchema"],
            "mode": mode,
            "runtime": "src/coszo_hub_tools/pi_portal_agent_tools.py",
            "requires_user_invocation_after_corpus_answer": name in user_invoked_names,
            "approved_host": PORTAL_HOST,
            "writes_only_to_runtime_data": name in download_names,
            "source_is_untrusted_data": True,
        }
        tools.append(tool)
        chunk_id = _stable_id("PI-PORTAL-CHUNK", tool["tool_id"], "tool")
        text = (
            f"Agent tool {name}: {schema['description']} Mode: {mode}. "
            f"This tool is invoked after the static corpus answer when the user asks to browse, plan, find, or download current files. "
            f"Input schema: {json.dumps(schema['inputSchema'], ensure_ascii=False, sort_keys=True)}"
        )
        chunks.append(
            {
                "chunk_id": chunk_id,
                "parent_id": tool["tool_id"],
                "document_id": tool["tool_id"],
                "position": 0,
                "title": name,
                "content_kind": "agent_tool",
                "text": text,
                "word_count": len(text.split()),
                "source_ids": [source_ids["portal"]],
                "source_urls": [PORTAL_ROOT],
                "source_is_untrusted_data": True,
            }
        )
        relationships.append(_edge(tool["tool_id"], "HAS_CHUNK", chunk_id, [source_ids["portal"]]))

    entities = [
        RCA_ENTITY,
        {
            "entity_id": ROUTING_POLICY_ID,
            "name": "PI portal corpus-first routing policy",
            "entity_type": "routing_policy",
            "policy": "Answer availability from the static corpus first. Only after that response, invoke live tools when the user asks to browse, find, plan, or download current portal files.",
            "requires_user_invocation_for_live_actions": True,
        },
    ]

    for endpoint in endpoints:
        for tool_name in sorted(live_browse_names | planning_names | download_names):
            tool_id = _tool_node_id(tool_name)
            relationships.append(_edge(endpoint["endpoint_id"], "ACCESSIBLE_WITH", tool_id, [source_ids["portal"]]))
        for tool_name in sorted(live_browse_names):
            relationships.append(_edge(_tool_node_id(tool_name), "BROWSES", endpoint["endpoint_id"], [source_ids["portal"]]))
        for tool_name in sorted(planning_names):
            relationships.append(_edge(_tool_node_id(tool_name), "PLANS_DOWNLOAD_FROM", endpoint["endpoint_id"], [source_ids["portal"]]))
        for tool_name in sorted(download_names):
            relationships.append(_edge(_tool_node_id(tool_name), "DOWNLOADS_FROM", endpoint["endpoint_id"], [source_ids["portal"]]))

    for tool_name in sorted(user_invoked_names):
        relationships.append(
            _edge(
                ROUTING_POLICY_ID,
                "USE_CORPUS_FIRST_THEN_INVOKE_TOOL",
                _tool_node_id(tool_name),
                [source_ids["portal"]],
                requires_user_invocation=True,
            )
        )
    for source in sources:
        relationships.append(_edge(ROUTING_POLICY_ID, "PREFERS_STATIC_SOURCE", source["source_id"], [source["source_id"]]))

    source_names = "; ".join(
        f"{source['title']} ({source.get('source_url') or source.get('source_path')})" for source in sources
    )
    endpoint_names = "; ".join(f"{endpoint['label']} ({endpoint['url']})" for endpoint in endpoints)
    policy_text = (
        "Routing policy: use the static corpus first to answer whether PI data exist, where they are available, their physical site, formats, layout, aliases, and caveats. "
        f"Static sources: {source_names}. Audited download endpoints: {endpoint_names}. "
        "Live tools are only for user-invoked browsing, file discovery, download planning, or bounded downloading after the corpus response. "
        "Do not browse or download merely to answer availability already represented in the corpus. Downloaded files belong in runtime_data/PIPortal and are runtime evidence, not static Graph-RAG input."
    )
    policy_chunk_id = _stable_id("PI-PORTAL-CHUNK", ROUTING_POLICY_ID, "routing-policy")
    chunks.append(
        {
            "chunk_id": policy_chunk_id,
            "parent_id": ROUTING_POLICY_ID,
            "document_id": ROUTING_POLICY_ID,
            "position": 0,
            "title": "PI portal corpus-first routing policy",
            "content_kind": "routing_policy",
            "text": policy_text,
            "word_count": len(policy_text.split()),
            "source_ids": [source["source_id"] for source in sources],
            "source_urls": [source["source_url"] for source in sources if source.get("source_url")],
            "source_is_untrusted_data": True,
        }
    )
    relationships.append(_edge(ROUTING_POLICY_ID, "HAS_CHUNK", policy_chunk_id, chunks[-1]["source_ids"]))

    instruments.sort(key=lambda row: row["portal_instrument_key"])
    endpoints.sort(key=lambda row: (row["instrument_key"], row["endpoint_key"]))
    sites.sort(key=lambda row: row["site_id"])
    sources.sort(key=lambda row: row["source_id"])
    tools.sort(key=lambda row: row["name"])
    entities.sort(key=lambda row: row["entity_id"])
    relationships.sort(key=lambda row: (row["source_id"], row["predicate"], row["target_id"]))
    chunks.sort(key=lambda row: (row["content_kind"], row["parent_id"], row["position"]))

    validation = _validate(instruments, endpoints, sites, sources, tools, entities, relationships, chunks)
    for filename, rows in [
        ("instruments.jsonl", instruments),
        ("endpoints.jsonl", endpoints),
        ("sites.jsonl", sites),
        ("sources.jsonl", sources),
        ("tools.jsonl", tools),
        ("entities.jsonl", entities),
        ("relationships.jsonl", relationships),
        ("chunks.jsonl", chunks),
    ]:
        _write_jsonl(output_dir / filename, rows)

    predicate_counts = Counter(row["predicate"] for row in relationships)
    manifest = {
        "schema_version": "1.0-graph",
        "corpus": "UW RCA PI portal availability and download routing",
        "audit_date": "2026-09-19",
        "deterministic_build": True,
        "scope": "Exactly ten audited logical RCA PI datasets",
        "instrument_count": len(instruments),
        "instrument_keys": [row["portal_instrument_key"] for row in instruments],
        "endpoint_count": len(endpoints),
        "site_count": len(sites),
        "source_count": len(sources),
        "tool_count": len(tools),
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "relationships_by_predicate": dict(sorted(predicate_counts.items())),
        "chunk_count": len(chunks),
        "embedding_input": "chunks.jsonl",
        "graph_node_inputs": [
            "instruments.jsonl",
            "endpoints.jsonl",
            "sites.jsonl",
            "sources.jsonl",
            "tools.jsonl",
            "entities.jsonl",
            "chunks.jsonl",
        ],
        "graph_edge_input": "relationships.jsonl",
        "approved_download_host": PORTAL_HOST,
        "routing_policy": "Static corpus first; live browse/download tools only after the corpus response and user invocation.",
        "validation": validation,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme = """# RCA PI portal Graph-RAG corpus

This static corpus covers exactly ten audited logical Regional Cabled Array PI
datasets. It answers whether data are available, the exact public download
endpoints, physical sites, formats, directory layouts, aliases, and caveats.

The intended agent flow is corpus first. Answer availability from `chunks.jsonl`
and traverse `DOWNLOADABLE_FROM` and `LOCATED_AT` relationships. After the
corpus response, the user may invoke the PI portal tools to browse current
directory listings, find files, plan a bounded download, or download selected
files. Live downloads belong under `runtime_data/PIPortal`; they are not added
to this static corpus automatically.

Files:

- `instruments.jsonl`: ten logical dataset/instrument nodes, reusing shared
  Instruments corpus IDs where available.
- `endpoints.jsonl`: every audited public data branch.
- `sites.jsonl`: physical site nodes using shared location IDs.
- `sources.jsonl`: the portal, official OOI pages, and shared Instruments corpus.
- `tools.jsonl`: schemas and execution policy for PI portal agent tools.
- `entities.jsonl`: routing policy and shared RCA observatory nodes.
- `relationships.jsonl`: graph edges, including first-class
  `DOWNLOADABLE_FROM`, `LOCATED_AT`, `ACCESSIBLE_WITH`, `BROWSES`, and
  `DOWNLOADS_FROM` edges.
- `chunks.jsonl`: embedding-ready instrument, tool, and routing-policy text.
- `manifest.json`: counts, validation results, and ingest entry points.

The PI portal currently uses public HTTP on the exact audited host
`piweb.ooirsn.uw.edu`. Source URLs are retained as provenance and actionable
download routes.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Directory for the Graph-RAG corpus")
    parser.add_argument("--instrument-corpus", type=Path, help="Optional shared Instruments/instruments.jsonl path")
    args = parser.parse_args()
    manifest = build(args.output, args.instrument_corpus)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
