#!/usr/bin/env python3
import json, urllib.request, datetime as dt
P="/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch2/results.jsonl"
rs=[json.loads(x) for x in open(P)]
for r in rs:
    u=r.get("full_text_url")
    if not u: continue
    # These are metadata/DOI landing pages, not links to full text.
    if r["id"] in ("COSZO-REF-083","COSZO-REF-086"):
        r.setdefault("attempts",[]).append({"url":u,"result":"removed from full_text_url: metadata/DOI landing page, not a direct full-text link"})
        r["full_text_url"]=None; continue
    try:
        req=urllib.request.Request(u,headers={"User-Agent":"COSZO-link-verification/1.0","Range":"bytes=0-4095","Accept":"application/pdf,text/html"})
        with urllib.request.urlopen(req,timeout=35) as z:
            b=z.read(4096); final=z.geturl(); ct=(z.headers.get("Content-Type") or "").lower(); st=z.status
        is_pdf=b.startswith(b"%PDF") or "application/pdf" in ct
        if st in (200,206) and is_pdf:
            r["full_text_url"]=final
            r.setdefault("attempts",[]).append({"url":u,"result":f"verified direct full text HTTP {st}; {ct}"})
        else:
            r["full_text_url"]=None
            r.setdefault("attempts",[]).append({"url":u,"result":f"removed: not verified as direct PDF; HTTP {st}; {ct}"})
    except Exception as e:
        r["full_text_url"]=None
        r.setdefault("attempts",[]).append({"url":u,"result":f"removed: direct full text verification failed: {type(e).__name__}: {e}"})
with open(P,"w") as f:
    for r in rs:f.write(json.dumps(r,ensure_ascii=False)+"\n")
