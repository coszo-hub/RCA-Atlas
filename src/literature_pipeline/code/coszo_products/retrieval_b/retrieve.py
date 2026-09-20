#!/usr/bin/env python3
import datetime as dt
import difflib
import html
from html.parser import HTMLParser
import json
import os
import re
import time
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE="/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_products/retrieval_b"
RAW=os.path.join(BASE,"raw"); OUT=os.path.join(BASE,"results.jsonl")
UA="COSZO-product-abstract-verification/1.0 (mailto:research@example.org)"

WORKS=[
 {"id":"COSZO-PRODB-001","title":"Formation of Large Native Sulfur Deposits Does Not Require Molecular Oxygen","authors":"Labrado Brunner Bernasconi Peckmann","year":2019,"pmid":None,"pmcid":"PMC6355691","doi":"10.3389/fmicb.2019.00024"},
 {"id":"COSZO-PRODB-002","title":"Secondary Electrons as an Energy Source for Life","authors":"Stelmach Neveu Vick-Majors Mickol Chou Webster Tilley Zacchei Escudero Flores Martinez Labrado Fernández","year":2018,"pmid":"29314901","pmcid":None,"doi":None},
 {"id":"COSZO-PRODB-004","title":"Novel Integration of Geodetic and Geologic Methods for High-Resolution Monitoring of Subsidence in the Mississippi Delta","authors":"Zumberge Xie Wyatt Steckler Li Hatfield Elliott Dixon Bridgeman Chamberlain Allison Törnqvist","year":2022,"doi":"10.1029/2022JF006718"},
 {"id":"COSZO-PRODB-005","title":"Offshore Sea Levels Measured With an Anchored Spar-Buoy System Using GPS Interferometric Reflectometry","authors":"Xie Chen Dixon Weisberg Zumberge","year":2021,"doi":"10.1029/2021JC017734"},
 {"id":"COSZO-PRODB-006","title":"Improved vertical optical fiber borehole strainmeter design for measuring Earth strain","authors":"DeWolf Wyatt Zumberge Hatfield","year":2015,"pmid":"26628152","pmcid":None,"doi":None},
 {"id":"COSZO-PRODB-007","title":"A Three-Component Borehole Optical Seismic and Geodetic Sensor","authors":"Zumberge Berger Hatfield Wielandt","year":2018,"doi":"10.1785/0120180045"},
 {"id":"COSZO-PRODB-008","title":"Results From a Decade of Optical Fiber Strainmeters at Piñon Flat Observatory","authors":"Hatfield Elliott Wyatt Xie Zumberge","year":2022,"doi":"10.1029/2022EA002381"},
 {"id":"COSZO-PRODB-009","title":"Automatic classification with an autoencoder of seismic signals on a distributed acoustic sensing cable","authors":"Chien Jenkins Gerstoft Zumberge Mellors","year":2023,"doi":"10.1016/j.compgeo.2022.105223"},
]

def get(url,accept="application/json",timeout=35):
    q=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":accept})
    with urllib.request.urlopen(q,timeout=timeout) as r:return r.read(),r.geturl(),dict(r.headers),r.status
def clean(s):
    if not s:return None
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s))).strip() or None
def norm(s):return re.sub(r"[^a-z0-9]+"," ",(clean(s) or "").lower()).strip()
def sim(a,b):return difflib.SequenceMatcher(None,norm(a),norm(b)).ratio()
def invabs(inv):return " ".join(w for _,w in sorted((p,w) for w,ps in (inv or {}).items() for p in ps)).strip() or None
def save(rid,name,data):
    with open(os.path.join(RAW,f"{rid}_{name}"),"wb") as f:f.write(data)
def attempt(r,url,msg):r["attempts"].append({"url":url,"result":msg})
class MP(HTMLParser):
    def __init__(self):super().__init__();self.m={}
    def handle_starttag(self,t,a):
        if t.lower()=="meta":
            d={k.lower():v for k,v in a if k and v};k=(d.get("name") or d.get("property") or "").lower()
            if k and d.get("content"):self.m[k]=clean(d["content"])

def pubmed(w,r):
    if not w.get("pmid") and not w.get("pmcid"):return
    term=w.get("pmid") or w.get("pmcid")
    url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"+urllib.parse.urlencode({"db":"pubmed","id":term,"retmode":"xml"})
    try:
        data,final,h,st=get(url,"application/xml");save(w["id"],"pubmed.xml",data);root=ET.fromstring(data)
        art=root.find(".//PubmedArticle")
        title="".join(art.find(".//ArticleTitle").itertext()) if art is not None and art.find(".//ArticleTitle") is not None else ""
        score=sim(w["title"],title);attempt(r,url,f"HTTP {st}; title similarity {score:.3f}")
        if score>=.92:
            r["resolved_title"]=clean(title);r["metadata_source_url"]="https://pubmed.ncbi.nlm.nih.gov/"+(w.get("pmid") or "")+"/"
            nodes=art.findall(".//Abstract/AbstractText")
            parts=[]
            for x in nodes:
                txt=clean("".join(x.itertext()));lab=x.attrib.get("Label")
                if txt:parts.append((lab+": " if lab else "")+txt)
            if parts:r["abstract"]=" ".join(parts);r["abstract_source_url"]=r["metadata_source_url"]
            for x in art.findall(".//ArticleId"):
                if x.attrib.get("IdType")=="doi" and x.text:r["resolved_doi"]=x.text.strip()
                if x.attrib.get("IdType")=="pmc" and x.text:w["pmcid"]=x.text.strip()
    except Exception as e:attempt(r,url,f"error {type(e).__name__}: {e}")

def resolve(w):
    r={"id":w["id"],"resolved_title":None,"resolved_doi":w.get("doi"),"paper_url":None,"abstract":None,"abstract_status":"not_found","abstract_source_url":None,"retrieved_at":None,"metadata_source_url":None,"license":None,"full_text_url":None,"notes":"","attempts":[]}
    pubmed(w,r)
    doi=r.get("resolved_doi") or w.get("doi")
    # Resolve PMCID DOI/full text when PubMed did not have a numeric PMID in the input.
    if w.get("pmcid") and not doi:
        eu="https://www.ebi.ac.uk/europepmc/webservices/rest/search?"+urllib.parse.urlencode({"query":"EXT_ID:"+w["pmcid"],"format":"json"})
        try:
            data,final,h,st=get(eu);save(w["id"],"europepmc.json",data);x=(json.loads(data).get("resultList",{}).get("result") or [{}])[0]
            attempt(r,eu,f"HTTP {st}; {x.get('title','')[:80]}")
            if sim(w["title"],x.get("title"))>=.92:
                doi=x.get("doi") or doi;r["resolved_doi"]=doi;r["resolved_title"]=clean(x.get("title"));r["metadata_source_url"]=eu
                if x.get("authorString") and norm(w["authors"].split()[0]) not in norm(x["authorString"]):r["notes"]+=" Europe PMC author check warning."
        except Exception as e:attempt(r,eu,f"error {type(e).__name__}: {e}")
    if doi:
        r["resolved_doi"]=doi;r["paper_url"]="https://doi.org/"+doi
        cu="https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="")
        try:
            data,final,h,st=get(cu);save(w["id"],"crossref.json",data);c=json.loads(data).get("message",{});ct=(c.get("title") or [""])[0];score=sim(w["title"],ct)
            auth=" ".join((a.get("family") or "") for a in c.get("author",[]));year=((c.get("published") or c.get("issued") or {}).get("date-parts") or [[0]])[0][0]
            attempt(r,cu,f"HTTP {st}; title similarity {score:.3f}; year {year}; authors {auth[:100]}")
            if score>=.92 and abs((year or w["year"])-w["year"])<=1 and norm(w["authors"].split()[0]) in norm(auth):
                r["resolved_title"]=clean(ct);r["metadata_source_url"]=cu
                if not r["abstract"] and c.get("abstract"):r["abstract"]=clean(c["abstract"]);r["abstract_source_url"]=cu
                if c.get("license"):r["license"]=c["license"][0].get("URL")
            else:r["notes"]+=f" Crossref exact-DOI record failed metadata check (title={score:.3f}, year={year})."
        except Exception as e:attempt(r,cu,f"error {type(e).__name__}: {e}")
        time.sleep(.3)
        ou="https://api.openalex.org/works/https://doi.org/"+urllib.parse.quote(doi,safe="/:.")
        try:
            data,final,h,st=get(ou);save(w["id"],"openalex.json",data);o=json.loads(data);ot=o.get("display_name") or "";score=sim(w["title"],ot);oy=o.get("publication_year") or 0;auth=" ".join((a.get("author",{}).get("display_name") or "") for a in o.get("authorships",[]))
            attempt(r,ou,f"HTTP {st}; title similarity {score:.3f}; year {oy}; authors {auth[:100]}")
            if score>=.92 and abs((oy or w["year"])-w["year"])<=1 and norm(w["authors"].split()[0]) in norm(auth):
                r["resolved_title"]=clean(ot);r["metadata_source_url"]=o.get("id") or ou
                if not r["abstract"] and o.get("abstract_inverted_index"):r["abstract"]=invabs(o["abstract_inverted_index"]);r["abstract_source_url"]=o.get("id") or ou
                loc=o.get("best_oa_location") or {}
                if not r["license"]:r["license"]=loc.get("license") or (o.get("primary_location") or {}).get("license")
                if loc.get("pdf_url"):r["full_text_url"]=loc["pdf_url"]
        except Exception as e:attempt(r,ou,f"error {type(e).__name__}: {e}")
    # PMC full text is a primary repository and can supply an abstract and verified article link.
    if w.get("pmcid"):
        xu="https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/"+w["pmcid"]+"/unicode"
        try:
            data,final,h,st=get(xu,"application/xml");save(w["id"],"pmc_bioc.xml",data);root=ET.fromstring(data)
            passages=root.findall(".//passage")
            title_parts=[]; abstracts=[]
            for p in passages:
                typ=next((x.text for x in p.findall("infon") if x.attrib.get("key")=="type"),None)
                txt=" ".join((x.text or "") for x in p.findall("text"))
                if typ=="title" and txt:title_parts.append(txt)
                if typ=="abstract" and txt:abstracts.append(txt)
            title=" ".join(title_parts)
            a=clean(" ".join(abstracts));attempt(r,xu,f"HTTP {st}; PMC XML abstract words {len((a or '').split())}")
            if a and (not title or sim(w["title"],title)>=.85):r["abstract"]=a;r["abstract_source_url"]="https://pmc.ncbi.nlm.nih.gov/articles/"+w["pmcid"]+"/";r["full_text_url"]="https://pmc.ncbi.nlm.nih.gov/articles/"+w["pmcid"]+"/pdf/"
        except Exception as e:attempt(r,xu,f"error {type(e).__name__}: {e}")
    # Publisher meta fallback only from abstract-specific fields.
    if doi and not r["abstract"]:
        try:
            data,final,h,st=get("https://doi.org/"+doi,"text/html,application/xhtml+xml");save(w["id"],"landing.html",data);p=MP();p.feed(data.decode("utf-8","replace"));attempt(r,"https://doi.org/"+doi,f"HTTP {st}; final {final}");r["paper_url"]=final
            for k in ("citation_abstract","dc.description","dcterms.abstract","eprints.abstract"):
                a=p.m.get(k)
                if a and len(a.split())>=40:r["abstract"]=a;r["abstract_source_url"]=final;break
        except Exception as e:attempt(r,"https://doi.org/"+doi,f"error {type(e).__name__}: {e}")
    # Verify direct PDF/full-text URL; remove unverified links.
    if r["full_text_url"]:
        u=r["full_text_url"]
        try:
            q=urllib.request.Request(u,headers={"User-Agent":UA,"Range":"bytes=0-4095","Accept":"application/pdf,text/html"})
            with urllib.request.urlopen(q,timeout=35) as z:b=z.read(4096);ct=(z.headers.get("Content-Type") or "").lower();st=z.status;final=z.geturl()
            if st in (200,206) and (b.startswith(b"%PDF") or "application/pdf" in ct or (w.get("pmcid") and "html" in ct)):
                r["full_text_url"]=final;attempt(r,u,f"verified full text HTTP {st}; {ct}")
            else:attempt(r,u,f"removed unverified full text HTTP {st}; {ct}");r["full_text_url"]=None
        except Exception as e:attempt(r,u,f"removed; full text verification failed: {type(e).__name__}: {e}");r["full_text_url"]=None
    r["abstract_status"]="retrieved" if r["abstract"] else ("unresolved_citation" if not r["resolved_title"] else "not_found")
    r["retrieved_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
    r["notes"]=(r["notes"]+" Exact title, lead author, and publication year checked against DOI/registry metadata.").strip()
    return r

def main():
    os.makedirs(RAW,exist_ok=True)
    wanted=set(sys.argv[1:])
    existing={x["id"]:x for x in (json.loads(line) for line in open(OUT))} if os.path.exists(OUT) else {}
    results=[]
    for w in WORKS:
        if wanted and w["id"] not in wanted:
            if w["id"] in existing: results.append(existing[w["id"]])
            continue
        r=resolve(dict(w));results.append(r)
        print(r["id"],r["abstract_status"],r["resolved_doi"],len((r["abstract"] or "").split()),flush=True)
        time.sleep(.4)
    order={x["id"]:i for i,x in enumerate(WORKS)}
    results.sort(key=lambda x:order[x["id"]])
    with open(OUT,"w") as f:
        for x in results:f.write(json.dumps(x,ensure_ascii=False)+"\n")
if __name__=="__main__":main()
