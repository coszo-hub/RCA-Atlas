#!/usr/bin/env python3
"""Build the graph-ready corpus for OSU's Axial monitoring landing page.

The source page is deliberately archived first under ``source_material``.  This
builder does not fetch the web, so rebuilding is reproducible from that source
snapshot.  It represents changing plots as public live endpoints, not frozen
scientific observations.  The page says the plots refresh every 15 minutes and
are pre-QA; both constraints remain in the generated evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from axial_monitoring_tools import TOOL_SCHEMAS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "source_material/original_documents/AxialCEOAS/index.html"
DEFAULT_OUTPUT = ROOT / "data/AxialMonitoring"
PAGE_URL = "https://axial.ceoas.oregonstate.edu/index.html"

STREAMS = (
    ("BOTPT-A301-MJ03F", "BOTPT-A301-MJ03F — Central Caldera", "Central Caldera", "mj03f.html"),
    ("BOTPT-A302-MJ03E", "BOTPT-A302-MJ03E — Eastern Caldera", "Eastern Caldera", "mj03e.html"),
    ("BOTPT-A303-MJ03D", "BOTPT-A303-MJ03D — International District", "International District", "mj03d.html"),
    ("BOTPT-A304-MJ03B", "BOTPT-A304-MJ03B — ASHES Vent Field", "ASHES Hydrothermal Field", "mj03b.html"),
    ("CTDPFB304-MJ03B", "ASHES Seafloor CTD (MJ03B-CTDPFB304)", "ASHES Hydrothermal Field", "CTD.html"),
    ("CTDPFB306-MJ03E", "Eastern Seafloor CTD (MJ03E-CTDPFB306)", "Eastern Caldera", "CTD2.html"),
    ("CTDPFB305-MJ03F", "Central Seafloor CTD (MJ03F-CTDPFB305)", "Central Caldera", "CTD3.html"),
    ("CTDPFB307-MJ03D", "Int. Dist. Seafloor CTD (MJ03D-CTDPFB307)", "International District", "CTD4.html"),
)
PRODUCTS = (
    ("Differential Uplift Rate from MJ03E-F", "diffs.html", "derived_plot"),
    ("Long-Term Rates of Uplift (BPR data)", "rates.html", "derived_plot"),
    ("Long-Term Rates of Tilt (LILY data)", "tilt.html", "derived_plot"),
    ("Event Alarms", "alarms.html", "operational_alarm_page"),
    ("Inflation Forecasts — Method 1", "Forecasts.html", "forecast"),
    ("Inflation Forecasts — Method 2", "Forecasts2.html", "forecast"),
    ("Inflation Forecasts — Method 3", "Forecasts3.html", "forecast"),
    ("Inflation Forecasts — Method 4", "Forecasts4.html", "forecast"),
    ("Axial eruption status", "https://axial.ceoas.oregonstate.edu/status/", "status_page"),
)


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def clean_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def build(source: Path, output: Path) -> None:
    raw = source.read_text(encoding="utf-8", errors="replace")
    source_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    text = clean_html(raw)
    if "Realtime data from the OOI instruments at Axial Seamount" not in text:
        raise ValueError("Expected Axial CEOAS landing-page title was not found")

    output.mkdir(parents=True, exist_ok=True)
    (output / "text").mkdir(exist_ok=True)
    page_id = stable_id("PAGE", PAGE_URL)
    source_id = stable_id("SOURCE", PAGE_URL)
    chunk_id = f"{page_id}-CHUNK-001"
    text_path = output / "text" / f"{page_id}.md"
    text_path.write_text(text + "\n", encoding="utf-8")

    pages = [{
        "page_id": page_id, "url": PAGE_URL, "title": "Realtime data from the OOI instruments at Axial Seamount",
        "site_host": "axial.ceoas.oregonstate.edu", "source_format": "static_html",
        "selection_reason": "RCA Axial operational monitoring and public data links",
        "content_sha256": source_sha, "text_path": text_path.relative_to(output).as_posix(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "text_source": "public_web_page",
        "source_is_untrusted_data": True,
        "data_caveat": "The publisher labels these as pre-commissioned data not through Quality Assurance checks.",
    }]
    chunks = [{
        "chunk_id": chunk_id, "page_id": page_id, "source_url": PAGE_URL,
        "title": pages[0]["title"], "section_heading": "Axial monitoring landing page",
        "position": 0, "word_count": len(text.split()), "text": text,
        "source_is_untrusted_data": True,
    }]
    sources = [{
        "source_id": source_id, "name": "Oregon State University Axial monitoring website",
        "url": PAGE_URL, "publisher": "Oregon State University CEOAS", "access": "public",
        "content_sha256": source_sha, "retrieved_at": pages[0]["retrieved_at"],
        "rights_note": "Source URL and attribution retained; live plots remain at the publisher.",
    }]
    entities: list[dict] = []
    endpoints: list[dict] = []
    relationships = [
        {"source_id": page_id, "predicate": "HAS_CHUNK", "target_id": chunk_id},
        {"source_id": page_id, "predicate": "SOURCED_FROM", "target_id": source_id},
    ]
    site_ids: dict[str, str] = {}
    for stream_key, name, site, href in STREAMS:
        stream_id = stable_id("AXIAL-STREAM", stream_key)
        site_id = site_ids.setdefault(site, stable_id("AXIAL-SITE", site))
        if not any(row["entity_id"] == site_id for row in entities):
            entities.append({"entity_id": site_id, "name": site, "type": "Axial Seamount monitoring site", "method": "publisher_named_location"})
        entities.append({
            "entity_id": stream_id, "name": name, "type": "instrument_stream",
            "canonical_id": stream_key, "method": "publisher_named_instrument_stream",
            "data_caveat": "Live plot source; publisher says pre-commissioned data have not passed QA.",
        })
        endpoint_id = stable_id("AXIAL-ENDPOINT", href)
        endpoints.append({"endpoint_id": endpoint_id, "name": name + " live plot", "url": urljoin(PAGE_URL, href), "endpoint_type": "public_live_plot", "refresh_cadence": "publisher states updated every 15 minutes", "access": "public"})
        relationships.extend((
            {"source_id": chunk_id, "predicate": "MENTIONS", "target_id": stream_id},
            {"source_id": stream_id, "predicate": "LOCATED_AT", "target_id": site_id},
            {"source_id": stream_id, "predicate": "LIVE_DATA_AVAILABLE_AT", "target_id": endpoint_id},
        ))
    for name, href, endpoint_type in PRODUCTS:
        endpoint_id = stable_id("AXIAL-ENDPOINT", href)
        endpoints.append({"endpoint_id": endpoint_id, "name": name, "url": urljoin(PAGE_URL, href), "endpoint_type": endpoint_type, "access": "public", "data_caveat": "Interpret changing status, alarms, forecasts, and plots as live publisher content."})
        relationships.append({"source_id": page_id, "predicate": "LINKS_TO", "target_id": endpoint_id})

    write_jsonl(output / "pages.jsonl", pages)
    write_jsonl(output / "chunks.jsonl", chunks)
    write_jsonl(output / "sources.jsonl", sources)
    write_jsonl(output / "entities.jsonl", entities)
    write_jsonl(output / "endpoints.jsonl", endpoints)
    write_jsonl(output / "relationships.jsonl", relationships)
    write_jsonl(output / "tools.jsonl", TOOL_SCHEMAS)
    ids = {page_id, chunk_id, source_id} | {row["entity_id"] for row in entities} | {row["endpoint_id"] for row in endpoints}
    unresolved = [row for row in relationships if row["source_id"] not in ids or row["target_id"] not in ids]
    validation = {"status": "pass" if not unresolved else "fail", "checks": {"all_relationship_endpoints_resolve": not unresolved, "landing_page_title_verified": True, "all_live_endpoints_are_public_urls": all(row["url"].startswith("https://") for row in endpoints)}, "counts": {"pages": len(pages), "chunks": len(chunks), "sources": len(sources), "entities": len(entities), "endpoints": len(endpoints), "relationships": len(relationships)}, "problems": {"unresolved_relationships": unresolved}}
    (output / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "scope": "OSU Axial Seamount operational monitoring landing page and public live endpoints", "source_input": source.relative_to(ROOT).as_posix(), "embedding_input": "chunks.jsonl", "graph_node_inputs": ["pages.jsonl", "chunks.jsonl", "sources.jsonl", "entities.jsonl", "endpoints.jsonl"], "graph_edge_input": "relationships.jsonl", "live_tool_manifest": "tools.jsonl", "validation_status": validation["status"], "counts": {**validation["counts"], "tools": len(TOOL_SCHEMAS)}, "limitations": ["Only the landing page is archived in this collection; linked live pages are represented as endpoints.", "Live plots, alarms, forecasts, and status are not frozen observations and should be refreshed only when a user requests current information.", "Publisher labels the data as pre-commissioned and not through Quality Assurance checks."]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# OSU Axial monitoring corpus\n\nThis collection archives the Axial CEOAS landing page and represents its live monitoring links as public endpoints. It is intentionally not a snapshot of the changing plots. See `manifest.json` for caveats and provenance.\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
