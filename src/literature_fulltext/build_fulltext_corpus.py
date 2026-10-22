#!/usr/bin/env python3
"""Build the full-text literature layer (data/LiteratureFullText) from the validated full-text cache.

The layer is a separate collection: the search leaves it out unless a request names it, and the Worker asks it only
for passages of papers the main search already found. So it adds evidence to a literature answer without crowding
instruments, websites or abstracts out of any answer. Its documents keep the literature catalog's IDs and source URLs,
so a passage cites the same paper, by the same link, as the paper's abstract.

Pages that are mostly a reference list, and fragments under 40 words, are left out. Passages are never shown to
readers; the Worker sends only their citations.

Graph: each paper HAS_FULLTEXT_PASSAGE its passages, and a passage MENTIONS the RCA sites and instruments it names,
by literal match only (no inference), with the matched words and page on the edge. Entities carry the names and
reference designators other collections use, so they resolve across the graph by identifier. A caldera or vent-field
name counts only where the passage also names Axial, so "central caldera" in a paper on another volcano does not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runtime_data/Literature/full_text_cache"
CATALOG = ROOT / "data/Literature/documents.jsonl"
OUTPUT = ROOT / "data/LiteratureFullText"
MIN_WORDS = 40
# Journal abbreviations, DOIs, volume/page marks and cited years per 100 words: a reference list scores 3 or more,
# running text 0-2 even where it cites heavily.
REFERENCE_MARK = re.compile(r"\b(?:Geophys|Res\.|Lett\.|J\. |Sci\.|Bull\.|Seismol|Geochem|Geosyst|Oceanogr|doi[:.]|"
                            r"https?://doi|Vol\.|pp\.|\bv\. \d)")
CITED_YEAR = re.compile(r"\(\d{4}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\.")
REFERENCE_SCORE = 3.0
# Publisher download stamps printed on every page ("Downloaded from https://www.science.org at University of
# Washington on September 22, 2026"; Wiley's longer one with its terms of use): noise that matched questions' words.
STAMPS = (
    re.compile(r"(?:\d{7,9}[0-9X]?,\s*\d{4},\s*\d+,\s*)?Downloaded from https?://\S+ by [^\[]{0,150}\[\d{2}/\d{2}/\d{4}\]\.?"
               r"\s*See the Terms and Conditions \(\S+?\) on Wiley Online Library for rules of use; OA articles are governed"
               r" by the applicable Creative Commons License\.?"),
    re.compile(r"Downloaded from \S+ (?:at|by) .{0,100}? on (?:[A-Z][a-z]+ \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]+ \d{4}"
               r"|\[\d{2}/\d{2}/\d{4}\])\.?"),
)


def unstamped(text: str) -> str:
    text = text.replace("\u200b", "")                     # zero-width spaces split GeoScienceWorld's stamp URLs
    for stamp in STAMPS:
        text = stamp.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
INSTRUMENTS = ROOT / "data/Instruments/instruments.jsonl"
REFDES = re.compile(r"\b(?:RS|CE)\d\d[A-Z0-9]{4}-[A-Z0-9]{5}-\d\d-[A-Z0-9]{9}\b")
# (entity id, name, aliases, needs an Axial mention in the same passage)
SITES = (
    ("SITE-axial-seamount", "Axial Seamount", ("Axial Seamount", "Axial Volcano"), False),
    ("SITE-axial-central-caldera", "Axial Seamount Central Caldera", ("Central Caldera",), True),
    ("SITE-axial-eastern-caldera", "Axial Seamount Eastern Caldera", ("Eastern Caldera",), True),
    ("SITE-axial-international-district", "Axial Seamount International District", ("International District",), True),
    ("SITE-ashes", "ASHES Hydrothermal Field, Axial Seamount", ("ASHES",), True),
    ("SITE-axial-base", "Axial Seamount Base", ("Axial Base",), False),
    ("SITE-southern-hydrate-ridge", "Southern Hydrate Ridge", ("Southern Hydrate Ridge",), False),
    ("SITE-hydrate-ridge", "Hydrate Ridge", ("Hydrate Ridge",), False),
    ("SITE-oregon-slope-base", "Oregon Slope Base", ("Oregon Slope Base", "Slope Base"), False),
    ("SITE-oregon-shelf", "Oregon Shelf", ("Oregon Shelf",), False),
    ("SITE-oregon-offshore", "Oregon Offshore", ("Oregon Offshore",), False),
)
SYSTEMS = (
    ("SYSTEM-covis", "Cabled Observatory Vent Imaging Sonar (COVIS)", ("COVIS", "Cabled Observatory Vent Imaging Sonar")),
    ("SYSTEM-botpt", "Bottom pressure and tilt instrument (BOTPT)", ("BOTPT",)),
    ("SYSTEM-regional-cabled-array", "OOI Regional Cabled Array", ("Regional Cabled Array", "Cabled Array")),
)
AXIAL = re.compile(r"\bAxial\b")


def _word(alias: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", 0 if alias.isupper() else re.I)


def entities(instruments: Path = INSTRUMENTS) -> tuple[list[dict], list[tuple]]:
    """The entity records, and the matchers: (entity id, kind, compiled alias, needs Axial)."""
    records, matchers = [], []
    for eid, name, aliases, axial in SITES:
        records.append({"entity_id": eid, "entity_type": "site", "name": name, "aliases": list(aliases)})
        matchers += [(eid, "site", _word(a), a, axial) for a in aliases]
    for eid, name, aliases in SYSTEMS:
        records.append({"entity_id": eid, "entity_type": "instrument_system", "name": name, "aliases": list(aliases)})
        matchers += [(eid, "instrument_system", _word(a), a, False) for a in aliases]
    known = {}
    for line in instruments.open(encoding="utf-8"):
        d = json.loads(line)
        for code in [d.get("canonical_id"), *(d.get("aliases") or [])]:
            if code and REFDES.fullmatch(code):
                known[code] = d
    for code, d in sorted(known.items()):
        records.append({"entity_id": code, "entity_type": "instrument", "name": d.get("name") or code,
                        "aliases": [code, d["instrument_id"]]})
    return records, matchers, set(known)


def mentions(text: str, matchers: list[tuple], refdes: set[str]) -> dict[str, str]:
    """entity id -> the literal words matched in this passage."""
    found: dict[str, str] = {}
    axial = bool(AXIAL.search(text))
    for eid, _, rx, literal, needs_axial in matchers:
        if eid not in found and (axial or not needs_axial) and rx.search(text):
            found[eid] = literal
    for code in REFDES.findall(text):
        if code in refdes:
            found.setdefault(code, code)
    return found


def reference_score(text: str) -> float:
    words = len(text.split())
    return (len(REFERENCE_MARK.findall(text)) + len(CITED_YEAR.findall(text))) / max(words, 1) * 100


def keep(text: str) -> bool:
    return len(text.split()) >= MIN_WORDS and reference_score(text) < REFERENCE_SCORE


# Places a paper is pinned to on the map: the atlas sites and instruments its passages name most, specific sites
# before the volcano, ridge or array they lie in.
GENERIC = {"SITE-axial-seamount", "SITE-hydrate-ridge"}
# A paper on the volcano or ridge as a whole is pinned at the atlas site that stands for it.
PIN_AS = {"SITE-axial-seamount": "Axial Seamount summit caldera", "SITE-hydrate-ridge": "Southern Hydrate Ridge"}
MAX_PLACES = 3


def paper_places(counts: Counter, names: dict[str, str]) -> list[str]:
    def rank(eid):
        return (eid in GENERIC, -counts[eid], eid)
    pinnable = [e for e in counts if e.startswith("SITE-") or REFDES.fullmatch(e)]
    places = []
    for e in sorted(pinnable, key=rank):
        name = PIN_AS.get(e, names[e])
        if name not in places:
            places.append(name)
    return places[:MAX_PLACES]


def paper_keys(work: dict) -> list[str]:
    """How the Worker names a paper it found: its DOI (lowercase, no resolver prefix) and its catalog ID."""
    doi = (work.get("doi") or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return [k for k in (doi, work["document_id"]) if k]


def build(cache: Path = CACHE, catalog: Path = CATALOG, output: Path = OUTPUT) -> dict:
    works = {}
    for line in catalog.open(encoding="utf-8"):
        d = json.loads(line)
        works[d["document_id"]] = d
    documents, chunks, dropped = [], [], {"short": 0, "references": 0}
    entity_records, matchers, refdes = entities()
    names = {e["entity_id"]: e["name"] for e in entity_records}
    relationships, used, seen = [], set(), set()
    for meta_path in sorted(cache.glob("*/metadata.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        work = works.get(meta["work_id"])
        chunk_path = meta_path.parent / "chunks.jsonl"
        if not work or not chunk_path.exists():
            continue
        kept = []
        for line in chunk_path.open(encoding="utf-8"):
            c = json.loads(line)
            text = unstamped(re.sub(r"\s+", " ", c.get("text") or ""))
            if c["chunk_id"] in seen:              # a page whose text repeats verbatim has the same ID
                continue
            seen.add(c["chunk_id"])
            if len(text.split()) < MIN_WORDS:
                dropped["short"] += 1
            elif not keep(text):
                dropped["references"] += 1
            else:
                kept.append((c, text))
        if not kept:
            continue
        documents.append({
            "document_id": work["document_id"], "title": work["title"], "doi": work.get("doi"),
            "publication_year": work.get("publication_year"), "citation": work.get("citation"),
            "source_url": work.get("source_url"), "text_source": meta.get("source_origin"),
            "document_sha256": meta.get("sha256"), "source_is_untrusted_data": True,
        })
        found = [(c, text, mentions(text, matchers, refdes)) for c, text in kept]
        counts = Counter(eid for _, _, m in found for eid in m)
        places = paper_places(counts, names)
        keys = paper_keys(work)
        documents[-1]["places"] = places
        for c, text, m in found:
            relationships.append({"source_id": work["document_id"], "predicate": "HAS_FULLTEXT_PASSAGE", "target_id": c["chunk_id"]})
            for eid, literal in m.items():
                used.add(eid)
                relationships.append({"source_id": c["chunk_id"], "predicate": "MENTIONS", "target_id": eid,
                                      "evidence": {"literal": literal, "page": c.get("page"), "source_sha256": meta.get("sha256")}})
            chunks.append({
                "paper_keys": keys, "places": places,
                "chunk_id": c["chunk_id"], "document_id": work["document_id"], "title": work["title"],
                "doi": work.get("doi"), "source_url": work.get("source_url"), "page": c.get("page"),
                "locator": f"page {c['page']}" if c.get("page") else None, "section_heading": c.get("section"),
                "position": c.get("position"), "content_kind": "full_text", "text": text,
                "source_is_untrusted_data": True,
            })
    entity_records = [{**e, "source_is_untrusted_data": False} for e in entity_records if e["entity_id"] in used]
    output.mkdir(parents=True, exist_ok=True)
    for name, records in (("documents.jsonl", documents), ("chunks.jsonl", chunks), ("entities.jsonl", entity_records),
                          ("relationships.jsonl", relationships)):
        with (output / name).open("w", encoding="utf-8") as stream:
            for r in records:
                stream.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Full text of literature-catalog papers, a retrieval layer searched only for papers already found",
        "embedding_input": "chunks.jsonl", "graph_node_inputs": ["documents.jsonl", "chunks.jsonl", "entities.jsonl"],
        "graph_edge_input": "relationships.jsonl",
        "counts": {"documents": len(documents), "chunks": len(chunks), "entities": len(entity_records),
                   "relationships": len(relationships), "dropped": dropped},
        "chunks_sha256": hashlib.sha256((output / "chunks.jsonl").read_bytes()).hexdigest(),
        "limitations": [
            "Passages are evidence for answers only; they are never shown to readers, who follow the paper's link.",
            "Text is extracted from PDFs (some user-supplied under license) and may contain extraction errors.",
            "Reference-list pages and fragments under 40 words are left out.",
            "MENTIONS edges are literal name or reference-designator matches, not judgements of relevance.",
        ],
        "validation_status": "pass",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest["counts"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()
    print(json.dumps(build(output=args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
