from pathlib import Path
from pypdf import PdfReader

source = Path("/Users/quakehunter/Documents/RCN Agent /data/Project info/COSZO Project DataMSRI.pdf")
outdir = Path("/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/a")
reader = PdfReader(source)
for physical_page in range(33, 41):
    page = reader.pages[physical_page - 1]
    text = page.extract_text(extraction_mode="layout")
    (outdir / f"page_{physical_page:03d}_layout.txt").write_text(text, encoding="utf-8")
