import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


BASE = Path(__file__).parent
SOURCE = BASE.parent / "coszo_products" / "zotero_E5UH7L89_top1.json"
OUT = BASE / "endurance_crossref.json"


def fetch(doi: str) -> tuple[str, dict]:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "COSZO-Zotero-Audit/1.0 (mailto:metadata-audit@example.org)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        message = payload.get("message", {})
        return doi, {
            "status": "retrieved",
            "url": url,
            "title": (message.get("title") or [None])[0],
            "type": message.get("type"),
            "published": message.get("published") or message.get("issued"),
            "abstract": message.get("abstract"),
            "publisher": message.get("publisher"),
            "container_title": (message.get("container-title") or [None])[0],
        }
    except Exception as exc:
        return doi, {"status": "error", "url": url, "error": repr(exc)}


items = json.loads(SOURCE.read_text())
dois = sorted({i["data"].get("DOI", "").strip() for i in items if i["data"].get("DOI", "").strip()})
records = {}
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(fetch, doi): doi for doi in dois}
    for future in as_completed(futures):
        doi, result = future.result()
        records[doi] = result
        time.sleep(0.05)

OUT.write_text(json.dumps({"source": str(SOURCE), "records": records}, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({"dois": len(dois), "retrieved": sum(r["status"] == "retrieved" for r in records.values()), "errors": {d: r for d, r in records.items() if r["status"] != "retrieved"}}, indent=2))
