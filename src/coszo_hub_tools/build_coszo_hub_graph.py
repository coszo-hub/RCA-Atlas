#!/usr/bin/env python3
"""Build a Graph-RAG-ready snapshot of COSZO Hub computational outputs.

Raw repositories and binary scientific artifacts stay in source_material.
This builder emits normalized JSONL, graph nodes/edges, retrieval chunks, and
selected visual outputs.  Live tools rescan the source output trees later.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coszo_hub_agent_tools import (
    DIVE_CONFIG,
    PRESSURE_STATIONS,
    SUPPORTED_REPOSITORIES,
    TOOL_SCHEMAS,
    VELOCITY_STATIONS,
    _coerce_scalar,
    _date_from_path,
    _kind,
    _station_from_path,
)
from ooi_m2m_agent_tools import SOURCE_REFERENCES
from earthscope_fdsn_agent_tools import OFFICIAL_SOURCES as EARTHSCOPE_OFFICIAL_SOURCES
from pi_portal_agent_tools import PI_INSTRUMENTS


UTC = timezone.utc
REPO_SUMMARIES = {
    "absolute-seafloor-pressure": "PREST absolute seafloor pressure acquisition, conversion, StationXML, gap detection, and timing diagnostics for RCA HYSB1, HYS14, and AXBA1.",
    "chronfix": "Clock correction package that consumes chronos correction bundles, applies interpolated timing corrections to MiniSEED, and splits at clock discontinuities.",
    "dive-index-hindcast": "CAWCR wave and wind hindcast workflow for the seasonal probability of suitable and persistent ROV dive conditions at four published COSZO sites.",
    "sea-water-velocity": "VEL3D acquisition, conversion, StationXML, gap detection, and timing diagnostics; the normalized corpus and default tools retain the RCA Series B outputs.",
}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def commit(repo: Path, fallback: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=20).strip()
    except Exception:
        return fallback


def graph_record(identifier: str, kind: str, name: str, summary: str, repo: str,
                 commit_sha: str, properties: dict | None = None, tags: list[str] | None = None) -> dict:
    return {
        "id": identifier, "type": kind, "name": name, "summary": summary,
        "source_url": f"https://github.com/coszo-hub/{repo}/tree/{commit_sha}",
        "repository": repo, "commit_sha": commit_sha,
        "license": SUPPORTED_REPOSITORIES[repo]["license"],
        "properties": properties or {}, "tags": tags or ["COSZO", "RCA"],
    }


def edge(identifier: str, source: str, target: str, predicate: str, repo: str, commit_sha: str) -> dict:
    return {"id": identifier, "type": "edge", "from": source, "to": target,
            "predicate": predicate, "evidence_url": f"https://github.com/coszo-hub/{repo}/tree/{commit_sha}",
            "repository": repo, "commit_sha": commit_sha}


def build(repository_root: Path, output_dir: Path) -> dict:
    generated = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    commits = {name: commit(repository_root / name, str(meta["commit"])) for name, meta in SUPPORTED_REPOSITORIES.items()}

    repositories, entities, relationships, chunks = [], [], [], []
    for name in SUPPORTED_REPOSITORIES:
        rid = f"repo:coszo-hub:{name}@{commits[name]}"
        rec = graph_record(rid, "Repository", name, REPO_SUMMARIES[name], name, commits[name],
                           {"organization": "coszo-hub", "default_branch": "main", "output_mode": "growing live directory"},
                           ["COSZO", "RCA", "software", "output-source"])
        repositories.append(rec); entities.append(rec)
        chunks.append({"id": f"chunk:{rid}", "type": "text_chunk", "title": name,
                       "text": f"{REPO_SUMMARIES[name]} Its output directory is treated as a growing live source. The agent rescans it at query time and records file modification times and commit provenance.",
                       "entity_ids": [rid], "repository": name, "commit_sha": commits[name], "source_url": rec["source_url"]})

    station_entities: dict[str, str] = {}
    for role, stations, repo in [("pressure", PRESSURE_STATIONS, "absolute-seafloor-pressure"), ("velocity", VELOCITY_STATIONS, "sea-water-velocity")]:
        for item in stations:
            sid = f"instrument:{item['reference_designator']}"
            station_entities[item["reference_designator"]] = sid
            rec = graph_record(sid, "Instrument", item["reference_designator"],
                               f"{role.title()} instrument at {item['site']} ({item['station']}).",
                               repo, commits[repo], item, ["COSZO", "RCA", role])
            entities.append(rec)
            relationships.append(edge(f"edge:{repo}:{sid}", f"repo:coszo-hub:{repo}@{commits[repo]}", sid, "SERVES_INSTRUMENT", repo, commits[repo]))

    dive_id = "algorithm:coszo:dive-index"
    entities.append(graph_record(dive_id, "Algorithm", "COSZO Dive Index",
        DIVE_CONFIG["formula"], "dive-index-hindcast", commits["dive-index-hindcast"], DIVE_CONFIG,
        ["COSZO", "ROV", "hindcast", "weather"]));
    relationships.append(edge("edge:dive-index:implemented-by", f"repo:coszo-hub:dive-index-hindcast@{commits['dive-index-hindcast']}", dive_id, "IMPLEMENTS", "dive-index-hindcast", commits["dive-index-hindcast"]))

    # Explicit capability, service, credential, algorithm, and artifact-schema
    # nodes make operational and lineage questions traversable in Graph-RAG.
    conceptual_nodes = [
        ("credential:ooi-api", "Credential", "OOI M2M API credentials", "OOI_USERNAME and OOI_TOKEN are required only to collect new OOI M2M data; querying existing repository outputs is credential-free.", "absolute-seafloor-pressure", {"environment_variables": ["OOI_USERNAME", "OOI_TOKEN"]}),
        ("service:ooi:m2m", "ExternalService", "OOI Machine-to-Machine API", "Supplies deployment metadata and asynchronous NetCDF data used by the pressure and velocity acquisition pipelines.", "absolute-seafloor-pressure", {"hosts": ["ooinet.oceanobservatories.org", "opendap.oceanobservatories.org", "downloads.oceanobservatories.org"]}),
        ("service:earthscope:fdsn", "ExternalService", "EarthScope FDSN", "Credential-free public waveform and station metadata access for OO and other FDSN networks. Bounded agent requests use the current service.earthscope.org endpoint.", "absolute-seafloor-pressure", {"host": "service.earthscope.org", "interfaces": ["station/1", "dataselect/1", "availability/1"], "availability_note": "The legacy availability service may return HTTP 410 during the 2026 cloud transition."}),
        ("service:csiro:cawcr", "ExternalService", "CSIRO CAWCR Wave Hindcast", "OPeNDAP source for significant wave height and 10-m wind components used by the Dive Index hindcast.", "dive-index-hindcast", {"grid": "glob_24m", "resolution_degrees": 0.4}),
        ("algorithm:coszo:gap:legacy", "Algorithm", "PREST legacy gap detector", "Robust median sample interval with an adaptive absolute interval threshold.", "absolute-seafloor-pressure", {}),
        ("algorithm:coszo:gap:anomaly", "Algorithm", "PREST anomaly gap detector", "OLS sample-clock fit plus integer-step reconstruction and wall-clock missing-sample correction; falls back to legacy below 100 samples.", "absolute-seafloor-pressure", {"minimum_samples": 100}),
        ("algorithm:coszo:chronfix:resample", "Algorithm", "Chronfix resample correction", "Subtracts interpolated clock error and resamples onto a regular UTC grid, splitting at trigger intervals.", "chronfix", {}),
        ("algorithm:coszo:chronfix:shift-only", "Algorithm", "Chronfix shift-only correction", "Shifts timestamps without changing sample bytes when within-segment drift is negligible.", "chronfix", {}),
        ("artifact-schema:coszo:temporal-variability", "DataArtifactType", "Temporal variability table", "Daily timing, gap, missing-sample, OLS interval, and jitter metrics keyed by station and UTC date.", "absolute-seafloor-pressure", {"format": "CSV upstream; JSONL in Graph-RAG"}),
        ("artifact-schema:coszo:diagnostic-figure", "DataArtifactType", "Timing diagnostic figure", "Per-day four-panel or cross-day summary visualization of sample timing, jitter, and gaps.", "sea-water-velocity", {"format": "PNG"}),
        ("artifact-schema:coszo:miniseed", "DataArtifactType", "MiniSEED", "Waveform output staged for SeedLink, EarthScope historical transfer, or corrected Chronfix output.", "absolute-seafloor-pressure", {"format": "MiniSEED"}),
        ("artifact-schema:coszo:stationxml", "DataArtifactType", "StationXML", "Station, channel, epoch, and instrument-response metadata.", "absolute-seafloor-pressure", {"format": "StationXML"}),
        ("artifact-schema:coszo:netcdf", "DataArtifactType", "OOI NetCDF", "Optional raw OOI response retained for audit and historical backfill.", "absolute-seafloor-pressure", {"format": "NetCDF"}),
        ("artifact-schema:coszo:chronfix-bundle", "DataArtifactType", "Chronfix correction bundle", "Aligned hourly timestamps and cleaned clock errors plus trigger-period indices.", "chronfix", {"required_files": ["hour_times.npy", "delta_t_hourly_clean.npy", "trigger_periods.csv"]}),
        ("artifact-schema:coszo:dive-index-report", "DataArtifactType", "Dive Index hindcast report", "Sixteen-page PDF containing four climatology plots for each of four published sites.", "dive-index-hindcast", {"pages": 16, "format": "PDF upstream; PNG pages in Graph-RAG"}),
        ("instrument:OO:HYS14:OBS", "Instrument", "HYS14 Hydrate Ridge OBS", "The one HYS14 ocean-bottom seismometer instrument whose clock error is represented by the bundled Chronfix model. The same instrument clock drives all of its channels.", "chronfix", {"network": "OO", "station": "HYS14", "instrument_type": "OBS", "instrument_id": "OO.HYS14.OBS", "correction_scope": "all channels on this OBS clock; not PREST or VEL3D"}),
        ("stream:OO:HYS14::MHZ", "DataStream", "OO.HYS14..MHZ", "The 8 Hz vertical seismic stream used to derive and validate the bundled HYS14 Chronfix model. MHZ supplies the evidence; the fitted clock error applies to other channels on the same OBS instrument.", "chronfix", {"network": "OO", "station": "HYS14", "location": "", "channel": "MHZ", "role": "derivation_and_validation"}),
        ("policy:hys14:chronfix-routing", "RoutingPolicy", "HYS14 Chronfix routing", "Every HYS14 question discloses that one OBS instrument has a known clock correction. Shifts apply to apparent timestamps on any channel sharing that OBS clock; PREST, VEL3D, other instruments, and already-corrected UTC remain unchanged.", "chronfix", {"aliases": ["HYS14", "RS01SUM1", "Hydrate Summit"], "affected_instrument": "OO.HYS14.OBS", "derivation_channel": "MHZ", "automatic_context": True, "refresh_before_use": True}),
    ]
    for identifier, kind, name, summary, repo, properties in conceptual_nodes:
        entities.append(graph_record(identifier, kind, name, summary, repo, commits[repo], properties))
        chunks.append({"id": f"chunk:{identifier}", "type": "text_chunk", "title": name, "text": summary,
                       "entity_ids": [identifier], "repository": repo, "commit_sha": commits[repo],
                       "source_url": f"https://github.com/coszo-hub/{repo}/tree/{commits[repo]}"})

    # These projects informed the lightweight live M2M adapter. Their source
    # code stays outside data; Graph-RAG receives only compact provenance.
    for source in SOURCE_REFERENCES:
        slug = source["name"].casefold().replace("_", "-")
        sid = f"software-reference:{slug}@{source['commit']}"
        record = {
            "id": sid, "type": "SoftwareReference", "name": source["name"],
            "summary": source["role"], "source_url": f"{source['url']}/tree/{source['commit']}",
            "repository": source["url"].removeprefix("https://github.com/"),
            "commit_sha": source["commit"], "license": source["license"],
            "properties": {"role": "design reference for independent OOI M2M agent adapter"},
            "tags": ["OOI", "M2M", "software", "provenance"],
        }
        entities.append(record)
        chunks.append({"id": f"chunk:{sid}", "type": "text_chunk", "title": source["name"],
                       "text": f"{source['name']} ({source['license']}) is pinned at commit {source['commit']} and serves as a design reference for the agent's OOI M2M tools: {source['role']}.",
                       "entity_ids": [sid], "repository": record["repository"],
                       "commit_sha": source["commit"], "source_url": record["source_url"]})

    for index, source in enumerate(EARTHSCOPE_OFFICIAL_SOURCES, 1):
        sid = f"source:earthscope:fdsn:{index}"
        record = {
            "id": sid, "type": "AuthoritativeSource", "name": source["name"],
            "summary": source["role"], "source_url": source["url"],
            "repository": None, "commit_sha": None, "license": None,
            "properties": {"publisher": "EarthScope Consortium", "accessed_on": generated[:10]},
            "tags": ["EarthScope", "FDSN", "official-documentation", "provenance"],
        }
        entities.append(record)
        chunks.append({"id": f"chunk:{sid}", "type": "text_chunk", "title": source["name"],
                       "text": f"Official EarthScope source: {source['role']}. URL: {source['url']}",
                       "entity_ids": [sid], "repository": None, "commit_sha": None,
                       "source_url": source["url"]})
        relationships.append({"id": f"edge:earthscope-service:documented-by:{index}", "type": "edge",
                              "from": "service:earthscope:fdsn", "to": sid,
                              "predicate": "DOCUMENTED_BY", "evidence_url": source["url"],
                              "repository": None, "commit_sha": None})

    for repo in ["absolute-seafloor-pressure", "sea-water-velocity"]:
        rid = f"repo:coszo-hub:{repo}@{commits[repo]}"
        relationships.extend([
            edge(f"edge:{repo}:calls:ooi", rid, "service:ooi:m2m", "CALLS", repo, commits[repo]),
            edge(f"edge:{repo}:requires:ooi", rid, "credential:ooi-api", "REQUIRES_FOR_NEW_COLLECTION", repo, commits[repo]),
            edge(f"edge:{repo}:uses:legacy", rid, "algorithm:coszo:gap:legacy", "USES_ALGORITHM", repo, commits[repo]),
            edge(f"edge:{repo}:uses:anomaly", rid, "algorithm:coszo:gap:anomaly", "USES_ALGORITHM", repo, commits[repo]),
            edge(f"edge:{repo}:produces:variability", rid, "artifact-schema:coszo:temporal-variability", "PRODUCES", repo, commits[repo]),
            edge(f"edge:{repo}:produces:figure", rid, "artifact-schema:coszo:diagnostic-figure", "PRODUCES", repo, commits[repo]),
            edge(f"edge:{repo}:produces:mseed", rid, "artifact-schema:coszo:miniseed", "PRODUCES", repo, commits[repo]),
            edge(f"edge:{repo}:produces:stationxml", rid, "artifact-schema:coszo:stationxml", "PRODUCES", repo, commits[repo]),
            edge(f"edge:{repo}:produces:netcdf", rid, "artifact-schema:coszo:netcdf", "PRODUCES", repo, commits[repo]),
        ])
    relationships.extend([
        edge("edge:pressure:uses:fdsn", f"repo:coszo-hub:absolute-seafloor-pressure@{commits['absolute-seafloor-pressure']}", "service:earthscope:fdsn", "CAN_QUERY", "absolute-seafloor-pressure", commits["absolute-seafloor-pressure"]),
        edge("edge:chronfix:uses:resample", f"repo:coszo-hub:chronfix@{commits['chronfix']}", "algorithm:coszo:chronfix:resample", "IMPLEMENTS", "chronfix", commits["chronfix"]),
        edge("edge:chronfix:uses:shift", f"repo:coszo-hub:chronfix@{commits['chronfix']}", "algorithm:coszo:chronfix:shift-only", "IMPLEMENTS", "chronfix", commits["chronfix"]),
        edge("edge:chronfix:consumes:bundle", f"repo:coszo-hub:chronfix@{commits['chronfix']}", "artifact-schema:coszo:chronfix-bundle", "CONSUMES", "chronfix", commits["chronfix"]),
        edge("edge:chronfix:produces:mseed", f"repo:coszo-hub:chronfix@{commits['chronfix']}", "artifact-schema:coszo:miniseed", "PRODUCES", "chronfix", commits["chronfix"]),
        edge("edge:chronfix:corrects:hys14-obs", "artifact-schema:coszo:chronfix-bundle", "instrument:OO:HYS14:OBS", "CORRECTS_CLOCK_OF", "chronfix", commits["chronfix"]),
        edge("edge:chronfix:validated:mhz", "instrument:OO:HYS14:OBS", "stream:OO:HYS14::MHZ", "MODEL_DERIVED_AND_VALIDATED_WITH", "chronfix", commits["chronfix"]),
        edge("edge:hys14-policy:uses:bundle", "policy:hys14:chronfix-routing", "artifact-schema:coszo:chronfix-bundle", "USES", "chronfix", commits["chronfix"]),
        edge("edge:hys14-policy:targets:obs", "policy:hys14:chronfix-routing", "instrument:OO:HYS14:OBS", "AUTO_APPLIES_TO_ALL_CHANNELS_OF", "chronfix", commits["chronfix"]),
        edge("edge:dive:consumes:cawcr", f"repo:coszo-hub:dive-index-hindcast@{commits['dive-index-hindcast']}", "service:csiro:cawcr", "CALLS", "dive-index-hindcast", commits["dive-index-hindcast"]),
        edge("edge:dive:produces:report", f"repo:coszo-hub:dive-index-hindcast@{commits['dive-index-hindcast']}", "artifact-schema:coszo:dive-index-report", "PRODUCES", "dive-index-hindcast", commits["dive-index-hindcast"]),
    ])

    tool_records = []
    for schema in TOOL_SCHEMAS:
        tid = f"tool:{schema['name']}"
        tool = {"id": tid, "type": "AgentTool", "name": schema["name"], "summary": schema["description"],
                "input_schema": schema["inputSchema"], "runtime": "src/coszo_hub_tools/mcp_server.py",
                "reads_growing_outputs": schema["name"] in {"coszo_output_status","coszo_list_outputs","coszo_read_output","coszo_get_figure","coszo_find_diagnostic_figure","coszo_metric_rows","coszo_metric_summary","coszo_dive_index_page","coszo_question_context"},
                "uses_live_ooi_m2m": schema["name"].startswith("ooi_m2m_") and schema["name"] not in {"ooi_m2m_status", "ooi_m2m_plan_request", "ooi_m2m_search_instruments"},
                "uses_live_earthscope_fdsn": schema["name"].startswith("earthscope_") and schema["name"] not in {"earthscope_fdsn_status", "earthscope_plan_waveform"},
                "uses_live_pi_portal": schema["name"].startswith("pi_portal_") and schema["name"] not in {"pi_portal_status", "pi_portal_list_instruments", "pi_portal_plan_download"},
                "generated_at_utc": generated}
        tool_records.append(tool); entities.append(tool)
        chunks.append({"id": f"chunk:{tid}", "type": "text_chunk", "title": schema["name"],
                       "text": f"Agent tool {schema['name']}: {schema['description']} Inputs follow this JSON Schema: {json.dumps(schema['inputSchema'], sort_keys=True)}",
                       "entity_ids": [tid], "source_url": None})
        if schema["name"].startswith("ooi_m2m_"):
            relationships.append({"id": f"edge:{schema['name']}:calls:ooi", "type": "edge",
                                  "from": tid, "to": "service:ooi:m2m", "predicate": "CALLS_OR_PLANS_CALL_TO",
                                  "evidence_url": "https://oceanobservatories.org/ooi-m2m-interface/",
                                  "repository": "local-agent-tool", "commit_sha": None})
            for source in SOURCE_REFERENCES:
                slug = source["name"].casefold().replace("_", "-")
                sid = f"software-reference:{slug}@{source['commit']}"
                relationships.append({"id": f"edge:{schema['name']}:informed-by:{slug}", "type": "edge",
                                      "from": tid, "to": sid, "predicate": "INFORMED_BY",
                                      "evidence_url": f"{source['url']}/tree/{source['commit']}",
                                      "repository": source["url"].removeprefix("https://github.com/"),
                                      "commit_sha": source["commit"]})
        if schema["name"].startswith("earthscope_"):
            relationships.append({"id": f"edge:{schema['name']}:calls:earthscope", "type": "edge",
                                  "from": tid, "to": "service:earthscope:fdsn", "predicate": "CALLS_OR_PLANS_CALL_TO",
                                  "evidence_url": "https://service.earthscope.org/fdsnws/",
                                  "repository": None, "commit_sha": None})
            for index, source in enumerate(EARTHSCOPE_OFFICIAL_SOURCES, 1):
                relationships.append({"id": f"edge:{schema['name']}:documented-by:{index}", "type": "edge",
                                      "from": tid, "to": f"source:earthscope:fdsn:{index}",
                                      "predicate": "DOCUMENTED_BY", "evidence_url": source["url"],
                                      "repository": None, "commit_sha": None})

    metrics, diagnostics, figure_records, artifact_records = [], [], [], []
    roots = {
        "absolute-seafloor-pressure": repository_root / "absolute-seafloor-pressure" / "PREST-data-collection" / "output",
        "sea-water-velocity": repository_root / "sea-water-velocity" / "VEL3D-data-collection" / "output",
        "chronfix": repository_root / "chronfix" / "examples" / "HYS14",
        "dive-index-hindcast": repository_root / "dive-index-hindcast",
    }
    counts = Counter()
    for repo, root in roots.items():
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
            rel = path.relative_to(root).as_posix()
            station = _station_from_path(rel)
            in_scope = not (repo == "sea-water-velocity" and station and station.startswith("CE"))
            if not in_scope:
                continue
            artifact_id = f"artifact:{hashlib.sha256((repo + ':' + rel).encode()).hexdigest()[:24]}"
            base = {"id": artifact_id, "type": "DataArtifact", "repository": repo,
                    "relative_path": rel, "name": path.name, "kind": _kind(path),
                    "station": station, "observation_date": _date_from_path(rel),
                    "byte_size": path.stat().st_size,
                    "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z"),
                    "source_url": f"https://github.com/coszo-hub/{repo}/blob/{commits[repo]}/{path.relative_to(repository_root/repo).as_posix()}",
                    "commit_sha": commits[repo], "license": SUPPORTED_REPOSITORIES[repo]["license"]}
            artifact_records.append(base); counts[f"artifact:{repo}"] += 1
            relationships.append(edge(f"edge:{repo}:produces:{artifact_id}", f"repo:coszo-hub:{repo}@{commits[repo]}", artifact_id, "PRODUCES", repo, commits[repo]))
            suffix = path.suffix.lower()
            if suffix == ".csv":
                with path.open(newline="", encoding="utf-8", errors="replace") as stream:
                    for row_number, raw in enumerate(csv.DictReader(stream), 2):
                        row = {str(k) if k is not None else "extra_columns": _coerce_scalar(v) for k, v in raw.items()}
                        rid = hashlib.sha256(f"{repo}:{rel}:{row_number}".encode()).hexdigest()[:24]
                        metrics.append({"id": f"metric:{rid}", "type": "MetricObservation", "repository": repo,
                                        "source_artifact_id": artifact_id, "source_relative_path": rel,
                                        "source_row": row_number, "commit_sha": commits[repo], **row})
            elif suffix in {".txt", ".log"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                pairs = {}
                for line in text.splitlines():
                    match = re.match(r"\s*([^:#]{2,60})\s*:\s*(.*?)\s*$", line)
                    if match: pairs[match.group(1).strip()] = _coerce_scalar(match.group(2))
                diagnostics.append({**base, "text": text[:100_000], "parsed_fields": pairs})
            elif suffix in {".png", ".jpg", ".jpeg"}:
                figure_records.append(base)

    # Preserve the relatively small, high-value summary/example figures in data.
    selected: list[tuple[str, Path]] = []
    chron = roots["chronfix"]
    selected.extend(("chronfix", p) for p in sorted(chron.rglob("*.png")))
    vel = roots["sea-water-velocity"]
    selected.extend(("sea-water-velocity", p) for p in sorted(vel.rglob("fig*.png")) if "summary" in p.as_posix())
    copied_figures = []
    for repo, src in selected:
        target = figures_dir / repo / src.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied_figures.append({"repository": repo, "path": target.relative_to(output_dir).as_posix(), "sha256": sha256(target), "byte_size": target.stat().st_size})

    # Render every page of the current Dive Index result to an ingestible PNG.
    dive_pdf = roots["dive-index-hindcast"] / "RCA_DiveIndex_2006_2025.pdf"
    if dive_pdf.exists() and shutil.which("pdftoppm"):
        dive_target = figures_dir / "dive-index-hindcast"
        dive_target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-png", "-r", "110", str(dive_pdf), str(dive_target / "RCA_DiveIndex_2006_2025_page")], check=True, timeout=300)
        for page in sorted(dive_target.glob("*.png")):
            copied_figures.append({"repository": "dive-index-hindcast", "path": page.relative_to(output_dir).as_posix(), "sha256": sha256(page), "byte_size": page.stat().st_size})

    write_jsonl(output_dir / "repositories.jsonl", repositories)
    write_jsonl(output_dir / "tools.jsonl", tool_records)
    write_jsonl(output_dir / "entities.jsonl", entities + artifact_records)
    write_jsonl(output_dir / "relationships.jsonl", relationships)
    write_jsonl(output_dir / "chunks.jsonl", chunks)
    write_jsonl(output_dir / "metrics.jsonl", metrics)
    write_jsonl(output_dir / "diagnostics.jsonl", diagnostics)
    write_jsonl(output_dir / "figures.jsonl", figure_records)

    readme = f"""# COSZO Hub Graph-RAG and live output tools

This corpus covers four computational repositories from `coszo-hub`: absolute
seafloor pressure, Chronfix, Dive Index hindcast, and sea-water velocity.  The
website repository is intentionally excluded because its content is already in
the existing COSZO website corpus.

The JSONL files contain repository/tool descriptions, graph entities and
relationships, normalized CSV observations, parsed diagnostic text, and figure
metadata. Selected summary/example figures and all 16 pages of the published
Dive Index report are supplied as PNGs under `figures/`.

The source output directories are expected to grow. Static JSONL records are a
reproducible snapshot generated at {generated}. Time-sensitive questions should
use the MCP tools in `src/coszo_hub_tools/`; they rescan configured output roots
at query time and maintain only an incremental SQLite index in `runtime_data`.

The same MCP server includes general OOI M2M tools for local instrument search,
live vocabulary/deployment/stream discovery, bounded request planning and
submission, asynchronous status checks, result listing, and bounded downloads.
The adapter is not restricted to PREST. OOINet and ooi-harvester are pinned as
design references with license and commit provenance; their source code remains
under `source_material`, outside this ingestible corpus. Live request state and
downloaded files go to `runtime_data/OOIM2M`, never to `data`.

Public EarthScope tools search station/channel metadata, plan and download
bounded MiniSEED waveforms, download StationXML, and query availability when
that service is operating. Waveform requests default to one exact station and
at most 24 hours. Results and hash manifests are written to
`runtime_data/EarthScope`; continuous real-time streams should use SeedLink.

The same server exposes public PI portal tools for the ten audited RCA PI
instrument or experiment collections. Availability and download URLs are
answered first from `data/PIPortal`; a user can then invoke bounded live
browsing, file discovery, download planning, or selected downloads. Runtime
files and hash manifests go to `runtime_data/PIPortal`, never to `data`.

HYS14 routing is instrument-scoped. The bundled Chronfix model represents the
clock of the HYS14 Hydrate Ridge OBS. It was derived and validated with
`OO.HYS14..MHZ`, and the same fitted clock error applies to every channel that
shares that OBS clock. The shift is never applied to independent PREST, VEL3D,
or other instrument data. Correction calls refresh the live model files or the
public Chronfix checkout first and record an immutable bundle fingerprint.

Repository snapshots, raw CSV/TXT/NPY/XML/PDF/MiniSEED/NetCDF files, and source
code belong under `source_material/repositories/coszo-hub`, outside `data`.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    manifest = {
        "schema_version": "1.0", "generated_at_utc": generated,
        "scope": "COSZO Hub computational repositories; RCA defaults; published Dive Index sites retained",
        "excluded_repository": "coszo-hub.github.io (duplicate of existing coszo.org corpus)",
        "repository_commits": commits,
        "counts": {"repositories": len(repositories), "tools": len(tool_records),
                   "entities": len(entities) + len(artifact_records), "relationships": len(relationships),
                   "chunks": len(chunks), "metrics": len(metrics), "diagnostics": len(diagnostics),
                   "figure_records": len(figure_records), "copied_figures": len(copied_figures)},
        "copied_figures": copied_figures,
        "live_index": "runtime_data/COSZOHub/output_index.sqlite",
        "ooi_m2m_runtime": "runtime_data/OOIM2M",
        "ooi_m2m_source_references": SOURCE_REFERENCES,
        "earthscope_runtime": "runtime_data/EarthScope",
        "earthscope_official_sources": EARTHSCOPE_OFFICIAL_SOURCES,
        "pi_portal_runtime": "runtime_data/PIPortal",
        "pi_portal_dataset_count": len(PI_INSTRUMENTS),
        "pi_portal_endpoint_count": sum(len(item["endpoints"]) for item in PI_INSTRUMENTS.values()),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repository_root.resolve(), args.output_dir.resolve()), indent=2))


if __name__ == "__main__":
    main()
