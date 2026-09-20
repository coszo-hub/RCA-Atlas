import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/coszo_products/zotero_E5UH7L89_top1.json"
RAW = ROOT / "tmp/zotero_expansion/raw"
OUT = ROOT / "tmp/zotero_expansion/endurance_overrides.jsonl"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def tos_abstract(filename: str) -> str:
    page = (RAW / filename).read_text()
    section = page.split('<a id="article-abstract"></a>', 1)[1]
    paragraph = re.search(r"<p>(.*?)</p>", section, flags=re.S).group(1)
    return clean(re.sub(r"<[^>]+>", " ", paragraph))


def pubmed_abstract(filename: str) -> str:
    element = ET.parse(RAW / filename).getroot().find(".//AbstractText")
    return clean("".join(element.itertext()))


items = json.loads(SOURCE.read_text())
by_key = {item["key"]: item["data"] for item in items}
retrieved_at = datetime.now(timezone.utc).isoformat()

# This publisher-rendered abstract was recovered from the exact ScienceDirect
# record. Direct curl access returned HTTP 403, so the failed response is kept
# in attempts rather than substituting or paraphrasing the text.
green_crab_abstract = clean("""
The annual abundance of the non-native European green crab, Carcinus maenas, in Oregon estuaries varies greatly with ocean conditions. Average numbers were high following the 1997–1998 El Niño, decreased and remained low (<0.3 per trap) until they increased (>2 per trap) following the extended anomalous warming in 2014–2016. The year class strength of young crabs is strongly linked to ocean indicators during their planktonic larval development. Many of the same physical and biological ecosystem indicators used in salmon forecasting are also correlated with green crabs, but in the opposite direction. While cold ocean conditions benefit salmon, warm ocean indicators are positively linked to green crab year class strength. Among the best indicators for green crab year class strength are winter water temperatures, the sign of the Pacific Decadal Oscillation index, the day of physical and biological spring transitions, and negative biomass anomalies of northern copepods. These correlations suggest that green crabs need (1) warm winters (temperature > 10 °C), which enable larvae to complete their development in the near-shore, (2) strong northward flow of coastal waters during winter, which allows larvae to be transported from established populations to the south and (3) coastal circulation patterns that keep larvae close to shore, where they can be carried by wind and tidal currents into estuaries to settle. By using a relatively simple stoplight approach of ranking indicators, we were able to explain 69% of the inter-annual variability in green crab year class strength, while a quantitative metric of a combination of indicators explained 64% of the variability. Recruitment in 2018 and 2019 exceeded what was expected from the suite of ocean indicators. We discuss the possible role of additional larval sources, from the north or from local estuaries, that may have contributed to the increased recruitment during these years. If breeding populations of green crabs in Oregon and Washington continue to build, the relationships between ocean conditions and recruitment we have developed based solely on larval sources from the south could be greatly underestimating recruitment in the future.
""")

crossref = json.loads((ROOT / "tmp/zotero_expansion/endurance_crossref.json").read_text())["records"]
wind_abstract = clean(re.sub(r"<[^>]+>", " ", crossref["10.1121/10.0007463"]["abstract"]))

page = (RAW / "A9I7PXNB_wm_mapping.json").read_text()
repository_abstract = clean(re.search(r'<meta name="description" content="(.*?)">', page, flags=re.S).group(1))

contaminated = by_key["92BSGBND"]["abstractNote"]
formal_benthic_abstract = clean(contaminated.rsplit(" Abstract ", 1)[1])

satellite_page = (RAW / "6HLEIGXZ_tos.html").read_text()
satellite_authors = re.findall(r'<a class="author-popover"[^>]+title="([^"]+)"', satellite_page)

records = [
    {
        "zotero_key": "6M94A5XU",
        "abstract": green_crab_abstract,
        "abstract_source_url": "https://www.sciencedirect.com/science/article/abs/pii/S0079661121001051",
        "retrieved_at": retrieved_at,
        "notes": "Exact DOI/title publisher record. ScienceDirect exposes the formal abstract; direct automated HTML retrieval returned HTTP 403, so no page-navigation or highlight text was included.",
        "attempts": [
            {"url": "https://www.sciencedirect.com/science/article/abs/pii/S0079661121001051", "result": "Exact publisher record and complete labeled Abstract recovered through the rendered scholarly page; title and DOI match."},
            {"url": "https://api.crossref.org/works/10.1016%2Fj.pocean.2021.102618", "result": "HTTP 200; exact metadata but no deposited abstract."},
            {"url": "https://www.sciencedirect.com/science/article/abs/pii/S0079661121001051", "result": "Direct curl attempt returned HTTP 403; retained as an access limitation."},
        ],
    },
    {
        "zotero_key": "9AZHN5UT",
        "abstract": wind_abstract,
        "abstract_source_url": "https://pubmed.ncbi.nlm.nih.gov/34972298/",
        "retrieved_at": retrieved_at,
        "notes": "Formal abstract verified in PubMed XML and independently matched the publisher-deposited Crossref abstract for DOI 10.1121/10.0007463.",
        "attempts": [
            {"url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=34972298&retmode=xml", "result": "HTTP 200; exact title, DOI, authors, and complete AbstractText."},
            {"url": "https://api.crossref.org/works/10.1121%2F10.0007463", "result": "HTTP 200; exact metadata and matching publisher-deposited abstract."},
        ],
    },
    {
        "zotero_key": "6HLEIGXZ",
        "abstract": tos_abstract("6HLEIGXZ_tos.html"),
        "abstract_source_url": "https://tos.org/oceanography/article/satellite-remote-sensing-and-the-marine-biodiversity-observation-network-current-science-and-future-steps",
        "retrieved_at": retrieved_at,
        "resolved_authors": satellite_authors,
        "pages": "62–79",
        "notes": "Publisher page supplies the labeled Article Abstract and full 14-author byline. Removed the spurious Zotero creator 'Oregon State University' and filled the publisher page range.",
        "attempts": [
            {"url": "https://tos.org/oceanography/article/satellite-remote-sensing-and-the-marine-biodiversity-observation-network-current-science-and-future-steps", "result": "HTTP 200; exact DOI/title, labeled abstract, 14-author byline, and pages 62–79 verified."},
            {"url": "https://tos.org/oceanography/assets/docs/34-2_kavanaugh.pdf", "result": "Publisher PDF link present on the article record; not needed to substitute text for the HTML abstract."},
        ],
    },
    {
        "zotero_key": "7HLK4VFF",
        "abstract": pubmed_abstract("7HLK4VFF_pubmed.xml"),
        "abstract_source_url": "https://pubmed.ncbi.nlm.nih.gov/34241418/",
        "retrieved_at": retrieved_at,
        "notes": "Formal abstract retrieved from PubMed XML for the exact DOI/title/authors; no publisher navigation or body text included.",
        "attempts": [
            {"url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=34241418&retmode=xml", "result": "HTTP 200; exact title, DOI, authors, and complete AbstractText."},
            {"url": "https://doi.org/10.1121/10.0005440", "result": "DOI and title verified against the AIP/JASA scholarly record."},
        ],
    },
    {
        "zotero_key": "92BSGBND",
        "abstract": formal_benthic_abstract,
        "abstract_source_url": "https://www.sciencedirect.com/science/article/abs/pii/S0278434314001915",
        "retrieved_at": retrieved_at,
        "notes": "Removed the scraped ScienceDirect Outline/Highlights/figures/tables/citation preamble and retained only the formal text under the publisher's Abstract heading.",
        "attempts": [
            {"url": "https://www.sciencedirect.com/science/article/abs/pii/S0278434314001915", "result": "Exact publisher record exposes the same complete labeled abstract; DOI, title, volume, date, and pages match."},
            {"url": "https://doi.org/10.1016/j.csr.2014.05.010", "result": "Exact DOI resolution and work identity verified."},
        ],
    },
    {
        "zotero_key": "A9I7PXNB",
        "abstract": repository_abstract,
        "abstract_source_url": "https://scholarworks.wm.edu/etd/1673281632/",
        "retrieved_at": retrieved_at,
        "notes": "Used the authoritative institutional-repository abstract and normalized layout line wraps. The repository wording also corrects a substantive Zotero transcription near the end ('notably absent … from the open-ocean mixed layer'). Repository DOI: 10.25773/v5-enmt-fn19.",
        "attempts": [
            {"url": "https://scholarworks.wm.edu/etd/1673281632/", "result": "HTTP redirect to the current William & Mary repository item."},
            {"url": "https://scholarworks.wm.edu/server/api/core/mapping?url=https://scholarworks.wm.edu/etd/1673281632", "result": "HTTP 200; exact dissertation title, author, formal repository abstract, and DOI verified."},
        ],
    },
    {
        "zotero_key": "I35B9SNE",
        "abstract": tos_abstract("I35B9SNE_tos.html"),
        "abstract_source_url": "https://tos.org/oceanography/article/warm-blobs-low-oxygen-events-and-an-eclipse-the-ocean-observatories-initiat",
        "retrieved_at": retrieved_at,
        "resolved_title": "Warm Blobs, Low-Oxygen Events, and an Eclipse: The Ocean Observatories Initiative Endurance Array Captures Them All",
        "notes": "Publisher title restores the colon and normal title case; DOI 10.5670/oceanog.2018.114 is unchanged. Publisher-labeled Article Abstract retained.",
        "attempts": [
            {"url": "https://tos.org/oceanography/article/warm-blobs-low-oxygen-events-and-an-eclipse-the-ocean-observatories-initiat", "result": "HTTP 200; canonical title, DOI, pages 90–97, and labeled abstract verified."},
            {"url": "https://api.crossref.org/works/10.5670%2Foceanog.2018.114", "result": "HTTP 200; canonical title independently matched."},
        ],
    },
    {
        "zotero_key": "JXHU5NG7",
        "abstract": tos_abstract("JXHU5NG7_tos.html"),
        "abstract_source_url": "https://tos.org/oceanography/article/using-authentic-data-fromnsfs-ocean-observatories-initiativein-undergraduate-teaching-an-invitation",
        "retrieved_at": retrieved_at,
        "resolved_title": "Using Authentic Data from NSF’s Ocean Observatories Initiative in Undergraduate Teaching: An Invitation",
        "notes": "Publisher title corrects the Zotero misspelling 'Intiative', restores the subtitle colon, and normalizes case. DOI 10.5670/oceanog.2020.103 is unchanged; publisher-labeled Article Abstract retained.",
        "attempts": [
            {"url": "https://tos.org/oceanography/article/using-authentic-data-fromnsfs-ocean-observatories-initiativein-undergraduate-teaching-an-invitation", "result": "HTTP 200; canonical title, DOI, pages 62–73, and labeled abstract verified."},
            {"url": "https://doi.org/10.5670/oceanog.2020.103", "result": "DOI resolves to the same publisher record."},
        ],
    },
]

OUT.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))
print(json.dumps({"records": len(records), "keys": [record["zotero_key"] for record in records], "abstract_lengths": {record["zotero_key"]: len(record["abstract"]) for record in records}}, indent=2))
