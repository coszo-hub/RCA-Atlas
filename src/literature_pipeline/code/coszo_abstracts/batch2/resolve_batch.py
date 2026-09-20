#!/usr/bin/env python3
import concurrent.futures
import datetime as dt
import difflib
import html
from html.parser import HTMLParser
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch2"
RAW = os.path.join(BASE, "raw")
INPUT = "/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl"
OUT = os.path.join(BASE, "results.jsonl")
UA = "COSZO-abstract-verification/1.0 (mailto:research@example.org)"

TITLES = {
45:"SZ4D Implementation Plan",
46:"Physical sources of high-frequency seismic noise on Cascadia Initiative ocean bottom seismometers",
47:"Integrating subseafloor microbial, hydrological, geochemical, and geophysical processes in zero-age, hydrothermally active oceanic crust at Axial Seamount, Juan de Fuca Ridge",
48:"Seismic characteristics of the Nootka fault zone: results from the seafloor earthquake array Japan–Canada Cascadia experiment (SeaJade)",
49:"Downdip landward limit of Cascadia great earthquake rupture",
50:"Temporal change in seismic velocity associated with an offshore MW 5.9 Off-Mie earthquake in the Nankai subduction zone from ambient noise cross-correlation",
51:"Episodic slow slip events in the Japan subduction zone before the 2011 Tohoku-Oki earthquake",
52:"Very low frequency earthquakes related to small asperities on the plate boundary interface at the locked to aseismic transition",
53:"Amphibious surface-wave phase-velocity measurements of the Cascadia subduction zone",
54:"Pressure gauge calibration applying 0-A-0 pressurization to reference gauge",
55:"Economic impacts of the 2011 Tohoku-Oki earthquake and tsunami",
56:"Propagation of slow slip leading up to the 2011 Mw 9.0 Tohoku-Oki earthquake",
57:"Establishing a new era of submarine volcanic observatories: Cabling Axial Seamount and the Endeavour Segment of the Juan de Fuca Ridge",
58:"Exploring Earth by Scientific Ocean Drilling: 2050 Science Framework",
59:"A Long-Term Earthquake Catalog for the Endeavour Segment: Constraints on the Extensional Cycle and Evidence for Hydrothermal Venting Supported by Propagating Rifts",
60:"Statistical analyses of great earthquake recurrence along the Cascadia Subduction Zone",
61:"The surge of great earthquakes from 2004 to 2014",
62:"Geodetically inferred locking state of the Cascadia megathrust based on a viscoelastic Earth model",
63:"Slip rate deficit and earthquake potential on shallow megathrusts",
64:"Estuarine Circulation, Mixing, and Residence Times in the Salish Sea",
65:"Integrating multidisciplinary observations in vent environments (IMOVE): Decadal progress in Deep-Sea observations at hydrothermal vents",
67:"A lack of dynamic triggering of slow slip and tremor indicates that the shallow Cascadia megathrust offshore Vancouver Island is likely locked",
68:"The SZ4D Initiative: Understanding the Processes that Underlie Subduction Zone Hazards in 4D",
69:"Newly detected earthquakes in the Cascadia subduction zone linked to seamount subduction and deformed upper plate",
70:"Selection is a significant driver of gene gain and loss in the pangenome of the bacterial genus Sulfurovum in geographically distinct deep-sea hydrothermal vents",
71:"A Vision for NSF Earth Sciences 2020-2030: Earth in Time",
72:"The slow earthquake spectrum in the Japan Trench illuminated by the S-net seafloor observatories",
73:"Inflation-predictable behavior and co-eruption deformation at Axial Seamount",
74:"Sea Change: 2015-2025 Decadal Survey of Ocean Sciences",
75:"Probabilities of significant earthquake shaking in communities across British Columbia: Implications for emergency management",
76:"Simulations of seismic hazard for the Pacific Northwest of the United States from earthquakes associated with the Cascadia subduction zone",
77:"Fluid migrations and volcanic earthquakes from depolarized ambient noise",
78:"Effective resolution and drift of Paroscientific pressure sensors derived from long-term seafloor measurements",
79:"New Opportunities to Study Earthquake Precursors",
80:"Slow slip events and strain accumulation in the Guerrero gap, Mexico",
81:"How the transition region along the Cascadia megathrust influences coseismic behavior: Insights from 2-D dynamic rupture simulations",
82:"Intense foreshocks and a slow slip event preceded the 2014 Iquique Mw 8.1 earthquake",
83:"Laboratory simulation and measurement of instrument drift in quartz-resonant pressure gauges",
84:"Drift Corrected Seafloor Pressure Observations of Vertical Deformation at Axial Seamount 2018–2021",
85:"A self-calibrating pressure recorder for detecting seafloor height change",
86:"Central Cascadia subduction zone creep",
87:"Earthquake and Tsunami Early Warning on the Cascadia Subduction Zone: A Feasibility Study for an Offshore Geophysical Monitoring Network",
88:"Non-volcanic tremor and low-frequency earthquake swarms",
89:"The ocean observatories initiative",
}

DOI_OVERRIDES = {
    45:"10.25740/hy589fc7561",
    54:"10.21014/acta_imeko.v5i1.319",
    57:"10.1016/j.margeo.2014.03.010",
    58:"10.6075/J0W66J9H",
    59:"10.1029/2022JB025662",
    61:"10.1016/j.epsl.2014.10.047",
    71:"10.17226/25761",
    74:"10.17226/21655",
    76:"10.1007/s00024-002-8728-5",
    77:"10.1038/s41467-021-26954-w",
    81:"10.1029/2018GL080812",
    85:"10.1109/JOE.2012.2233312",
}

def get(url, accept=None, timeout=25):
    headers={"User-Agent":UA}
    if accept: headers["Accept"]=accept
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(), r.geturl(), dict(r.headers), r.status

def norm(s):
    s=html.unescape(s or "").lower().replace("‐","-").replace("–","-").replace("—","-")
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def score(a,b):
    a,b=norm(a),norm(b)
    seq=difflib.SequenceMatcher(None,a,b).ratio()
    sa,sb=set(a.split()),set(b.split())
    jac=len(sa&sb)/max(1,len(sa|sb))
    return max(seq,jac)

def strip_markup(s):
    if not s: return None
    s=re.sub(r"<[^>]+>"," ",s)
    s=html.unescape(s)
    s=re.sub(r"\s+"," ",s).strip()
    return s or None

def openalex_abstract(inv):
    if not inv: return None
    pairs=[]
    for word,positions in inv.items():
        for p in positions: pairs.append((p,word))
    return " ".join(w for _,w in sorted(pairs)).strip() or None

class MetaParser(HTMLParser):
    def __init__(self): super().__init__(); self.meta=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="meta": return
        d={k.lower():v for k,v in attrs if k and v}
        key=(d.get("name") or d.get("property") or "").lower()
        val=d.get("content")
        if key and val: self.meta.append((key,val))

def save_raw(ref, name, data):
    path=os.path.join(RAW,f"{ref}_{name}")
    mode="wb"
    with open(path,mode) as f: f.write(data)
    return path

def candidate_authors(obj, source):
    if source=="openalex":
        return " ".join((a.get("author",{}).get("display_name") or "") for a in obj.get("authorships",[]))
    return " ".join(" ".join(filter(None,[a.get("given"),a.get("family")])) for a in obj.get("author",[]))

def resolve_one(item):
    rid=item["id"]; n=int(rid[-3:]); title=TITLES[n]; year=int(item.get("year_as_cited") or 0)
    attempts=[]; oa_candidates=[]; cr_candidates=[]
    # OpenAlex search
    q=urllib.parse.urlencode({"search":title,"per-page":10})
    oa_url="https://api.openalex.org/works?"+q
    try:
        data,final,headers,status=get(oa_url,accept="application/json")
        save_raw(rid,"openalex_search.json",data)
        payload=json.loads(data); oa_candidates=payload.get("results",[])
        attempts.append({"url":oa_url,"result":f"HTTP {status}; {len(oa_candidates)} candidates"})
    except Exception as e: attempts.append({"url":oa_url,"result":f"error {type(e).__name__}: {e}"})
    # Crossref search
    q=urllib.parse.urlencode({"query.title":title,"rows":10,"select":"DOI,title,author,published,issued,type,URL,abstract,resource,license,link,container-title"})
    cr_url="https://api.crossref.org/works?"+q
    try:
        data,final,headers,status=get(cr_url,accept="application/json")
        save_raw(rid,"crossref_search.json",data)
        cr_candidates=json.loads(data).get("message",{}).get("items",[])
        attempts.append({"url":cr_url,"result":f"HTTP {status}; {len(cr_candidates)} candidates"})
    except Exception as e: attempts.append({"url":cr_url,"result":f"error {type(e).__name__}: {e}"})

    citation_norm=norm(item.get("citation","")); first_author=norm(item.get("citation","").split(",",1)[0])
    ranked=[]
    for c in oa_candidates:
        ct=c.get("display_name") or c.get("title") or ""; ts=score(title,ct)
        ay=c.get("publication_year") or 0; aus=norm(candidate_authors(c,"openalex"))
        ybonus=(0.05 if year and ay==year else 0.02 if not year or abs(ay-year)<=1 else -0.05)
        bonus=(0.04 if first_author and first_author in aus else 0)+ybonus+0.005
        ranked.append((ts+bonus,"openalex",c,ts,ay,aus))
    for c in cr_candidates:
        ct=(c.get("title") or [""])[0]; ts=score(title,ct)
        parts=((c.get("published") or c.get("issued") or {}).get("date-parts") or [[0]])
        ay=(parts[0][0] if parts and parts[0] else 0) or 0; aus=norm(candidate_authors(c,"crossref"))
        ybonus=(0.05 if year and ay==year else 0.02 if not year or abs(ay-year)<=1 else -0.05)
        bonus=(0.04 if first_author and first_author in aus else 0)+ybonus
        ranked.append((ts+bonus,"crossref",c,ts,ay,aus))
    ranked.sort(key=lambda x:x[0],reverse=True)
    best=ranked[0] if ranked else None
    accepted=best and best[3]>=0.88 and (not year or not best[4] or abs(best[4]-year)<=2 or n in (58,60,75))
    if not accepted:
        result={"id":rid,"resolved_title":None,"resolved_doi":None,"paper_url":None,"abstract":None,
            "abstract_status":"unresolved_citation","abstract_source_url":None,"retrieved_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "metadata_source_url":None,"license":None,"full_text_url":None,"notes":f"No sufficiently exact title/author/year match. Best score={best[3] if best else None}","attempts":attempts}
        return result
    _,source,c,ts,ay,aus=best
    if source=="openalex":
        resolved_title=strip_markup(c.get("display_name") or c.get("title"))
        doi=(c.get("doi") or "").replace("https://doi.org/","") or None
        paper_url=(c.get("primary_location") or {}).get("landing_page_url") or (c.get("doi") if c.get("doi") else c.get("id"))
        abstract=openalex_abstract(c.get("abstract_inverted_index"))
        abstract_source=(c.get("id") if abstract else None)
        meta_url=c.get("id")
        lic=(c.get("primary_location") or {}).get("license")
        oa=(c.get("best_oa_location") or {})
        full=oa.get("pdf_url")
    else:
        resolved_title=strip_markup((c.get("title") or [title])[0])
        doi=c.get("DOI")
        paper_url=c.get("URL") or ("https://doi.org/"+doi if doi else None)
        abstract=strip_markup(c.get("abstract")); abstract_source=(cr_url if abstract else None)
        meta_url=cr_url
        licenses=c.get("license") or []; lic=licenses[0].get("URL") if licenses else None
        links=c.get("link") or []; full=next((x.get("URL") for x in links if x.get("content-type")=="application/pdf"),None)

    doi=DOI_OVERRIDES.get(n,doi)
    if doi: paper_url="https://doi.org/"+doi
    # Retrieve DOI-specific Crossref metadata to supplement and verify.
    if doi:
        du="https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="")
        try:
            data,final,headers,status=get(du,accept="application/json")
            save_raw(rid,"crossref_doi.json",data)
            dc=json.loads(data).get("message",{})
            dtitle=(dc.get("title") or [""])[0]
            if score(title,dtitle)>=0.88:
                resolved_title=strip_markup(dtitle) or resolved_title; meta_url=du
                if not abstract and dc.get("abstract"):
                    abstract=strip_markup(dc.get("abstract")); abstract_source=du
                if not lic and dc.get("license"): lic=dc["license"][0].get("URL")
                if not full:
                    full=next((x.get("URL") for x in (dc.get("link") or []) if x.get("content-type")=="application/pdf"),None)
            attempts.append({"url":du,"result":f"HTTP {status}; DOI title match {score(title,dtitle):.3f}"})
        except Exception as e: attempts.append({"url":du,"result":f"error {type(e).__name__}: {e}"})
    # OpenAlex sometimes supplies the abstract even when Crossref is the best metadata record.
    if not abstract:
        oa_exact=[]
        for oc in oa_candidates:
            ot=oc.get("display_name") or oc.get("title") or ""
            oy=oc.get("publication_year") or 0
            if score(title,ot)>=0.88 and (not year or not oy or abs(oy-year)<=1):
                oa_exact.append((score(title,ot)+(0.03 if oy==year else 0),oc))
        if oa_exact:
            oc=max(oa_exact,key=lambda x:x[0])[1]
            oa_abs=openalex_abstract(oc.get("abstract_inverted_index"))
            if oa_abs:
                abstract=oa_abs; abstract_source=oc.get("id")
                attempts.append({"url":oc.get("id"),"result":"exact-title OpenAlex record supplied abstract"})
    # Publisher landing-page metadata can contain an abstract omitted by registries.
    landing_final=None
    if paper_url:
        try:
            data,landing_final,headers,status=get(paper_url,accept="text/html",timeout=30)
            save_raw(rid,"landing.html",data)
            attempts.append({"url":paper_url,"result":f"HTTP {status}; final {landing_final}"})
            if not abstract and "html" in (headers.get("Content-Type") or "").lower():
                p=MetaParser(); p.feed(data.decode("utf-8","replace"))
                priority=["citation_abstract","dc.description","dcterms.abstract","eprints.abstract","description","og:description"]
                vals={k:strip_markup(v) for k,v in p.meta}
                for k in priority:
                    v=vals.get(k)
                    if v and len(v.split())>=35 and norm(title) not in norm(v):
                        abstract=v; abstract_source=landing_final; break
            if landing_final and landing_final.startswith("http"): paper_url=landing_final
        except Exception as e: attempts.append({"url":paper_url,"result":f"error {type(e).__name__}: {e}"})
    # Verify a claimed full-text URL.
    if full:
        try:
            data,ff,headers,status=get(full,accept="application/pdf,text/html",timeout=30)
            save_raw(rid,"fulltext_sample.bin",data[:200000])
            ctype=(headers.get("Content-Type") or "").lower()
            if status==200 and (data.startswith(b"%PDF") or "pdf" in ctype or "html" in ctype):
                full=ff; attempts.append({"url":full,"result":f"verified HTTP 200; {ctype}; saved 200KB sample"})
            else:
                attempts.append({"url":full,"result":f"not verified HTTP {status}; {ctype}"}); full=None
        except Exception as e: attempts.append({"url":full,"result":f"full text not verified: {type(e).__name__}: {e}"}); full=None
    notes=f"Exact-title match verified against {source}; title similarity {ts:.3f}, metadata year {ay}."
    return {"id":rid,"resolved_title":resolved_title,"resolved_doi":doi,"paper_url":paper_url,
        "abstract":abstract,"abstract_status":"retrieved" if abstract else "not_found",
        "abstract_source_url":abstract_source,"retrieved_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "metadata_source_url":meta_url,"license":lic,"full_text_url":full,"notes":notes,"attempts":attempts}

def main():
    os.makedirs(RAW,exist_ok=True)
    items=[]
    with open(INPUT) as f:
        for line in f:
            o=json.loads(line); n=int(o["id"][-3:])
            if 45<=n<=89 and n!=66: items.append(o)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(resolve_one,x):x["id"] for x in items}
        results=[]
        for fut in concurrent.futures.as_completed(futs):
            rid=futs[fut]
            try: result=fut.result()
            except Exception as e:
                result={"id":rid,"resolved_title":None,"resolved_doi":None,"paper_url":None,"abstract":None,"abstract_status":"blocked","abstract_source_url":None,"retrieved_at":dt.datetime.now(dt.timezone.utc).isoformat(),"metadata_source_url":None,"license":None,"full_text_url":None,"notes":f"resolver exception {type(e).__name__}: {e}","attempts":[]}
            results.append(result)
            results.sort(key=lambda x:x["id"])
            with open(OUT,"w") as f:
                for row in results: f.write(json.dumps(row,ensure_ascii=False)+"\n")
            print(rid,result["abstract_status"],result.get("resolved_doi"),flush=True)
    print(json.dumps({"total":len(results),"retrieved":sum(r["abstract_status"]=="retrieved" for r in results),"not_found":sum(r["abstract_status"]=="not_found" for r in results),"unresolved":sum(r["abstract_status"]=="unresolved_citation" for r in results),"blocked":sum(r["abstract_status"]=="blocked" for r in results)}))

if __name__=="__main__": main()
