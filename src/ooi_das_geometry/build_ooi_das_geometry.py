#!/usr/bin/env python3
"""Build structured, citable OOI RCA OptaSense DAS channel geography.

The official OOI geometry files supply one preliminary 2 m-spaced position for
each OptaSense channel.  They do *not* establish an equivalent channel mapping
for the separate Silixa interrogator, so this builder never makes that claim.
Raw portal files remain in source_material; output contains only published
coordinates, depth, and provenance required for location lookups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ooi_das_geometry_tools import TOOL_SCHEMAS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "source_material/original_documents/OOI_DAS_Geometry"
SOURCE_ROOT = "http://piweb.ooirsn.uw.edu/das/processed/metadata/Geometry/OOI_RCA_DAS_channel_location_with_depth/"
READ_ME_URL = "http://piweb.ooirsn.uw.edu/das/processed/metadata/readme.pdf"
DATASET_ID = "INSTRUMENT-981a1c15a947d3b1a1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:18]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_locations(path: Path, cable: str, source_sha256: str) -> list[dict[str, Any]]:
    locations = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4:
            raise ValueError(f"{path}:{line_number}: expected channel latitude longitude depth")
        channel_float, latitude, longitude, depth = map(float, parts)
        channel = int(channel_float)
        if channel != channel_float or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"{path}:{line_number}: invalid channel or WGS84 coordinate")
        locations.append({
            "channel_id": f"OOI-RCA-OPTASENSE-{cable.upper()}-CHANNEL-{channel:05d}",
            "channel_number": channel,
            "cable": cable,
            "instrument_id": DATASET_ID,
            "instrument_key": "PI-DAS-OPTASENSE-SILIXA",
            "interrogator": "OptaSense QuantX DAS",
            "latitude": latitude,
            "longitude": longitude,
            "depth_m": depth,
            "coordinate_reference_system": "WGS84",
            "channel_spacing_m": 2,
            "location_status": "preliminary_published_channel_location",
            "applicability": "OptaSense channel geometry only; not an asserted Silixa channel mapping.",
            "source_url": SOURCE_ROOT + path.name,
            "source_file": path.name,
            "source_file_sha256": source_sha256,
            "documented_campaign": "OOI RCN 2001 DAS/DTS experiment",
            "documented_data_dates": ["2021-11-01", "2021-11-02", "2021-11-03", "2021-11-04", "2021-11-05"],
            "source_is_untrusted_data": True,
        })
    if not locations:
        raise ValueError(f"{path}: no channel records")
    if any(right["channel_number"] <= left["channel_number"] for left, right in zip(locations, locations[1:])):
        raise ValueError(f"{path}: channel numbers must increase")
    return locations


def build(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    files = {cable: source_dir / f"{cable}_DAS_latlondepth.txt" for cable in ("north", "south")}
    if missing := [str(path) for path in files.values() if not path.is_file()]:
        raise FileNotFoundError("Missing OOI DAS geometry source files: " + ", ".join(missing))
    source_hashes = {cable: _sha256(path) for cable, path in files.items()}
    by_cable = {cable: parse_locations(path, cable, source_hashes[cable]) for cable, path in files.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    locations = [location for cable in ("north", "south") for location in by_cable[cable]]
    source_rows = [
        {
            "source_id": _id("SOURCE-OOI-DAS-GEOMETRY", path.name, source_hashes[cable]),
            "title": f"OOI RCA OptaSense {cable} DAS channel locations with depth",
            "source_url": SOURCE_ROOT + path.name,
            "source_file": path.name,
            "sha256": source_hashes[cable],
            "source_kind": "published_channel_geometry",
            "source_is_untrusted_data": True,
        }
        for cable, path in files.items()
    ]
    source_rows.append({
        "source_id": _id("SOURCE-OOI-DAS-README", READ_ME_URL),
        "title": "OOI RCN 2001 DAS/DTS experiment readme",
        "source_url": READ_ME_URL,
        "source_file": "readme.pdf",
        "sha256": _sha256(source_dir / "readme.pdf") if (source_dir / "readme.pdf").is_file() else None,
        "source_kind": "published_experiment_documentation",
        "source_is_untrusted_data": True,
    })
    entities, chunks, relationships = [], [], []
    for cable, rows in by_cable.items():
        entity_id = _id("ENTITY-OOI-DAS-CABLE", cable)
        source_id = source_rows[0 if cable == "north" else 1]["source_id"]
        title = f"OOI RCA OptaSense {cable.title()} Cable channel geometry"
        entities.append({
            "entity_id": entity_id, "name": title, "entity_type": "fiber_optic_cable_channel_map",
            "cable": cable, "interrogator": "OptaSense QuantX DAS", "channel_spacing_m": 2,
            "channel_start": rows[0]["channel_number"], "channel_end": rows[-1]["channel_number"],
            "channel_count": len(rows), "instrument_id": DATASET_ID,
            "location_status": "preliminary_published_channel_location",
            "source_is_untrusted_data": True,
        })
        text = (
            f"The OOI RCA 2021 OptaSense {cable} cable has {len(rows):,} published preliminary channel locations "
            f"at 2 m spacing, channels {rows[0]['channel_number']:,} through {rows[-1]['channel_number']:,}. "
            f"Each structured channel record provides WGS84 latitude, longitude, and GMRT-derived depth. "
            "The mapping applies to the OptaSense QuantX DAS geometry, not automatically to Silixa channels. "
            "The OOI readme documents data files dated 2021-11-01 through 2021-11-05."
        )
        chunk_id = _id("OOI-DAS-GEOMETRY-CHUNK", cable)
        chunks.append({"chunk_id": chunk_id, "parent_id": entity_id, "document_id": entity_id, "position": 0,
                       "title": title, "text": text, "word_count": len(text.split()), "source_ids": [source_id, source_rows[2]["source_id"]],
                       "source_urls": [SOURCE_ROOT + files[cable].name, READ_ME_URL], "source_is_untrusted_data": True})
        relationships.extend([
            {"relationship_id": _id("OOI-DAS-GEOMETRY-REL", entity_id, "HAS_CHUNK", chunk_id), "source_id": entity_id, "predicate": "HAS_CHUNK", "target_id": chunk_id, "evidence_source_ids": [source_id]},
            {"relationship_id": _id("OOI-DAS-GEOMETRY-REL", DATASET_ID, "USES_CHANNEL_MAP", entity_id), "source_id": DATASET_ID, "predicate": "USES_CHANNEL_MAP", "target_id": entity_id, "evidence_source_ids": [source_id, source_rows[2]["source_id"]]},
        ])
    _write_jsonl(output_dir / "channel_locations.jsonl", locations)
    _write_jsonl(output_dir / "sources.jsonl", source_rows)
    _write_jsonl(output_dir / "entities.jsonl", entities)
    _write_jsonl(output_dir / "chunks.jsonl", chunks)
    _write_jsonl(output_dir / "relationships.jsonl", relationships)
    _write_jsonl(output_dir / "tools.jsonl", [
        {**schema, "runtime": "src/ooi_das_geometry/ooi_das_geometry_tools.py",
         "requires_user_invocation_after_corpus_answer": True,
         "source_is_untrusted_data": True}
        for schema in TOOL_SCHEMAS
    ])
    manifest = {
        "schema_version": "1.0", "collection": "OOI RCA OptaSense DAS channel geometry", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "embedding_input": "chunks.jsonl", "graph_node_inputs": ["entities.jsonl", "sources.jsonl", "chunks.jsonl"],
        "graph_edge_input": "relationships.jsonl", "structured_inputs": ["channel_locations.jsonl"], "live_tool_manifest": "tools.jsonl",
        "counts": {"channel_locations": len(locations), "entities": len(entities), "chunks": len(chunks), "relationships": len(relationships)},
        "validation_status": "pass", "limitations": ["Published channel locations are preliminary.", "Only applies to OptaSense geometry; do not infer a Silixa channel mapping."],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "data/OOIDASGeometry")
    args = parser.parse_args()
    print(json.dumps(build(args.source_dir, args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
