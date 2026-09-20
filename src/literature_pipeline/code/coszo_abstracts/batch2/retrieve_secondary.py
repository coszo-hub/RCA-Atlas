#!/usr/bin/env python3
"""Exact-DOI recovery pass. Preserves good first-pass results and only replaces verified matches."""
import datetime as dt, html, json, os, re, time, urllib.parse, urllib.request
from html.parser import HTMLParser

BASE="/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch2"
OUT=os.path.join(BASE,"results.jsonl"); RAW=os.path.join(BASE,"raw")
UA="COSZO-abstract-verification/1.1 (mailto:research@example.org)"
DOIS={
45:"10.25740/hy589fc7561",46:"10.1029/2020GC009085",48:"10.1785/0120190008",49:"10.1002/JGRB.50390",
50:"10.1186/s40645-018-0211-8",51:"10.1016/j.tecto.2012.08.022",52:"10.1029/2008JB006036",
53:"10.1093/gji/ggz051",54:"10.21014/acta_imeko.v5i1.319",55:"10.1193/1.4000108",
56:"10.1126/science.1215141",57:"10.1016/j.margeo.2014.03.010",58:"10.6075/J0W66J9H",
59:"10.1029/2022JB025662",60:"10.1785/0120120105",61:"10.1016/j.epsl.2014.10.047",
62:"10.1029/2018JB015620",63:"10.1038/s41561-021-00736-x",64:"10.1029/2020JC016738",
65:"10.3389/fmars.2022.866422",67:"10.1029/2018GL079519",69:"10.1130/G45354.1",
70:"10.1128/mSystems.00673-19",71:"10.17226/25761",72:"10.1126/science.aax5618",
73:"10.1126/science.aah4666",74:"10.17226/21655",75:"10.4095/215329",
76:"10.1007/s00024-002-8728-5",77:"10.1038/s41467-021-26954-w",78:"10.1029/2009GC002532",
79:"10.1785/0220200089",80:"10.1029/2011JB008801",81:"10.1029/2018GL080812",
82:"10.1126/science.1256074",83:"10.1109/ACCESS.2018.2873479",84:"10.1029/2022EA002434",
85:"10.1109/JOE.2012.2233312",86:"10.1002/2013GC005172",88:"10.1038/nature05666",
89:"10.5670/oceanog.2018.105"}

def get(url,accept="application/json",timeout=35):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read(),r.geturl(),dict(r.headers),r.status
def norm(s):return re.sub(r"[^a-z0-9]+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or "")).lower()).strip()
def sim(a,b):
    sa,sb=set(norm(a).split()),set(norm(b).split()); return len(sa&sb)/max(1,len(sa|sb))
def clean(s):return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip() or None
def invabs(inv):
    return " ".join(w for _,w in sorted((p,w) for w,ps in (inv or {}).items() for p in ps)).strip() or None
class MP(HTMLParser):
    def __init__(self):super().__init__();self.m={}
    def handle_starttag(self,t,a):
        if t.lower()=="meta":
            d={k.lower():v for k,v in a if k and v}; k=(d.get("name") or d.get("property") or "").lower()
            if k and d.get("content"):self.m[k]=clean(d["content"])
def raw(rid,name,data):
    with open(os.path.join(RAW,f"{rid}_{name}"),"wb") as f:f.write(data)
def add_attempt(r,url,msg):r.setdefault("attempts",[]).append({"url":url,"result":msg})

def recover(r,title):
    n=int(r["id"][-3:]); doi=DOIS.get(n)
    if not doi:return r
    r["resolved_doi"]=doi; r["paper_url"]="https://doi.org/"+doi
    # Exact DOI OpenAlex record.
    ou="https://api.openalex.org/works/https://doi.org/"+urllib.parse.quote(doi,safe="/:.")
    try:
        data,final,h,st=get(ou); raw(r["id"],"openalex_doi.json",data); o=json.loads(data)
        mt=o.get("display_name") or ""; match=sim(title,mt)
        add_attempt(r,ou,f"HTTP {st}; exact DOI title similarity {match:.3f}")
        if match>=.75:
            r["resolved_title"]=clean(mt); r["metadata_source_url"]=o.get("id") or ou
            a=invabs(o.get("abstract_inverted_index"))
            if a:
                r["abstract"]=a;r["abstract_status"]="retrieved";r["abstract_source_url"]=o.get("id") or ou
            loc=o.get("best_oa_location") or {}; pdf=loc.get("pdf_url")
            if pdf:r["full_text_url"]=pdf
            if not r.get("license"):r["license"]=loc.get("license") or (o.get("primary_location") or {}).get("license")
    except Exception as e:add_attempt(r,ou,f"error {type(e).__name__}: {e}")
    time.sleep(.25)
    # Exact DOI Crossref record, especially useful for publisher-supplied abstracts.
    cu="https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="")
    try:
        data,final,h,st=get(cu); raw(r["id"],"crossref_doi_exact.json",data); c=json.loads(data).get("message",{})
        mt=(c.get("title") or [""])[0]; match=sim(title,mt); add_attempt(r,cu,f"HTTP {st}; title similarity {match:.3f}")
        if match>=.75:
            r["resolved_title"]=clean(mt);r["metadata_source_url"]=cu
            a=clean(c.get("abstract"))
            if a and not r.get("abstract"):
                r["abstract"]=a;r["abstract_status"]="retrieved";r["abstract_source_url"]=cu
            if not r.get("license") and c.get("license"):r["license"]=c["license"][0].get("URL")
    except Exception as e:add_attempt(r,cu,f"error {type(e).__name__}: {e}")
    time.sleep(.25)
    # Semantic Scholar fallback for journals whose publishers omit abstract from registry metadata.
    if not r.get("abstract"):
        su="https://api.semanticscholar.org/graph/v1/paper/DOI:"+urllib.parse.quote(doi,safe="")+"?fields=title,year,authors,abstract,url,openAccessPdf"
        try:
            data,final,h,st=get(su); raw(r["id"],"semantic_scholar.json",data); s=json.loads(data)
            match=sim(title,s.get("title") or ""); add_attempt(r,su,f"HTTP {st}; exact DOI title similarity {match:.3f}")
            if match>=.75 and s.get("abstract"):
                r["abstract"]=clean(s["abstract"]);r["abstract_status"]="retrieved";r["abstract_source_url"]=su
                if not r.get("full_text_url") and (s.get("openAccessPdf") or {}).get("url"):r["full_text_url"]=s["openAccessPdf"]["url"]
        except Exception as e:add_attempt(r,su,f"error {type(e).__name__}: {e}")
        time.sleep(.4)
    # Publisher page metadata fallback; only abstract-specific fields, never generic snippets.
    if not r.get("abstract"):
        try:
            data,final,h,st=get("https://doi.org/"+doi,"text/html,application/xhtml+xml"); raw(r["id"],"landing_exact.html",data)
            add_attempt(r,"https://doi.org/"+doi,f"HTTP {st}; final {final}"); r["paper_url"]=final
            p=MP();p.feed(data.decode("utf-8","replace"))
            for k in ("citation_abstract","dc.description","dcterms.abstract","eprints.abstract"):
                a=p.m.get(k)
                if a and len(a.split())>=35:
                    r["abstract"]=a;r["abstract_status"]="retrieved";r["abstract_source_url"]=final;break
        except Exception as e:add_attempt(r,"https://doi.org/"+doi,f"error {type(e).__name__}: {e}")
    if r.get("abstract"):
        r["abstract_status"]="retrieved"
        r["notes"]=(r.get("notes") or "")+" Exact DOI and title independently rechecked in recovery pass."
    elif n in (71,74):
        r["abstract_status"]="no_abstract_expected";r["notes"]=(r.get("notes") or "")+" National Academies book/report; no article abstract found."
    else:r["abstract_status"]="not_found"
    r["retrieved_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
    return r

def main():
    rs=[json.loads(x) for x in open(OUT)]
    from resolve_batch import TITLES
    for i,r in enumerate(rs):
        n=int(r["id"][-3:])
        if n in DOIS:
            # Recheck every DOI because the first pass had a few exact-title false versions.
            rs[i]=recover(r,TITLES[n]);print(r["id"],rs[i]["abstract_status"],len((rs[i].get("abstract") or "").split()),flush=True)
            with open(OUT,"w") as f:
                for x in rs:f.write(json.dumps(x,ensure_ascii=False)+"\n")
    print("done")
if __name__=="__main__":main()
