#!/usr/bin/env python3
"""Build a conservative, provenance-preserving Zotero/literature dedup audit."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import unquote


ROOT = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent")
ZOTERO_PATHS = [
    ROOT / "tmp/coszo_products/zotero_E5UH7L89_top1.json",
    ROOT / "tmp/coszo_products/zotero_RMTSE2IH_top1.json",
    ROOT / "tmp/coszo_products/zotero_RMTSE2IH_top2.json",
]
LITERATURE_PATH = Path(
    "/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_literature.jsonl"
)
OUTPUT_PATH = ROOT / "tmp/zotero_expansion/dedup_audit.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_doi(value: object) -> str | None:
    if not value:
        return None
    text = unquote(str(value)).strip().lower()
    text = re.sub(r"^(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)", "", text)
    text = text.strip().rstrip(".,;)")
    return text or None


def normalize_title(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def year_from(value: object) -> int | None:
    m = re.search(r"\b(18|19|20)\d{2}\b", str(value or ""))
    return int(m.group(0)) if m else None


def zotero_author_surnames(data: dict) -> list[str]:
    names = []
    for creator in data.get("creators", []):
        if creator.get("creatorType") != "author":
            continue
        name = creator.get("lastName") or creator.get("name")
        if name:
            names.append(normalize_title(name))
    return names


def existing_author_segment(record: dict) -> str:
    citation = record.get("citation") or record.get("citation_as_cited") or ""
    return re.split(r"\((?:18|19|20)\d{2}[a-z]?\)", citation, maxsplit=1)[0]


def author_support(zotero_surnames: list[str], existing: dict) -> dict:
    segment = normalize_title(existing_author_segment(existing))
    supported = [name for name in zotero_surnames if re.search(rf"\b{re.escape(name)}\b", segment)]
    return {
        "zotero_author_surnames": zotero_surnames,
        "supported_in_existing_citation": supported,
        "all_zotero_authors_supported": bool(zotero_surnames)
        and len(supported) == len(zotero_surnames),
        "first_author_supported": bool(zotero_surnames)
        and bool(supported)
        and supported[0] == zotero_surnames[0],
    }


def version_evidence(existing: dict, doi: str | None) -> list[dict]:
    if not doi:
        return []
    evidence = []
    for entry in existing.get("verified_metadata", []) or []:
        if normalize_doi(entry.get("doi")) == doi:
            evidence.append(
                {
                    "source": entry.get("source"),
                    "url": entry.get("url"),
                    "doi": doi,
                    "relationship": entry.get("relationship"),
                    "title": entry.get("title"),
                }
            )
    return evidence


def occurrence_id(source_file: str, index_1_based: int) -> str:
    return f"{source_file}#{index_1_based}"


def main() -> None:
    existing = [json.loads(line) for line in LITERATURE_PATH.read_text().splitlines() if line.strip()]
    existing_by_doi: dict[str, list[dict]] = defaultdict(list)
    for record in existing:
        doi = normalize_doi(record.get("resolved_doi") or record.get("doi_as_cited"))
        if doi:
            existing_by_doi[doi].append(record)

    occurrences = []
    for path in ZOTERO_PATHS:
        doc = json.loads(path.read_text())
        items = doc if isinstance(doc, list) else doc["items"]
        collection_key = re.search(r"zotero_([^_]+)_top", path.name).group(1)
        for idx, item in enumerate(items, 1):
            data = item["data"]
            occurrences.append(
                {
                    "occurrence_id": occurrence_id(path.name, idx),
                    "source_file": str(path),
                    "source_index_1_based": idx,
                    "collection_key": collection_key,
                    "zotero_key": item["key"],
                    "zotero_version": item.get("version"),
                    "item_type": data.get("itemType"),
                    "title": data.get("title"),
                    "normalized_title": normalize_title(data.get("title")),
                    "doi_as_stored": data.get("DOI") or None,
                    "normalized_doi": normalize_doi(data.get("DOI")),
                    "date_as_stored": data.get("date") or None,
                    "year": year_from(data.get("date")),
                    "author_surnames": zotero_author_surnames(data),
                    "url_as_stored": data.get("url") or None,
                }
            )

    occurrences_by_key: dict[str, list[dict]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_key[occurrence["zotero_key"]].append(occurrence)

    # Detect cross-collection duplicates by work identity, not merely repeated
    # Zotero key. DOI is authoritative; records without a DOI must agree on the
    # normalized title, year, and ordered author surnames.
    cross_collection_duplicates = []
    duplicate_group_by_key = {}
    cross_identity_groups: dict[tuple, list[dict]] = defaultdict(list)
    for occurrence in occurrences:
        if occurrence["normalized_doi"]:
            identity = ("normalized_doi", occurrence["normalized_doi"])
        else:
            identity = (
                "title_year_authors",
                occurrence["normalized_title"],
                occurrence["year"],
                tuple(occurrence["author_surnames"]),
            )
        cross_identity_groups[identity].append(occurrence)
    for identity, group in sorted(cross_identity_groups.items(), key=lambda x: repr(x[0])):
        collections = sorted({x["collection_key"] for x in group})
        if len(collections) <= 1:
            continue
        signatures = {
            (x["normalized_title"], x["normalized_doi"], tuple(x["author_surnames"]), x["year"])
            for x in group
        }
        keys = sorted({x["zotero_key"] for x in group})
        result = {
            "identity_basis": identity[0],
            "zotero_keys": keys,
            "collections": collections,
            "occurrences": [x["occurrence_id"] for x in group],
            "title": group[0]["title"],
            "normalized_doi": group[0]["normalized_doi"],
            "metadata_consistent_across_occurrences": len(signatures) == 1,
            "decision": "cross_collection_duplicate" if len(signatures) == 1 else "ambiguous_repeated_key",
        }
        cross_collection_duplicates.append(result)
        for key in keys:
            duplicate_group_by_key[key] = result

    existing_matches = []
    matched_key_to_result = {}
    candidate_pairs = []

    # Work at unique Zotero-key level so collection overlap does not inflate matches.
    for key, group in sorted(occurrences_by_key.items()):
        zotero = group[0]
        doi = zotero["normalized_doi"]
        match = None

        if doi and doi in existing_by_doi:
            targets = existing_by_doi[doi]
            # A DOI collision within the existing corpus would itself be ambiguous.
            if len(targets) == 1:
                target = targets[0]
                match = {
                    "zotero_key": key,
                    "occurrences": [x["occurrence_id"] for x in group],
                    "collections": sorted({x["collection_key"] for x in group}),
                    "zotero_title": zotero["title"],
                    "zotero_doi": doi,
                    "zotero_year": zotero["year"],
                    "existing_id": target["id"],
                    "existing_title": target.get("resolved_title"),
                    "existing_doi": normalize_doi(target.get("resolved_doi")),
                    "existing_year": year_from(target.get("resolved_year") or target.get("year_as_cited")),
                    "match_type": "normalized_doi_exact",
                    "title_similarity": round(
                        SequenceMatcher(
                            None,
                            zotero["normalized_title"],
                            normalize_title(target.get("resolved_title")),
                        ).ratio(),
                        6,
                    ),
                    "decision": "same_work_existing_record",
                }
        else:
            ranked = []
            for target in existing:
                similarity = SequenceMatcher(
                    None,
                    zotero["normalized_title"],
                    normalize_title(target.get("resolved_title")),
                ).ratio()
                if similarity >= 0.94:
                    authors = author_support(zotero["author_surnames"], target)
                    target_year = year_from(target.get("resolved_year") or target.get("year_as_cited"))
                    ranked.append(
                        {
                            "existing": target,
                            "title_similarity": similarity,
                            "author_support": authors,
                            "existing_year": target_year,
                            "version_evidence": version_evidence(target, doi),
                        }
                    )
            ranked.sort(key=lambda x: x["title_similarity"], reverse=True)
            for candidate in ranked:
                candidate_pairs.append((zotero, candidate))
            # Different DOI is accepted only with near-exact title, same year,
            # complete author support, and explicit version metadata in the
            # existing record naming this Zotero DOI.
            qualified = [
                x
                for x in ranked
                if x["title_similarity"] >= 0.99
                and x["existing_year"] == zotero["year"]
                and x["author_support"]["all_zotero_authors_supported"]
                and x["version_evidence"]
            ]
            if len(qualified) == 1:
                candidate = qualified[0]
                target = candidate["existing"]
                match = {
                    "zotero_key": key,
                    "occurrences": [x["occurrence_id"] for x in group],
                    "collections": sorted({x["collection_key"] for x in group}),
                    "zotero_title": zotero["title"],
                    "zotero_doi": doi,
                    "zotero_year": zotero["year"],
                    "existing_id": target["id"],
                    "existing_title": target.get("resolved_title"),
                    "existing_doi": normalize_doi(target.get("resolved_doi")),
                    "existing_year": candidate["existing_year"],
                    "match_type": "same_work_different_version",
                    "title_similarity": round(candidate["title_similarity"], 6),
                    "author_support": candidate["author_support"],
                    "version_evidence_from_existing_record": candidate["version_evidence"],
                    "decision": "same_work_existing_record",
                }

        if match:
            existing_matches.append(match)
            matched_key_to_result[key] = match

    ambiguous_cases = []
    for zotero, candidate in candidate_pairs:
        key = zotero["zotero_key"]
        target = candidate["existing"]
        if key in matched_key_to_result:
            continue
        # These are surfaced rather than silently matched. The date-span case is
        # resolvable as distinct; any future high-similarity case remains open.
        decision = "needs_manual_review"
        reason = (
            "Near-title candidate did not meet the conservative title+year+authors+version-evidence rule."
        )
        if (
            key == "U9ERWZJH"
            and target.get("id") == "COSZO-REF-084"
            and zotero["normalized_doi"] == "10.1002/2016ea000190"
        ):
            decision = "distinct_works"
            reason = (
                "The titles identify different observation intervals (2013–2014 versus "
                "2018–2021), and the records have different DOIs and publication years. "
                "They are related Axial Seamount pressure-series papers, not duplicate records."
            )
        ambiguous_cases.append(
            {
                "zotero_key": key,
                "occurrences": [x["occurrence_id"] for x in occurrences_by_key[key]],
                "zotero_title": zotero["title"],
                "zotero_doi": zotero["normalized_doi"],
                "zotero_year": zotero["year"],
                "zotero_authors": zotero["author_surnames"],
                "candidate_existing_id": target["id"],
                "candidate_existing_title": target.get("resolved_title"),
                "candidate_existing_doi": normalize_doi(target.get("resolved_doi")),
                "candidate_existing_year": candidate["existing_year"],
                "title_similarity": round(candidate["title_similarity"], 6),
                "author_support": candidate["author_support"],
                "decision": decision,
                "reason": reason,
            }
        )

    ambiguous_by_key = defaultdict(list)
    for case in ambiguous_cases:
        ambiguous_by_key[case["zotero_key"]].append(case)

    item_dispositions = []
    for occurrence in occurrences:
        key = occurrence["zotero_key"]
        if key in matched_key_to_result:
            status = "existing_match"
            rationale = matched_key_to_result[key]["match_type"]
        elif ambiguous_by_key.get(key):
            decisions = {x["decision"] for x in ambiguous_by_key[key]}
            status = (
                "reviewed_distinct_near_match"
                if decisions == {"distinct_works"}
                else "ambiguous_near_match"
            )
            rationale = "; ".join(sorted(decisions))
        else:
            status = "unmatched_expansion_candidate"
            rationale = "No supported normalized-DOI or near-exact title+authors/year/version match."
        item_dispositions.append(
            {
                **occurrence,
                "cross_collection_duplicate": key in duplicate_group_by_key,
                "audit_status": status,
                "existing_match": (
                    {
                        "existing_id": matched_key_to_result[key]["existing_id"],
                        "match_type": matched_key_to_result[key]["match_type"],
                    }
                    if key in matched_key_to_result
                    else None
                ),
                "rationale": rationale,
            }
        )

    unique_items = len(occurrences_by_key)
    matched_unique = len(matched_key_to_result)
    matched_occurrences = sum(len(x["occurrences"]) for x in existing_matches)
    duplicate_occurrences = sum(len(x["occurrences"]) for x in cross_collection_duplicates)
    redundant_occurrences = sum(len(x["occurrences"]) - 1 for x in cross_collection_duplicates)
    unresolved_ambiguous_keys = {
        x["zotero_key"] for x in ambiguous_cases if x["decision"] == "needs_manual_review"
    }
    reviewed_distinct_keys = {
        x["zotero_key"] for x in ambiguous_cases if x["decision"] == "distinct_works"
    }

    audit = {
        "audit_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "zotero_sources": [
                {
                    "path": str(path),
                    "sha256": sha256(path),
                    "collection_key": re.search(r"zotero_([^_]+)_top", path.name).group(1),
                }
                for path in ZOTERO_PATHS
            ],
            "existing_literature_source": {
                "path": str(LITERATURE_PATH),
                "sha256": sha256(LITERATURE_PATH),
            },
            "instruction": (
                "Compare all Zotero top-item occurrences with the existing literature corpus; "
                "do not edit the main package."
            ),
        },
        "policy": {
            "doi_match": (
                "Lowercase DOI after URL decoding and removal of doi:/doi.org prefixes and trailing citation punctuation."
            ),
            "title_normalization": (
                "HTML-unescape, strip tags/diacritics, casefold, map ampersand to 'and', retain letters and numbers, and collapse whitespace."
            ),
            "accepted_matches": [
                "Exact normalized DOI with a single existing target.",
                (
                    "For differing DOI versions only: title similarity >= 0.99, same year, all Zotero "
                    "author surnames supported by the existing citation, and the existing record explicitly "
                    "names the Zotero DOI as a related version in verified_metadata."
                ),
            ],
            "near_match_review_threshold": 0.94,
            "guardrail": (
                "No match is inferred from topical similarity, shared first author, or a shared title stem alone; numeric date spans remain part of titles."
            ),
        },
        "summary": {
            "zotero_occurrences_audited": len(occurrences),
            "unique_zotero_keys": unique_items,
            "existing_literature_records_audited": len(existing),
            "existing_match_occurrences": matched_occurrences,
            "existing_match_unique_zotero_keys": matched_unique,
            "existing_match_unique_existing_ids": len({x["existing_id"] for x in existing_matches}),
            "exact_doi_match_unique_zotero_keys": sum(
                x["match_type"] == "normalized_doi_exact" for x in existing_matches
            ),
            "same_work_different_version_unique_zotero_keys": sum(
                x["match_type"] == "same_work_different_version" for x in existing_matches
            ),
            "cross_collection_duplicate_groups": len(cross_collection_duplicates),
            "cross_collection_duplicate_occurrences": duplicate_occurrences,
            "cross_collection_redundant_occurrences": redundant_occurrences,
            "reviewed_distinct_near_match_unique_zotero_keys": len(reviewed_distinct_keys),
            "unresolved_ambiguous_unique_zotero_keys": len(unresolved_ambiguous_keys),
            "unmatched_unique_expansion_candidates": unique_items - matched_unique,
            "unmatched_occurrences": len(occurrences) - matched_occurrences,
            "zotero_items_without_doi": sum(x["normalized_doi"] is None for x in occurrences),
            "unique_zotero_keys_without_doi": len(
                {x["zotero_key"] for x in occurrences if x["normalized_doi"] is None}
            ),
            "audit_status_occurrence_counts": dict(
                sorted(Counter(x["audit_status"] for x in item_dispositions).items())
            ),
        },
        "existing_matches": sorted(existing_matches, key=lambda x: (x["existing_id"], x["zotero_key"])),
        "cross_collection_duplicates": cross_collection_duplicates,
        "ambiguous_cases": sorted(
            ambiguous_cases, key=lambda x: (x["decision"], x["zotero_key"], x["candidate_existing_id"])
        ),
        "items_without_doi": [
            {
                "zotero_key": key,
                "occurrences": [x["occurrence_id"] for x in group],
                "title": group[0]["title"],
                "year": group[0]["year"],
                "authors": group[0]["author_surnames"],
                "audit_status": next(
                    x["audit_status"] for x in item_dispositions if x["zotero_key"] == key
                ),
            }
            for key, group in sorted(occurrences_by_key.items())
            if group[0]["normalized_doi"] is None
        ],
        "item_dispositions": item_dispositions,
        "notes": [
            (
                "Counts distinguish source occurrences from unique Zotero keys because seven keys occur in both source collections."
            ),
            (
                "Unmatched expansion candidates include the reviewed-distinct Axial Seamount pressure paper; 'unmatched' means absent from the existing corpus under this conservative policy."
            ),
            "No main-package files were modified.",
        ],
    }

    OUTPUT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(audit["summary"], indent=2))


if __name__ == "__main__":
    main()
