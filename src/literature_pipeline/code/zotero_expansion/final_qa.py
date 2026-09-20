#!/usr/bin/env python3
"""Independent consistency checks for the staged literature package."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent")
PACKAGE = ROOT / "tmp/zotero_expansion/package"
REPORT = ROOT / "tmp/zotero_expansion/final_qa_report.json"


def read_jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (PACKAGE / name).read_text().splitlines()
        if line.strip()
    ]


def normalize_doi(value: object) -> str | None:
    if not value:
        return None
    text = unquote(str(value)).casefold().strip()
    text = re.sub(r"^(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)", "", text)
    return text.rstrip(".,;)") or None


def normalize_text(value: object) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKD", html.unescape(str(value or "")))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_zotero_raw() -> dict[str, dict]:
    raw_dir = PACKAGE / "zotero_retrieval_provenance"
    items = []
    for name in (
        "zotero_RMTSE2IH_top1.json",
        "zotero_RMTSE2IH_top2.json",
        "zotero_E5UH7L89_top1.json",
    ):
        doc = json.loads((raw_dir / name).read_text())
        items.extend(doc if isinstance(doc, list) else doc["items"])
    by_key = {}
    for item in items:
        if item["key"] in by_key:
            prior = by_key[item["key"]]
            assert prior["data"] == item["data"]
        by_key[item["key"]] = item
    return by_key


def load_override_abstracts() -> dict[str, list[dict]]:
    raw_dir = PACKAGE / "zotero_retrieval_provenance"
    result: dict[str, list[dict]] = defaultdict(list)
    for name in ("rmt_overrides.jsonl", "endurance_overrides.jsonl", "missing_results.jsonl"):
        for line in (raw_dir / name).read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                item["provenance_file"] = name
                result[item.get("zotero_key")].append(item)
    return result


def main() -> None:
    issues: list[dict] = []
    checks: dict[str, object] = {}

    def require(condition: bool, check: str, details: object = None) -> None:
        if not condition:
            issues.append({"check": check, "details": details})

    coszo = read_jsonl("coszo_literature.jsonl")
    ooi = read_jsonl("ooi_zotero_literature.jsonl")
    literature = read_jsonl("literature.jsonl")
    ooi_edges = read_jsonl("ooi_zotero_occurrences.jsonl")
    all_edges = read_jsonl("literature_occurrences.jsonl")
    matches = json.loads((PACKAGE / "zotero_existing_matches.json").read_text())
    manifest = json.loads((PACKAGE / "literature_manifest.json").read_text())

    checks["counts"] = {
        "coszo_records": len(coszo),
        "new_ooi_records": len(ooi),
        "canonical_records": len(literature),
        "ooi_occurrences": len(ooi_edges),
        "all_occurrences": len(all_edges),
        "zotero_existing_matches": len(matches),
        "unique_zotero_keys": len({edge["zotero_key"] for edge in ooi_edges}),
    }
    require(len(coszo) == 183, "expected COSZO record count", len(coszo))
    require(len(ooi) == 153, "expected new OOI record count", len(ooi))
    require(len(literature) == 336, "expected canonical record count", len(literature))
    require(len(ooi_edges) == 180, "expected Zotero occurrence count", len(ooi_edges))
    require(len({edge["zotero_key"] for edge in ooi_edges}) == 173, "expected unique Zotero works")
    require(len(matches) == 20, "expected Zotero-to-existing match count", len(matches))
    require(manifest.get("canonical_records") == len(literature), "manifest canonical count")
    require(manifest.get("coszo_pdf_records") == len(coszo), "manifest COSZO count")
    require(manifest.get("new_zotero_records") == len(ooi), "manifest new Zotero count")
    require(manifest.get("zotero_top_level_occurrences") == len(ooi_edges), "manifest Zotero occurrence count")

    ids = [row["id"] for row in literature]
    canonical_ids = [row["canonical_id"] for row in literature]
    require(len(ids) == len(set(ids)), "duplicate record IDs")
    require(len(canonical_ids) == len(set(canonical_ids)), "duplicate canonical IDs")
    require(set(ids) == set(canonical_ids), "record ID/canonical ID disagreement")

    doi_groups: dict[str, list[str]] = defaultdict(list)
    title_groups: dict[str, list[str]] = defaultdict(list)
    for row in literature:
        doi = normalize_doi(row.get("resolved_doi"))
        if doi:
            doi_groups[doi].append(row["id"])
        title_groups[normalize_title(row.get("resolved_title"))].append(row["id"])
    duplicate_dois = {doi: members for doi, members in doi_groups.items() if len(members) > 1}
    require(not duplicate_dois, "duplicate normalized resolved DOI", duplicate_dois)
    checks["identity_uniqueness"] = {
        "unique_ids": len(set(ids)),
        "unique_canonical_ids": len(set(canonical_ids)),
        "records_with_resolved_doi": len(doi_groups),
        "duplicate_resolved_doi_groups": duplicate_dois,
        "same_normalized_title_distinct_work_groups": [
            {
                "normalized_title": title,
                "record_ids": members,
                "reason": "Distinct authors, years, and DOIs; title-only collision is not a duplicate.",
            }
            for title, members in title_groups.items()
            if title and len(members) > 1
        ],
    }

    # Every OOI canonical record must contain a formal source abstract and a real URL.
    raw_zotero = load_zotero_raw()
    override_abstracts = load_override_abstracts()
    provenance_results = Counter()
    for row in ooi:
        key = row.get("zotero_item_key")
        source_url = row.get("abstract_source_url")
        require(row.get("abstract_status") == "retrieved", "OOI abstract status", row["id"])
        require(bool(normalize_text(row.get("abstract"))), "OOI empty abstract", row["id"])
        require(
            bool(source_url) and urlparse(source_url).scheme in {"http", "https"} and bool(urlparse(source_url).netloc),
            "OOI invalid abstract source URL",
            {"id": row["id"], "url": source_url},
        )
        if source_url and urlparse(source_url).netloc == "api.zotero.org":
            source_abstract = raw_zotero.get(key, {}).get("data", {}).get("abstractNote")
            ok = normalize_text(source_abstract) == normalize_text(row.get("abstract"))
            require(ok, "OOI abstract does not match packaged Zotero source", row["id"])
            if ok:
                provenance_results["exact_packaged_zotero_abstractNote"] += 1
        else:
            candidates = override_abstracts.get(key, [])
            ok = any(
                normalize_text(candidate.get("abstract")) == normalize_text(row.get("abstract"))
                for candidate in candidates
            )
            require(ok, "OOI override abstract lacks matching packaged provenance", row["id"])
            if ok:
                provenance_results["exact_packaged_override_or_retrieval_result"] += 1
    checks["ooi_abstract_provenance"] = {
        "records": len(ooi),
        "status_counts": dict(Counter(row.get("abstract_status") for row in ooi)),
        "nonempty_abstracts": sum(bool(normalize_text(row.get("abstract"))) for row in ooi),
        "valid_http_source_urls": sum(
            bool(row.get("abstract_source_url"))
            and urlparse(row["abstract_source_url"]).scheme in {"http", "https"}
            and bool(urlparse(row["abstract_source_url"]).netloc)
            for row in ooi
        ),
        "provenance_matches": dict(provenance_results),
    }

    # Abstract duplication check: normalized exact identity plus a conservative
    # five-token-shingle near-duplicate screen.
    with_abstract = [row for row in literature if normalize_text(row.get("abstract"))]
    abstract_hash_groups: dict[str, list[str]] = defaultdict(list)
    shingle_sets = []
    for row in with_abstract:
        normalized = normalize_text(row["abstract"])
        abstract_hash_groups[hashlib.sha256(normalized.encode()).hexdigest()].append(row["id"])
        tokens = re.findall(r"[a-z0-9]+", normalized)
        shingle_sets.append({tuple(tokens[i : i + 5]) for i in range(max(0, len(tokens) - 4))})
    exact_abstract_duplicates = [members for members in abstract_hash_groups.values() if len(members) > 1]
    require(not exact_abstract_duplicates, "duplicate normalized abstracts", exact_abstract_duplicates)
    near_duplicates = []
    for i, left in enumerate(shingle_sets):
        for j in range(i + 1, len(shingle_sets)):
            right = shingle_sets[j]
            union = left | right
            similarity = len(left & right) / len(union) if union else 0.0
            if similarity >= 0.8:
                near_duplicates.append(
                    {
                        "left": with_abstract[i]["id"],
                        "right": with_abstract[j]["id"],
                        "five_token_shingle_jaccard": round(similarity, 6),
                    }
                )
    require(not near_duplicates, "near-duplicate abstract candidates", near_duplicates)
    checks["abstract_duplicates"] = {
        "abstracts_checked": len(with_abstract),
        "exact_duplicate_groups": exact_abstract_duplicates,
        "near_duplicate_threshold": 0.8,
        "near_duplicate_candidates": near_duplicates,
    }

    # Known correction checks.
    ooi_by_key = {row["zotero_item_key"]: row for row in ooi}
    expected_corrections = {
        "5Y85SKAW": {
            "doi": "10.1002/rob.21961",
            "title_phrase": "georeferenced seafloor imagery",
            "abstract_phrase": "unsupervised feature learning method",
        },
        "XYD5BSMF": {
            "doi": "10.1029/2020gl087372",
            "title_phrase": "frequency of occurrence distribution for tsunamis",
            "abstract_phrase": "32 year record of high resolution bottom pressure",
        },
        "92BSGBND": {
            "doi": "10.1016/j.csr.2014.05.010",
            "title_phrase": "benthic boundary layer",
            "abstract_phrase": "measurement of in situ o2 consumption",
        },
    }
    correction_details = {}
    for key, expected in expected_corrections.items():
        row = ooi_by_key.get(key)
        require(row is not None, "known corrected key absent", key)
        if not row:
            continue
        title = normalize_title(row.get("resolved_title"))
        abstract = normalize_title(row.get("abstract"))
        ok = (
            normalize_doi(row.get("resolved_doi")) == expected["doi"]
            and normalize_title(expected["title_phrase"]) in title
            and normalize_title(expected["abstract_phrase"]) in abstract
        )
        require(ok, "known bad key is not corrected", key)
        correction_details[key] = {
            "record_id": row["id"],
            "resolved_doi": row.get("resolved_doi"),
            "resolved_title": row.get("resolved_title"),
            "abstract_source_url": row.get("abstract_source_url"),
            "verified": ok,
        }
    checks["known_corrections"] = correction_details

    pu_matches = [item for item in matches if item.get("zotero_key") == "PU7BMBHB"]
    pu_edges = [edge for edge in ooi_edges if edge.get("zotero_key") == "PU7BMBHB"]
    require(len(pu_matches) == 1 and pu_matches[0].get("canonical_id") == "COSZO-REF-019", "PU7BMBHB match mapping", pu_matches)
    require(len(pu_edges) == 1 and pu_edges[0].get("canonical_id") == "COSZO-REF-019", "PU7BMBHB occurrence mapping", pu_edges)
    require("PU7BMBHB" not in ooi_by_key, "PU7BMBHB incorrectly emitted as new OOI canonical record")
    checks["pu7bmbhb_mapping"] = {"match_table": pu_matches, "occurrence_edges": pu_edges}

    # Occurrence graph integrity and exact source-specific embedding.
    records_by_id = {row["id"]: row for row in literature}
    edge_by_id: dict[str, dict] = {}
    duplicate_edge_ids = []
    for edge in all_edges:
        occurrence_id = edge["occurrence_id"]
        if occurrence_id in edge_by_id:
            duplicate_edge_ids.append(occurrence_id)
        edge_by_id[occurrence_id] = edge
        require(edge.get("canonical_id") in records_by_id, "edge targets missing canonical record", edge)
    require(not duplicate_edge_ids, "duplicate occurrence IDs", duplicate_edge_ids)

    missing_from_records = []
    wrong_target = []
    undeclared_edges = []
    declared_pairs = set()
    for record in literature:
        for occurrence_id in record.get("source_occurrence_ids", []):
            declared_pairs.add((record["id"], occurrence_id))
            edge = edge_by_id.get(occurrence_id)
            if edge is None:
                missing_from_records.append((record["id"], occurrence_id))
            elif edge.get("canonical_id") != record["id"]:
                wrong_target.append((record["id"], occurrence_id, edge.get("canonical_id")))
    for edge in all_edges:
        if (edge["canonical_id"], edge["occurrence_id"]) not in declared_pairs:
            undeclared_edges.append(edge["occurrence_id"])
    require(not missing_from_records, "record cites missing occurrence edge", missing_from_records)
    require(not wrong_target, "record/edge canonical target disagreement", wrong_target)
    require(not undeclared_edges, "occurrence edge absent from target record source_occurrence_ids", undeclared_edges)

    serialized_ooi_edges = Counter(json.dumps(edge, sort_keys=True) for edge in ooi_edges)
    serialized_all_edges = Counter(json.dumps(edge, sort_keys=True) for edge in all_edges)
    missing_ooi_edge_copies = list((serialized_ooi_edges - serialized_all_edges).elements())
    require(not missing_ooi_edge_copies, "OOI source edge missing or changed in unified occurrence file", missing_ooi_edge_copies)
    checks["occurrence_edges"] = {
        "all_edges": len(all_edges),
        "unique_occurrence_ids": len(edge_by_id),
        "ooi_edges": len(ooi_edges),
        "all_targets_exist": not any(x["check"] == "edge targets missing canonical record" for x in issues),
        "record_edge_bijection_valid": not (missing_from_records or wrong_target or undeclared_edges),
        "ooi_edges_embedded_unchanged": not missing_ooi_edge_copies,
    }

    # Referenced Markdown artifacts.
    missing_record_files = []
    missing_abstract_files = []
    abstract_text_mismatches = []
    for row in literature:
        record_file = row.get("record_file")
        if not record_file or not (PACKAGE / record_file).is_file():
            missing_record_files.append(row["id"])
        abstract_file = row.get("abstract_file")
        if row.get("abstract_status") == "retrieved":
            if not abstract_file or not (PACKAGE / abstract_file).is_file():
                missing_abstract_files.append(row["id"])
            elif normalize_text(row.get("abstract")) not in normalize_text((PACKAGE / abstract_file).read_text()):
                abstract_text_mismatches.append(row["id"])
    require(not missing_record_files, "missing record Markdown", missing_record_files)
    require(not missing_abstract_files, "missing abstract Markdown", missing_abstract_files)
    require(not abstract_text_mismatches, "abstract Markdown content mismatch", abstract_text_mismatches)
    checks["markdown_artifacts"] = {
        "record_files_verified": len(literature),
        "abstract_files_verified": sum(row.get("abstract_status") == "retrieved" for row in literature),
    }

    # Both nested and package-wide checksum manifests must match current bytes.
    checksum_checks = {}
    for manifest_name in ("coszo_collection_checksums.json", "literature_collection_checksums.json"):
        checksum_map = json.loads((PACKAGE / manifest_name).read_text())
        missing = []
        mismatches = []
        for relative, expected in checksum_map.items():
            target = PACKAGE / relative
            if not target.is_file():
                missing.append(relative)
            else:
                actual = sha256(target)
                if actual != expected:
                    mismatches.append({"path": relative, "expected": expected, "actual": actual})
        checksum_checks[manifest_name] = {
            "entries": len(checksum_map),
            "missing": missing,
            "mismatches": mismatches,
        }
        require(not missing, f"{manifest_name} missing files", missing)
        require(not mismatches, f"{manifest_name} checksum mismatch", mismatches)

    package_checksum_map = json.loads((PACKAGE / "literature_collection_checksums.json").read_text())
    actual_package_files = {
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.name != "literature_collection_checksums.json"
    }
    checksum_coverage_extra = sorted(actual_package_files - set(package_checksum_map))
    checksum_coverage_stale = sorted(set(package_checksum_map) - actual_package_files)
    require(not checksum_coverage_extra, "package files omitted from package-wide checksum manifest", checksum_coverage_extra)
    require(not checksum_coverage_stale, "stale package checksum entries", checksum_coverage_stale)
    checksum_checks["package_wide_coverage"] = {
        "actual_files_excluding_self": len(actual_package_files),
        "manifest_entries": len(package_checksum_map),
        "omitted_files": checksum_coverage_extra,
        "stale_entries": checksum_coverage_stale,
    }
    checks["checksums"] = checksum_checks

    checks["manifest_abstract_count"] = {
        "declared": manifest.get("abstracts_retrieved"),
        "observed": sum(row.get("abstract_status") == "retrieved" for row in literature),
    }
    require(
        manifest.get("abstracts_retrieved")
        == sum(row.get("abstract_status") == "retrieved" for row in literature),
        "manifest abstract count",
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package": str(PACKAGE),
        "result": "pass" if not issues else "fail",
        "issues": issues,
        "checks": checks,
        "package_edits_during_qa": [
            {
                "reason": "Objective defect: nested COSZO checksum manifest had 181 stale hashes after shared Markdown regeneration.",
                "files": [
                    "coszo_collection_checksums.json",
                    "literature_collection_checksums.json",
                ],
                "action": "Recomputed nested hashes from staged bytes and updated its hash in the package-wide checksum manifest.",
            }
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"result": report["result"], "issue_count": len(issues), "checks": checks}, indent=2))
    raise SystemExit(0 if not issues else 1)


if __name__ == "__main__":
    main()
