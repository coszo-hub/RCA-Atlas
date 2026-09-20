"""Merge records recovered from a timed-out Interactive Oceans API batch."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
records_path = root / "wp_records.json"
candidates_path = root / "html_candidates.json"
records = json.loads(records_path.read_text())
candidates = json.loads(candidates_path.read_text())

files = [Path(f"/tmp/io_pages_{n}.json") for n in (29, 30, 151, 152, 153, 155, 157, 158, 159, 160)]
files += [Path(f"/tmp/io_page_{n}.json") for n in (766, 767, 768, 770, 776, 777, 778, 780)]
added = 0
for path in files:
    if not path.exists():
        continue
    for row in json.loads(path.read_text()):
        url = row["link"].replace("http://", "https://").replace("www.", "")
        if url not in records:
            added += 1
        records[url] = {**row, "site_host": "interactiveoceans.washington.edu"}

for path in (Path("/tmp/io_page_769_meta.json"), Path("/tmp/io_page_779_meta.json")):
    row = json.loads(path.read_text())[0]
    url = row["link"].replace("http://", "https://").replace("www.", "")
    candidates[url] = {
        "url": url,
        "site_host": "interactiveoceans.washington.edu",
        "discovery": "api_metadata_html_fallback",
    }

records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
candidates_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"records": len(records), "added": added, "html_candidates": len(candidates)}))
