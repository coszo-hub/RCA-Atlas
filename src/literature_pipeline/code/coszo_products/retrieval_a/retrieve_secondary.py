import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

RAW = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/retrieval_a/raw")
RAW.mkdir(parents=True, exist_ok=True)

doi_by_id = {
    134: "10.1130/G49639.1",
    135: "10.5670/oceanog.2019.125",
    136: "10.1130/GES01630.1",
    137: "10.1016/j.epsl.2016.10.050",
    138: "10.1016/j.tecto.2013.03.015",
    139: "10.1785/0220210171",
    140: "10.1016/j.tecto.2020.228410",
    141: "10.1016/B978-0-444-62617-2.00020-7",
    142: "10.1146/annurev-earth-040610-133408",
    143: "10.1126/sciadv.add6688",
    144: "10.1038/ngeo2929",
    145: "10.1002/2016GC006250",
    146: "10.1017/CBO9781139050524",
    148: "10.1029/2020GC009095",
    149: "10.1038/nrmicro1991",
    150: "10.1785/0220150255",
    151: "10.1029/2008JB006045",
    152: "10.1016/j.epsl.2016.01.033",
    153: "10.1029/2019GC008510",
    154: "10.1785/0120110096",
    155: "10.3390/w13030281",
}

pages = {
    134: "https://pubs.geoscienceworld.org/geology/article/50/11/1229/616603/Direct-constraints-on-in-situ-stress-state-from",
    135: "https://tos.org/oceanography/article/processes-governing-giant-subduction-earthquakes-iodp-drilling-to-sample-an",
    136: "https://pubs.geoscienceworld.org/gsa/geosphere/article/14/4/1411/532686/Laboratory-measurements-quantifying-elastic",
    137: "https://api.elsevier.com/content/article/PII:S0012821X1630615X?httpAccept=text/xml",
    138: "https://api.elsevier.com/content/article/PII:S0040195113001893?httpAccept=text/xml",
    140: "https://api.elsevier.com/content/article/PII:S0040195120300937?httpAccept=text/xml",
    141: "https://api.elsevier.com/content/article/PII:B9780444626172000207?httpAccept=text/xml",
    142: "https://www.annualreviews.org/doi/10.1146/annurev-earth-040610-133408",
    144: "https://www.nature.com/articles/ngeo2929",
    146: "https://www.cambridge.org/core/product/identifier/9781139050524/type/book",
    147: "https://interactiveoceans.washington.edu/",
    149: "https://www.nature.com/articles/nrmicro1991",
    150: "https://pubs.geoscienceworld.org/srl/article/87/4/930-943/314131",
    152: "https://api.elsevier.com/content/article/PII:S0012821X16000558?httpAccept=text/xml",
    154: "https://pubs.geoscienceworld.org/bssa/article/102/1/352-360/349715",
    155: "https://www.mdpi.com/2073-4441/13/3/281",
}

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; COSZO bibliography verification)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch(url, stem):
    meta = {"request_url": url}
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as response:
            body = response.read()
            ctype = response.headers.get("Content-Type", "")
            meta.update({
                "status_code": response.status,
                "final_url": response.geturl(),
                "content_type": ctype,
                "headers": dict(response.headers.items()),
                "bytes": len(body),
            })
            suffix = ".xml" if "xml" in ctype else ".html"
            (RAW / f"{stem}{suffix}").write_bytes(body)
    except HTTPError as exc:
        body = exc.read()
        meta.update({
            "status_code": exc.code,
            "final_url": exc.geturl(),
            "error": repr(exc),
            "content_type": exc.headers.get("Content-Type", ""),
            "bytes": len(body),
        })
        (RAW / f"{stem}_error_body.txt").write_bytes(body)
    except Exception as exc:
        meta["error"] = repr(exc)
    (RAW / f"{stem}_fetch.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


# Exact Crossref records for every DOI found by search or issue matching.
for n, doi in doi_by_id.items():
    if n in {134, 135, 137, 138, 139, 140, 141, 143, 144, 145, 146, 148, 149}:
        continue
    fetch(f"https://api.crossref.org/works/{quote(doi, safe='')}", f"COSZO-REF-{n:03d}_crossref_exact")
    time.sleep(0.15)

# Publisher and official project pages.
for n, url in pages.items():
    fetch(url, f"COSZO-REF-{n:03d}_publisher")
    time.sleep(0.2)

# OpenAlex and Semantic Scholar abstract fallbacks.
for n, doi in doi_by_id.items():
    openalex = (
        f"https://api.openalex.org/works/https://doi.org/{doi}"
        "?select=id,doi,title,authorships,publication_year,abstract_inverted_index,open_access,primary_location,best_oa_location,locations"
    )
    fetch(openalex, f"COSZO-REF-{n:03d}_openalex_retry")
    time.sleep(0.8)
    s2 = (
        "https://api.semanticscholar.org/graph/v1/paper/DOI:"
        + quote(doi, safe="")
        + "?fields=title,abstract,authors,year,externalIds,openAccessPdf,url"
    )
    fetch(s2, f"COSZO-REF-{n:03d}_semanticscholar")
    time.sleep(0.8)

# Europe PMC keyword searches for likely biomedical coverage.
for n, title in {
    143: "Fluid sources and overpressures within the central Cascadia Subduction Zone revealed by a warm high-flux seafloor seep",
    149: "Hydrothermal vents and the origin of life",
}.items():
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&query=" + quote(f'TITLE:"{title}"')
    fetch(url, f"COSZO-REF-{n:03d}_europepmc_search")

print("secondary retrieval complete")
