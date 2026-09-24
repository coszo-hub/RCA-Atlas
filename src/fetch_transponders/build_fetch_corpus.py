#!/usr/bin/env python3
"""Build a source-backed Graph-RAG collection for Axial FETCH transponders.

The builder deliberately reads the archived AxialFetch README and configuration
snapshot rather than reaching out to GitHub.  Raw time series remain original
source material; this collection indexes only concise descriptions and stable
station/baseline metadata needed to route questions correctly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "source_material/original_documents/AxialFetch"
DEFAULT_OUTPUT = ROOT / "data/FETCH"
UPSTREAM_URL = "https://github.com/MaleenKidiwela/AxialFetch"
UPSTREAM_COMMIT = "dbd132197b484490488fe16173df63140bb0ed22"
DATA_URL = f"{UPSTREAM_URL}/tree/{UPSTREAM_COMMIT}/Data"
DISTANCES_URL = f"{UPSTREAM_URL}/tree/{UPSTREAM_COMMIT}/src/output/distances"


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:18]}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _station_metadata(config: str) -> dict[str, dict[str, float]]:
    match = re.search(r"STATION_META\s*=\s*\{(.*?)\n\}", config, re.S)
    if not match:
        raise ValueError("AxialFetch config does not define STATION_META")
    result: dict[str, dict[str, float]] = {}
    for identifier, lat, lon, heading in re.findall(
        r'"(250[234])"\s*:\s*dict\(lat=([-0-9.]+),\s*lon=([-0-9.]+),\s*heading=([-0-9.]+)\)',
        match.group(1),
    ):
        result[identifier] = {"latitude": float(lat), "longitude": float(lon), "heading_degrees": float(heading)}
    if set(result) != {"2502", "2503", "2504"}:
        raise ValueError(f"Unexpected FETCH station metadata: {sorted(result)}")
    return result


def build(source: Path, output: Path) -> None:
    readme_path = source / "README.md"
    config_path = source / "config.py"
    readme = readme_path.read_text(encoding="utf-8")
    config = config_path.read_text(encoding="utf-8")
    if "three ocean-bottom stations at the summit caldera of Axial Seamount" not in readme:
        raise ValueError("AxialFetch README did not contain the expected network description")
    stations = _station_metadata(config)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    source_id = "SOURCE-AXIAL-FETCH-UPSTREAM"
    project_id = "FETCH-PROJECT-AXIAL-SEAMOUNT"
    site_id = "FETCH-SITE-AXIAL-SUMMIT-CALDERA"
    type_id = "FETCH-TYPE-ACOUSTIC-RANGING-STATION"
    data_id = "FETCH-DATA-ACOUSTIC-RANGE-PRODUCTS"
    raw_data_endpoint_id = "FETCH-ENDPOINT-RAW-STATION-DATA"
    distance_endpoint_id = "FETCH-ENDPOINT-PROCESSED-DISTANCES"
    station_rows = (
        ("2504", "Northern", "North side", "00687A"),
        ("2503", "Western", "West side", "006874"),
        ("2502", "Eastern", "East side", "006870"),
    )
    baseline_rows = (
        ("NW", "2504", "2503", 1.765), ("WN", "2503", "2504", 1.765),
        ("NE", "2504", "2502", 1.642), ("EN", "2502", "2504", 1.642),
        ("WE", "2503", "2502", 3.260), ("EW", "2502", "2503", 3.260),
    )

    entities = [
        {"entity_id": project_id, "name": "FETCH seafloor geodetic monitoring network", "type": "acoustic_geodetic_network", "canonical_id": "FETCH", "method": "upstream_readme"},
        {"entity_id": site_id, "name": "Axial Seamount summit caldera", "type": "location", "method": "upstream_readme"},
        {"entity_id": type_id, "name": "FETCH acoustic ranging station (transponder)", "type": "instrument_type", "aliases": ["FETCH transponder", "acoustic transponder", "acoustic geodetic transponder"], "method": "source_wording_plus_query_alias"},
        {"entity_id": data_id, "name": "FETCH calibrated acoustic baseline distance products", "type": "derived_data_product", "method": "upstream_readme"},
        {"entity_id": raw_data_endpoint_id, "name": "FETCH raw station data files", "type": "public_data_endpoint", "url": DATA_URL, "method": "upstream_repository_layout"},
        {"entity_id": distance_endpoint_id, "name": "FETCH processed baseline distance files", "type": "public_data_endpoint", "url": DISTANCES_URL, "method": "upstream_repository_layout"},
    ]
    chunks: list[dict] = []
    relationships: list[dict] = []
    instruments: list[dict] = []

    overview_id = stable_id("FETCH-CHUNK", "overview")
    chunks.append({
        "chunk_id": overview_id, "document_id": project_id, "parent_id": project_id, "position": 0,
        "title": "FETCH acoustic geodetic network at Axial Seamount",
        "source_ids": [source_id], "source_urls": [UPSTREAM_URL, DATA_URL, DISTANCES_URL], "source_is_untrusted_data": True,
        "text": "FETCH is a cabled seafloor geodetic monitoring network at the summit caldera of Axial Seamount. It has three ocean-bottom acoustic ranging stations: Northern (2504), Western (2503), and Eastern (2502). The system processes pressure, temperature, salinity, sound speed, inclinometer, and acoustic travel-time records to produce calibrated inter-station baseline distances for volcanic-deformation monitoring. Raw station files are published in the AxialFetch Data directory and processed baseline-distance CSVs in src/output/distances. It is not a generic hydrophone, DAS, or ambient-noise interferometry dataset.",
    })
    relationships.extend((
        {"source_id": overview_id, "predicate": "DESCRIBES", "target_id": project_id},
        {"source_id": project_id, "predicate": "LOCATED_AT", "target_id": site_id},
        {"source_id": project_id, "predicate": "PRODUCES", "target_id": data_id},
        {"source_id": project_id, "predicate": "RAW_DATA_AVAILABLE_AT", "target_id": raw_data_endpoint_id},
        {"source_id": data_id, "predicate": "AVAILABLE_AT", "target_id": distance_endpoint_id},
        {"source_id": project_id, "predicate": "SUPPORTED_BY", "target_id": source_id},
    ))

    station_ids: dict[str, str] = {}
    for position, (identifier, name, caldera_position, module_serial) in enumerate(station_rows, 1):
        station_id = f"FETCH-TRANSPONDER-{identifier}"
        station_ids[identifier] = station_id
        meta = stations[identifier]
        instruments.append({
            "instrument_id": station_id, "canonical_id": f"FETCH-{identifier}",
            "name": f"FETCH {name} acoustic ranging station ({identifier})",
            "instrument_type": "acoustic_ranging_station", "instrument_type_aliases": ["FETCH transponder", "acoustic transponder", "acoustic geodetic transponder"], "location": "Axial Seamount summit caldera",
            "station": name, "station_identifier": identifier, "caldera_position": caldera_position,
            "latitude": meta["latitude"], "longitude": meta["longitude"], "heading_degrees": meta["heading_degrees"],
            "module_serial_hex": module_serial, "projects": ["FETCH", "Regional Cabled Array"],
            "record_status": "documented_project_instance", "deployment_state": "status_not_stated_in_source_snapshot",
            "source_system": "AxialFetch upstream repository", "source_urls": [UPSTREAM_URL],
            "source_is_untrusted_data": True,
            "evidence": [{"source_id": source_id, "locator": "README Station Network; src/config.py STATION_META"}],
            "measurement_roles": ["acoustic travel-time ranging", "pressure", "temperature", "sound speed", "inclinometer pitch and roll"],
            "notes": "No depth or manufacturer is asserted because the archived source snapshot does not establish either field.",
        })
        entities.append({"entity_id": station_id, "name": instruments[-1]["name"], "type": "instrument", "canonical_id": f"FETCH-{identifier}", "aliases": [f"FETCH {name} transponder", f"FETCH {identifier}", f"{name} acoustic transponder"], "method": "upstream_config_station_metadata", "latitude": meta["latitude"], "longitude": meta["longitude"]})
        chunk_id = stable_id("FETCH-CHUNK", identifier)
        chunks.append({
            "chunk_id": chunk_id, "document_id": project_id, "parent_id": station_id, "position": position,
            "title": f"FETCH {name} acoustic ranging station / transponder ({identifier})", "source_ids": [source_id], "source_urls": [UPSTREAM_URL], "source_is_untrusted_data": True,
            "text": f"The FETCH {name} acoustic ranging station (also called a FETCH transponder) is station {identifier} on the {caldera_position.casefold()} of Axial Seamount summit caldera (latitude {meta['latitude']:.8f}, longitude {meta['longitude']:.7f}; configured heading {meta['heading_degrees']:.0f}°). Its archived input file uses module serial {module_serial}. FETCH station records include pressure (DQZ), temperature (TMP), sound speed (SSP), inclinometer (INC), and baseline acoustic travel-time (BSL) codes. The source does not establish a deployment depth or manufacturer for this station.",
        })
        relationships.extend((
            {"source_id": chunk_id, "predicate": "DESCRIBES", "target_id": station_id},
            {"source_id": project_id, "predicate": "HAS_STATION", "target_id": station_id},
            {"source_id": station_id, "predicate": "HAS_TYPE", "target_id": type_id},
            {"source_id": station_id, "predicate": "LOCATED_AT", "target_id": site_id},
            {"source_id": station_id, "predicate": "SUPPORTED_BY", "target_id": source_id},
        ))

    for direction, origin, target, length_km in baseline_rows:
        baseline_id = f"FETCH-BASELINE-{direction}"
        entities.append({"entity_id": baseline_id, "name": f"FETCH {direction} acoustic baseline", "type": "acoustic_baseline", "direction": direction, "nominal_length_km": length_km, "method": "upstream_config_baseline_metadata"})
        relationships.extend((
            {"source_id": station_ids[origin], "predicate": "RANGES_TO", "target_id": station_ids[target], "baseline_id": baseline_id, "direction": direction, "nominal_length_km": length_km},
            {"source_id": baseline_id, "predicate": "CONNECTS", "target_id": station_ids[origin]},
            {"source_id": baseline_id, "predicate": "CONNECTS", "target_id": station_ids[target]},
            {"source_id": baseline_id, "predicate": "GENERATES", "target_id": data_id},
        ))

    baseline_chunk_id = stable_id("FETCH-CHUNK", "baselines")
    chunks.append({
        "chunk_id": baseline_chunk_id, "document_id": project_id, "parent_id": project_id, "position": 4,
        "title": "FETCH Axial acoustic baselines and range products", "source_ids": [source_id], "source_urls": [UPSTREAM_URL], "source_is_untrusted_data": True,
        "text": "FETCH measures six directed acoustic baseline records across three station pairs: North–West and West–North, 1.765 km; North–East and East–North, 1.642 km; and West–East and East–West, 3.260 km. The range pipeline uses pairwise harmonic-mean sound speed and two-way acoustic travel time minus turnaround time to calculate one-way distance, applies tilt corrections, and exports raw and corrected distance time series with record time, distance in centimetres, and moving-average distance. The upstream README documents the formula Distance = harmonic sound speed × (range milliseconds − turnaround milliseconds) / 2000.",
    })
    relationships.append({"source_id": baseline_chunk_id, "predicate": "DESCRIBES", "target_id": data_id})
    for direction, _, _, _ in baseline_rows:
        relationships.append({"source_id": baseline_chunk_id, "predicate": "DESCRIBES", "target_id": f"FETCH-BASELINE-{direction}"})

    sources = [{
        "source_id": source_id, "name": "AxialFetch — Seafloor Geodetic Monitoring at Axial Seamount",
        "url": f"{UPSTREAM_URL}/tree/{UPSTREAM_COMMIT}", "publisher": "AxialFetch contributors", "access": "public",
        "source_kind": "versioned_upstream_repository", "upstream_commit": UPSTREAM_COMMIT,
        "archived_files": ["source_material/original_documents/AxialFetch/README.md", "source_material/original_documents/AxialFetch/config.py"],
        "content_sha256": {"README.md": sha256(readme_path), "config.py": sha256(config_path)},
        "rights_note": "Source URL, commit, identifiers, and attribution retained. Raw source data are not copied into the graph-ready collection.",
    }]
    ids = {row["entity_id"] for row in entities} | {row["instrument_id"] for row in instruments} | {row["chunk_id"] for row in chunks} | {source_id}
    unresolved = [edge for edge in relationships if edge["source_id"] not in ids or edge["target_id"] not in ids]
    validation = {"status": "pass" if not unresolved else "fail", "checks": {"three_fetch_transponders": len(instruments) == 3, "six_directed_baselines": len(baseline_rows) == 6, "all_relationship_endpoints_resolve": not unresolved, "no_unsupported_depth_or_manufacturer": all("depth_m" not in row and row.get("manufacturer") is None for row in instruments)}, "problems": {"unresolved_relationships": unresolved}}

    write_jsonl(output / "instruments.jsonl", instruments)
    write_jsonl(output / "entities.jsonl", entities)
    write_jsonl(output / "chunks.jsonl", chunks)
    write_jsonl(output / "sources.jsonl", sources)
    write_jsonl(output / "relationships.jsonl", relationships)
    (output / "validation_report.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "scope": "Axial Seamount FETCH cabled acoustic geodetic transponder network and derived range products", "source_input": source.relative_to(ROOT).as_posix(), "embedding_input": "chunks.jsonl", "instrument_node_input": "instruments.jsonl", "other_node_inputs": ["entities.jsonl", "sources.jsonl"], "graph_edge_input": "relationships.jsonl", "validation_status": validation["status"], "counts": {"instruments": len(instruments), "entities": len(entities), "chunks": len(chunks), "sources": len(sources), "relationships": len(relationships)}, "limitations": ["The archived source snapshot establishes station coordinates, roles, and baseline/range products but not deployment depth or manufacturer.", "Raw FETCH time series remain source material and are not embedded or copied into this graph-ready collection.", "The station called Northern (2504) is labelled Central in two legacy modeling notebooks; this collection retains the README/config naming and records that legacy caveat in source provenance."]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# FETCH Axial transponder corpus\n\nA source-backed, graph-ready index of the Axial FETCH network. It is intentionally distinct from generic hydrophone, DAS, and ambient-noise evidence. See `manifest.json` for provenance and limitations.\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
