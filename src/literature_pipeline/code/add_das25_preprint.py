#!/usr/bin/env python3
"""Add the verified DAS25 ESS Open Archive preprint to the canonical catalog.

The publisher can block automated full-text requests.  This preserves only
Crossref's public bibliographic metadata and abstract, with the original DOI
and a checksum of the retrieved metadata response.  It does not claim the
publisher PDF was downloaded.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOI = "10.22541/essoar.15004068/v1"
WORK_ID = "OOI-DAS-2026-001"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/Literature/literature.jsonl")
    parser.add_argument("--metadata", type=Path, default=ROOT / "source_material/original_documents/Literature/essoar_15004068_v1_crossref.json")
    args = parser.parse_args()
    works = [json.loads(line) for line in args.catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any((row.get("resolved_doi") or "").casefold() == DOI for row in works):
        print(json.dumps({"status": "already_present", "doi": DOI}))
        return 0
    raw = args.metadata.read_bytes()
    source = json.loads(raw)["message"]
    abstract = html.unescape(source.get("abstract") or "")
    import re
    abstract = " ".join(re.sub(r"<[^>]+>", " ", abstract).split())
    authors = [f"{author.get('given', '').strip()} {author.get('family', '').strip()}".strip() for author in source["author"]]
    title = source["title"][0]
    published = source["published"]["date-parts"][0]
    date = "-".join(str(part).zfill(2) for part in published)
    citation = f"{', '.join(authors)}. ({date}). {title}. ESS Open Archive. https://doi.org/{DOI}"
    occurrence = {
        "occurrence_id": "CROSSREF-ESSOAR-15004068-V1", "canonical_id": WORK_ID,
        "citation": citation, "doi": DOI, "collection_name": "RCA DAS literature audit",
        "source_url": f"https://api.crossref.org/works/{DOI}", "match_method": "verified_crossref_doi",
    }
    works.append({
        "id": WORK_ID, "canonical_id": WORK_ID, "duplicate_of": None,
        "citation": citation, "citation_as_extracted": citation, "year_as_cited": str(published[0]),
        "resource_type": "preprint", "resource_type_status": "verified_crossref_type",
        "dois_as_cited": [DOI], "source_links": [{"url": f"https://doi.org/{DOI}", "provenance": "Crossref DOI", "verification_status": "retrieved"}],
        "resolved_title": title, "resolved_doi": DOI, "paper_url": f"https://doi.org/{DOI}",
        "abstract": abstract, "abstract_status": "retrieved_from_crossref",
        "full_text_url": source.get("link", [{}])[0].get("URL"), "full_text_status": "publisher_access_blocked_automated_retrieval",
        "resolved_authors": authors, "publication_year": published[0],
        "abstract_source_url": f"https://api.crossref.org/works/{DOI}", "metadata_source_url": f"https://api.crossref.org/works/{DOI}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "license": None,
        "source_rights": "Copyright status must be checked at the publisher; no full text stored.",
        "provenance": {"source_document": args.metadata.name, "source_sha256": hashlib.sha256(raw).hexdigest(), "method": "verified_crossref_doi"},
        "notes": "Explicitly documents the 2025-2026 RCA Nokia multi-span and conventional OptoDAS deployment; full text was not ingested because ESS Open Archive returned an automated-access challenge.",
        "source_occurrence_ids": [occurrence["occurrence_id"]], "source_occurrences": [occurrence], "source_occurrence_count": 1,
        "schema_version": "1.3-runtime",
    })
    args.catalog.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in works), encoding="utf-8")
    print(json.dumps({"status": "added", "work_id": WORK_ID, "doi": DOI, "works": len(works)}))


if __name__ == "__main__":
    raise SystemExit(main())
