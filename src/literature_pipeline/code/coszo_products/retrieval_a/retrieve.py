import json
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products")
RAW = BASE / "retrieval_a" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
records = []
for line in (BASE / "new_citations.jsonl").read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    n = int(row["id"].rsplit("-", 1)[1])
    if 134 <= n <= 155:
        records.append(row)

HEADERS = {
    "User-Agent": "COSZO-bibliography-verification/1.0 (institutional literature audit)",
    "Accept": "application/json",
}


def get_json(url, out_path):
    result = {"request_url": url}
    try:
        request = Request(url, headers=HEADERS)
        response = urlopen(request, timeout=25)
        body_bytes = response.read()
        result.update({
            "status_code": response.status,
            "final_url": response.geturl(),
            "headers": dict(response.headers.items()),
        })
        try:
            result["body"] = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            result["body_text"] = body_bytes.decode("utf-8", errors="replace")[:200000]
    except HTTPError as exc:
        result.update({"status_code": exc.code, "final_url": exc.geturl(), "error": repr(exc)})
    except Exception as exc:
        result["error"] = repr(exc)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


for row in records:
    rid = row["id"]
    dois = row.get("dois_as_cited") or []
    title = row["citation"].split(".", 1)[0]
    if dois:
        doi = dois[0]
        urls = {
            "crossref": f"https://api.crossref.org/works/{quote(doi, safe='')}",
            "openalex": f"https://api.openalex.org/works/https://doi.org/{doi}",
        }
    else:
        query = row["citation"]
        urls = {
            "crossref_search": "https://api.crossref.org/works?rows=8&query.bibliographic=" + quote(query),
            "openalex_search": "https://api.openalex.org/works?per-page=8&search=" + quote(query),
        }
    for provider, url in urls.items():
        get_json(url, RAW / f"{rid}_{provider}.json")
        time.sleep(0.12)

# Targeted issue search for the orphan fragment.
url = (
    "https://api.crossref.org/journals/1938-2057/works?filter="
    "from-pub-date:2016-01-01,until-pub-date:2016-12-31&rows=1000"
)
get_json(url, RAW / "COSZO-REF-150_crossref_issn_2016.json")

print(f"retrieved first-pass metadata for {len(records)} records")
