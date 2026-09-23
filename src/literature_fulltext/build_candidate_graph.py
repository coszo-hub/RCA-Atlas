#!/usr/bin/env python3
"""Build a conservative full-text literature-to-RCA candidate graph.

This is deliberately deterministic: a relationship is emitted only when a
stable instrument/site identifier or a carefully bounded alias occurs in an
extracted full-text page.  Candidate edges retain the page, literal matched,
source-document digest, and target's canonical Atlas identifier.  They are not
silently merged into the authoritative graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runtime_data/Literature/full_text_cache"
OUTPUT = ROOT / "runtime_data/Literature/fulltext_candidate_graph"
INSTRUMENT_FILES = (ROOT / "data/Instruments/instruments.jsonl", ROOT / "data/PIPortal/instruments.jsonl")
SITE_FILES = (ROOT / "data/PIPortal/sites.jsonl",)


def rows(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def stable_id(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def identifier_aliases(record: dict) -> list[str]:
    """Return only identifier-like aliases; prose labels create false edges."""
    values = [record.get(key) for key in ("canonical_id", "shared_canonical_id", "portal_instrument_key", "reference_designator", "instrument_code")]
    values.extend(record.get("aliases") or [])
    output=[]
    for value in values:
        text=str(value or "").strip()
        if re.fullmatch(r"(?=.*\d)[A-Za-z][A-Za-z0-9-]{4,}", text) and text not in output:
            output.append(text)
    return output


def site_aliases(record: dict) -> list[str]:
    values=[record.get("name"), *(record.get("aliases") or [])]
    output=[]
    for value in values:
        text=" ".join(str(value or "").split()).strip(" ,.;")
        # Named places are accepted only when sufficiently specific.  Short
        # codes are excluded here; they are handled as instrument identifiers.
        if len(text) >= 12 and any(ch.isalpha() for ch in text) and text not in output:
            output.append(text)
    return output


def literal_matches(text: str, aliases: list[str]):
    folded=text.casefold()
    for alias in aliases:
        pattern=r"(?<![A-Za-z0-9_-])" + re.escape(alias.casefold()) + r"(?![A-Za-z0-9_-])"
        if re.search(pattern, folded):
            yield alias


def entities():
    output={}
    for path in INSTRUMENT_FILES:
        for record in rows(path):
            local_id=record.get("instrument_id")
            if not local_id:
                continue
            existing=output.get(local_id)
            candidate={
                "entity_id":local_id, "entity_type":"instrument", "name":record.get("name") or local_id,
                "canonical_id":record.get("canonical_id"), "external_collection":"instruments" if "Instruments" in str(path) else "pi_portal",
                "external_local_id":local_id, "aliases":identifier_aliases(record), "source_is_untrusted_data":True,
            }
            if existing:
                candidate["aliases"] = sorted(set(existing["aliases"]) | set(candidate["aliases"]))
            output[local_id]=candidate
    for path in SITE_FILES:
        for record in rows(path):
            local_id=record.get("site_id")
            if not local_id:
                continue
            output[local_id]={
                "entity_id":local_id, "entity_type":"site", "name":record.get("name") or local_id,
                "external_collection":"pi_portal", "external_local_id":local_id,
                "aliases":site_aliases(record), "source_is_untrusted_data":True,
            }
    return [entity for entity in output.values() if entity["aliases"]]


def build(cache: Path, output: Path) -> dict:
    target_entities=entities()
    instrument_alias_index={}
    site_targets=[]
    for target in target_entities:
        if target["entity_type"] == "instrument":
            for alias in target["aliases"]:
                instrument_alias_index.setdefault(alias.casefold(), []).append((target, alias))
        else:
            site_targets.append(target)
    ambiguous_instrument_aliases={alias for alias, targets in instrument_alias_index.items() if len({target["entity_id"] for target, _ in targets}) > 1}
    instrument_alias_index={alias:targets for alias, targets in instrument_alias_index.items() if alias not in ambiguous_instrument_aliases}
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    documents=[]; pages=[]; relationships=[]; used_targets={}; seen_edges=set()
    for metadata_path in sorted(cache.glob("*/metadata.json")):
        metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
        work_id=metadata["work_id"]
        documents.append({"document_id":work_id,"title":metadata.get("title"),"doi":metadata.get("doi"),
                          "full_text_sha256":metadata["sha256"],"source_origin":metadata.get("source_origin","public_web"),
                          "source_url":metadata.get("source_url"),"source_descriptor":metadata.get("source_descriptor"),
                          "source_is_untrusted_data":True})
        for line in (metadata_path.parent / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
            page=json.loads(line)
            page_id=page["chunk_id"]
            pages.append({"page_id":page_id,"document_id":work_id,"title":metadata.get("title"),"page":page.get("page"),
                          "section":page.get("section"),"text":page["text"],"source_sha256":metadata["sha256"],
                          "source_is_untrusted_data":True})
            relationships.append({"source_id":work_id,"predicate":"HAS_FULLTEXT_PASSAGE","target_id":page_id,
                                  "evidence":{"source_sha256":metadata["sha256"],"page":page.get("page"),"section":page.get("section")}})
            section=(page.get("section") or "").casefold()
            if any(term in section for term in ("reference", "bibliography", "acknowledg")):
                continue
            matches=[]
            # Most instrument aliases are reference-designator-like tokens.
            # Token lookup avoids testing every Atlas identifier against every
            # full-text page (millions of needless regular expressions).
            for token in set(re.findall(r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9-]{4,}(?![A-Za-z0-9_-])", page["text"])):
                matches.extend(instrument_alias_index.get(token.casefold(), []))
            for target in site_targets:
                matches.extend((target, alias) for alias in literal_matches(page["text"], target["aliases"]))
            for target, matched in matches:
                key=(page_id,target["entity_id"])
                if key in seen_edges:
                    continue
                seen_edges.add(key); used_targets[target["entity_id"]]=target
                relationships.append({"source_id":page_id,"predicate":"EXPLICITLY_MENTIONS_" + target["entity_type"].upper(),
                                      "target_id":target["entity_id"],"match_method":"bounded_literal_identifier" if target["entity_type"] == "instrument" else "bounded_literal_place_name",
                                      "matched_literal":matched,"confidence":1.0,
                                      "evidence":{"source_sha256":metadata["sha256"],"page":page.get("page"),"section":page.get("section"),"passage_id":page_id}})
    write_jsonl(output / "documents.jsonl", documents)
    write_jsonl(output / "pages.jsonl", pages)
    write_jsonl(output / "entities.jsonl", sorted(used_targets.values(), key=lambda item:item["entity_id"]))
    write_jsonl(output / "relationships.jsonl", relationships)
    counts=Counter(edge["predicate"] for edge in relationships)
    manifest={"schema_version":"1.0-candidate","method":"deterministic_literal_match_only","documents":len(documents),"pages":len(pages),
              "entities":len(used_targets),"relationships":len(relationships),"relationship_predicates":dict(sorted(counts.items())),
              "excluded_ambiguous_instrument_aliases":len(ambiguous_instrument_aliases),
              "source_cache":str(cache.relative_to(ROOT))}
    (output / "manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,default=CACHE)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    print(json.dumps(build(args.cache,args.output),indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
