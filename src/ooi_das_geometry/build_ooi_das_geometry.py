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
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ooi_das_geometry_tools import TOOL_SCHEMAS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "source_material/original_documents/OOI_DAS_Geometry"
SOURCE_ROOT = "http://piweb.ooirsn.uw.edu/das/processed/metadata/Geometry/OOI_RCA_DAS_channel_location_with_depth/"
READ_ME_URL = "http://piweb.ooirsn.uw.edu/das/processed/metadata/readme.pdf"
ARTICLE_URL = "https://oceanobservatories.org/2026/03/multi-span-fiber-sensing-expands-reach-of-ooi-regional-cabled-array/"
ARTICLE_FILE = "multi_span_fiber_sensing_2026-03-31.html"
DATASET_ID = "INSTRUMENT-981a1c15a947d3b1a1"
# PI-DAS25 is the canonical shared inventory entity for the 2025--26
# multi-span/OptoDAS deployment.  It must not be conflated with the separate
# 2021 OptaSense/Silixa channel-geometry campaign above.
DAS25_DATASET_ID = "INSTRUMENT-8f08939e9167bac57c"


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


def article_content(path: Path) -> str:
    """Extract only the publisher article body; preserve caption text and URLs."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'<div class="fl-post-content clearfix" itemprop="text">(.*?)</div><!-- \.fl-post-content -->', raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not locate OOI article body in {path}")
    body = match.group(1)
    # Retain publisher-provided destinations as citable retrieval paths before
    # flattening HTML, because a plain-text chunk otherwise loses each href.
    body = re.sub(
        r'(?is)<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        lambda found: f"{re.sub(r'(?s)<[^>]+>', ' ', found.group(2)).strip()} ({html.unescape(found.group(1))})",
        body,
    )
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(?:p|h2|li|ul|div)>", "\n", body)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body))
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()
    return re.sub(r"\s+([,.;:])", r"\1", text)


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
    entities, chunks, relationships, figures = [
        {"entity_id": DATASET_ID, "name": "2021 RCA OptaSense and Silixa DAS/DTS experiment",
         "entity_type": "instrument_reference", "source_is_untrusted_data": True},
        {"entity_id": DAS25_DATASET_ID, "name": "2025-2026 RCA Nokia MultiDAS and OptoDAS experiment",
         "entity_type": "instrument_reference", "source_is_untrusted_data": True},
    ], [], [], []
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
    article_path = next((path for path in (
        source_dir / ARTICLE_FILE,
        PROJECT_ROOT / "source_material/original_documents/OOI_DAS_2025" / ARTICLE_FILE,
    ) if path.is_file()), source_dir / ARTICLE_FILE)
    if article_path.is_file():
        article_sha = _sha256(article_path)
        article_source_id = _id("SOURCE-OOI-DAS25-ARTICLE", article_sha)
        source_rows.append({
            "source_id": article_source_id, "title": "Multi-Span Fiber Sensing Expands Reach of OOI Regional Cabled Array",
            "source_url": ARTICLE_URL, "source_file": ARTICLE_FILE, "sha256": article_sha,
            "source_kind": "official_ooi_news_article", "published": "2026-03-31", "source_is_untrusted_data": True,
        })
        document_id = _id("DOCUMENT-OOI-DAS25-ARTICLE", ARTICLE_URL)
        content = article_content(article_path)
        chunk_id = _id("OOI-DAS25-ARTICLE-CHUNK", article_sha)
        entities.append({"entity_id": document_id, "name": "Multi-Span Fiber Sensing Expands Reach of OOI Regional Cabled Array",
                         "entity_type": "official_ooi_article", "published": "2026-03-31", "source_is_untrusted_data": True})
        chunks.append({"chunk_id": chunk_id, "parent_id": document_id, "document_id": document_id, "position": 0,
                       "title": "Official OOI DAS25 deployment, data access, and mask summary", "text": content,
                       "word_count": len(content.split()), "source_ids": [article_source_id], "source_urls": [ARTICLE_URL], "source_is_untrusted_data": True})
        relationships.extend([
            {"relationship_id": _id("OOI-DAS25-ARTICLE-REL", document_id, "HAS_CHUNK", chunk_id), "source_id": document_id, "predicate": "HAS_CHUNK", "target_id": chunk_id, "evidence_source_ids": [article_source_id]},
            {"relationship_id": _id("OOI-DAS25-ARTICLE-REL", DAS25_DATASET_ID, "DOCUMENTED_BY", document_id), "source_id": DAS25_DATASET_ID, "predicate": "DOCUMENTED_BY", "target_id": document_id, "evidence_source_ids": [article_source_id]},
        ])
        figures.append({
            "figure_id": _id("FIGURE-OOI-DAS25", "multispan-map"), "title": "OOI RCA multi-span DAS cable coverage map",
            "caption": "Location of the OOI RCA cables off the Oregon coast, shown in red. The portions successfully interrogated with the Nokia multi-span system are black; white dashed lines show the OptoDAS first-span coverage on the south cable; repeaters are green.",
            "image_url": "https://oceanobservatories.org/wp-content/uploads/2026/04/multispan_ooi_website_map_plot-1-2048x794-1.jpeg",
            "source_url": ARTICLE_URL, "document_id": document_id, "source_id": article_source_id,
            "credit": "Z. Krauss, University of Washington", "source_is_untrusted_data": True,
        })
    _write_jsonl(output_dir / "channel_locations.jsonl", locations)
    _write_jsonl(output_dir / "sources.jsonl", source_rows)
    _write_jsonl(output_dir / "entities.jsonl", entities)
    _write_jsonl(output_dir / "chunks.jsonl", chunks)
    _write_jsonl(output_dir / "relationships.jsonl", relationships)
    if figures:
        _write_jsonl(output_dir / "figures.jsonl", figures)
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
        "counts": {"channel_locations": len(locations), "entities": len(entities), "chunks": len(chunks), "relationships": len(relationships), "figures": len(figures)},
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
