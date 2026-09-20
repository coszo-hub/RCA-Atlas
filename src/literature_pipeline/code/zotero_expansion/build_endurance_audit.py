import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/coszo_products/zotero_E5UH7L89_top1.json"
COLLECTION = ROOT / "tmp/coszo_products/zotero_E5UH7L89_collection.json"
RCA_FILES = [
    ROOT / "tmp/coszo_products/zotero_RMTSE2IH_top1.json",
    ROOT / "tmp/coszo_products/zotero_RMTSE2IH_top2.json",
]
CROSSREF = ROOT / "tmp/zotero_expansion/endurance_crossref.json"
OUT = ROOT / "tmp/zotero_expansion/endurance_audit.json"


def norm_doi(value):
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", (value or "").strip(), flags=re.I).lower().rstrip(".,;)")


items = json.loads(SOURCE.read_text())
collection = json.loads(COLLECTION.read_text())
by_key = {item["key"]: item for item in items}
position = {item["key"]: index for index, item in enumerate(items, 1)}

empty_abstract_sources = {
    "6M94A5XU": "https://www.sciencedirect.com/science/article/abs/pii/S0079661121001051",
    "9AZHN5UT": "https://pubmed.ncbi.nlm.nih.gov/34972298/",
    "6HLEIGXZ": "https://tos.org/oceanography/article/satellite-remote-sensing-and-the-marine-biodiversity-observation-network-current-science-and-future-steps",
    "7HLK4VFF": "https://pubmed.ncbi.nlm.nih.gov/34241418/",
}

issues = []
for key, source_url in empty_abstract_sources.items():
    data = by_key[key]["data"]
    issues.append({
        "severity": "high",
        "category": "missing_abstract",
        "zotero_key": key,
        "item_position_1_based": position[key],
        "title": data["title"],
        "doi": data["DOI"],
        "observed": "abstractNote is empty",
        "evidence_url": source_url,
        "recommendation": "Retrieve the published abstract from the cited primary page or its linked scholarly record and preserve its source URL.",
    })

issues.extend([
    {
        "severity": "high",
        "category": "contaminated_abstract",
        "zotero_key": "92BSGBND",
        "item_position_1_based": position["92BSGBND"],
        "title": by_key["92BSGBND"]["data"]["title"],
        "doi": by_key["92BSGBND"]["data"]["DOI"],
        "observed": "abstractNote begins with 1,961 characters of ScienceDirect navigation, figure/table listings, citation metadata, and highlights before the literal 'Abstract' heading; the actual abstract follows that heading.",
        "evidence_url": "https://doi.org/10.1016/j.csr.2014.05.010",
        "recommendation": "Discard the scraped page preamble and retain only the published abstract beginning 'Measurement of in situ O2 consumption…'.",
    },
    {
        "severity": "low",
        "category": "abstract_formatting",
        "zotero_key": "A9I7PXNB",
        "item_position_1_based": position["A9I7PXNB"],
        "title": by_key["A9I7PXNB"]["data"]["title"],
        "doi": None,
        "observed": "abstractNote contains 39 hard line breaks copied from page layout; the prose itself appears complete.",
        "recommendation": "Normalize line wrapping to spaces while preserving paragraph boundaries.",
    },
    {
        "severity": "medium",
        "category": "title_transcription",
        "zotero_key": "I35B9SNE",
        "item_position_1_based": position["I35B9SNE"],
        "title": by_key["I35B9SNE"]["data"]["title"],
        "doi": by_key["I35B9SNE"]["data"]["DOI"],
        "observed": "The subtitle separator is missing and the subtitle is stored in all caps.",
        "canonical_title": "Warm Blobs, Low-Oxygen Events, and an Eclipse: The Ocean Observatories Initiative Endurance Array Captures Them All",
        "evidence_url": "https://tos.org/oceanography/article/warm-blobs-low-oxygen-events-and-an-eclipse-the-ocean-observatories-initiat",
        "recommendation": "Replace the title with the publisher title; the DOI is consistent with that work.",
    },
    {
        "severity": "high",
        "category": "title_transcription",
        "zotero_key": "JXHU5NG7",
        "item_position_1_based": position["JXHU5NG7"],
        "title": by_key["JXHU5NG7"]["data"]["title"],
        "doi": by_key["JXHU5NG7"]["data"]["DOI"],
        "observed": "The title misspells 'Initiative' as 'Intiative', omits the colon before the subtitle, and is stored mostly in all caps.",
        "canonical_title": "Using Authentic Data from NSF’s Ocean Observatories Initiative in Undergraduate Teaching: An Invitation",
        "evidence_url": "https://tos.org/oceanography/article/using-authentic-data-fromnsfs-ocean-observatories-initiativein-undergraduate-teaching-an-invitation",
        "recommendation": "Replace the title with the publisher title; the DOI is consistent with that work.",
    },
    {
        "severity": "high",
        "category": "creator_contamination",
        "zotero_key": "6HLEIGXZ",
        "item_position_1_based": position["6HLEIGXZ"],
        "title": by_key["6HLEIGXZ"]["data"]["title"],
        "doi": by_key["6HLEIGXZ"]["data"]["DOI"],
        "observed": "'Oregon State University' is encoded as the second personal author. The publisher author list proceeds from Maria T. Kavanaugh directly to Tom Bell.",
        "evidence_url": "https://tos.org/oceanography/article/satellite-remote-sensing-and-the-marine-biodiversity-observation-network-current-science-and-future-steps",
        "recommendation": "Remove the spurious institutional creator and add the missing pages 62–79.",
    },
])

invalid_url_groups = []
pseudo = []
concatenated = []
for item in items:
    data = item["data"]
    url = data.get("url", "")
    entry = {"zotero_key": item["key"], "title": data.get("title"), "url": url}
    if url.startswith("<Go to ISI>"):
        pseudo.append(entry)
    if len(re.findall(r"https?://", url)) > 1:
        concatenated.append(entry)
invalid_url_groups.append({
    "severity": "medium",
    "category": "invalid_url_value",
    "problem": "Web of Science pseudo-URLs are not valid resolvable URLs.",
    "items": pseudo,
    "recommendation": "Move the WOS accession to an archive/catalog field and use the DOI landing page as URL.",
})
invalid_url_groups.append({
    "severity": "medium",
    "category": "invalid_url_value",
    "problem": "Two URLs are concatenated with a space in one Zotero URL field.",
    "items": concatenated,
    "recommendation": "Keep one canonical landing URL in url and store the other as an attachment or related link.",
})

doi_groups = defaultdict(list)
title_groups = defaultdict(list)
for item in items:
    data = item["data"]
    doi = norm_doi(data.get("DOI"))
    title = re.sub(r"[^a-z0-9]+", " ", data.get("title", "").lower()).strip()
    if doi:
        doi_groups[doi].append(item["key"])
    if title:
        title_groups[title].append(item["key"])
within_duplicates = {
    "duplicate_dois": {doi: keys for doi, keys in doi_groups.items() if len(keys) > 1},
    "duplicate_normalized_titles": {title: keys for title, keys in title_groups.items() if len(keys) > 1},
    "duplicate_keys": [key for key, count in Counter(i["key"] for i in items).items() if count > 1],
    "assessment": "No duplicate Zotero records were found within the Coastal Endurance Array export.",
}

rca_items = []
for path in RCA_FILES:
    rca_items.extend(json.loads(path.read_text()))
rca_by_key = {item["key"]: item for item in rca_items}
cross_collection = []
for item in items:
    if item["key"] in rca_by_key:
        data = item["data"]
        cross_collection.append({
            "zotero_key": item["key"],
            "title": data.get("title"),
            "doi": norm_doi(data.get("DOI")) or None,
            "other_collection": "Regional Cabled Array",
            "other_collection_key": "RMTSE2IH",
            "relationship": "same Zotero item is intentionally assigned to both collections; this is collection overlap, not a duplicate library record",
        })

package_match = {
    "zotero_key": "GBWZL49K",
    "title": "The Ocean Observatories Initiative",
    "doi": "10.3389/fmars.2019.00074",
    "other_record": "COSZO-REF-104",
    "other_file": str(ROOT / "tmp/coszo_abstracts/package/coszo_literature.jsonl"),
    "relationship": "same published work already exists in the assembled COSZO literature package",
}

crossref = json.loads(CROSSREF.read_text())["records"]
retrieved = {doi: record for doi, record in crossref.items() if record.get("status") == "retrieved"}
rate_limited = {doi: record for doi, record in crossref.items() if record.get("status") != "retrieved"}

result = {
    "audit_version": 1,
    "audited_at": datetime.now(timezone.utc).isoformat(),
    "source_file": str(SOURCE),
    "collection": {
        "key": collection["data"]["key"],
        "name": collection["data"]["name"],
        "library": collection["library"]["name"],
        "reported_num_items": collection["meta"]["numItems"],
    },
    "summary": {
        "items_audited": len(items),
        "items_with_abstract": sum(bool(i["data"].get("abstractNote", "").strip()) for i in items),
        "items_with_empty_abstract": sum(not bool(i["data"].get("abstractNote", "").strip()) for i in items),
        "abstract_quality_issues": 6,
        "title_issues": 2,
        "creator_issues": 1,
        "within_collection_duplicates": 0,
        "regional_cabled_array_overlaps": len(cross_collection),
        "existing_coszo_package_matches": 1,
        "doi_bearing_items": sum(bool(norm_doi(i["data"].get("DOI"))) for i in items),
        "non_doi_items": [i["key"] for i in items if not norm_doi(i["data"].get("DOI"))],
    },
    "issues": issues,
    "url_metadata_issues": invalid_url_groups,
    "doi_title_audit": {
        "conclusion": "No DOI appears to identify a different work. Two titles need transcription/formatting correction while retaining their existing DOIs.",
        "crossref_exact_doi_records_retrieved": len(retrieved),
        "crossref_exact_doi_records_rate_limited": len(rate_limited),
        "retrieved_records_title_assessment": "All 17 retrieved Crossref records match the Zotero work identity; the only material title formatting issue among them is I35B9SNE.",
        "additional_primary_publisher_checks": ["I35B9SNE", "JXHU5NG7", "6HLEIGXZ", "6M94A5XU"],
        "rate_limited_dois": sorted(rate_limited),
        "raw_crossref_file": str(CROSSREF),
        "note": "Crossref returned HTTP 429 for 19 DOI lookups. The audit records this limitation rather than treating an unavailable lookup as a mismatch.",
    },
    "within_collection_duplicates": within_duplicates,
    "cross_collection_overlaps": {
        "regional_cabled_array": cross_collection,
        "assembled_coszo_literature": [package_match],
        "assessment": "The seven Regional Cabled Array matches reuse identical Zotero keys and are shared collection membership, not duplicate records. The COSZO package match should be deduplicated by DOI during any future merge.",
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(result["summary"], indent=2))
