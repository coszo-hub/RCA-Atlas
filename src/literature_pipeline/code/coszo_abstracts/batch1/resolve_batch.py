#!/usr/bin/env python3
import concurrent.futures as cf
import html, json, re, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

OUT=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1')
RAW=OUT/'raw'; SRC=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')
UA='COSZO bibliography abstract verification (scholarly metadata retrieval)'

def fetch(url, accept='application/json', timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':accept})
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read()
def fetchj(url): return json.loads(fetch(url).decode())
def norm(s):
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()).split())
def sim(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()
def inv(inv):
    if not inv:return None
    return ' '.join(w for _,w in sorted((p,w) for w,ps in inv.items() for p in ps))
def strip(s): return ' '.join(html.unescape(re.sub(r'<[^>]+>',' ',s or '')).split()) or None

titles={
1:'Recurring and triggered slow-slip events near the trench at the Nankai Trough subduction megathrust',
2:'Characteristics of slow slip event in March 2020 revealed from borehole and DONET observatories',
3:'Seismic imaging of the internal workings of Axial Seamount on the Juan de Fuca Ridge',
4:'Future geophysical facilities required to address grand challenges in the Earth sciences',
5:'Evidence for great Holocene earthquakes along the outer coast of Washington State',
6:'The orphan tsunami of 1700—Japanese clues to a parent earthquake in North America',
7:'Collaborative Research: Deployment of Seafloor Optical Fiber Strainmeters for the Detection of Slow Slip Events',
8:'A long-term view of episodic tremor and slip in Cascadia',
9:'Long-Term Observations of Subseafloor Temperatures and Pressures in a Low-Temperature, Off-Axis Hydrothermal System in North Pond on the Western Flank of the Mid-Atlantic Ridge',
10:'No progress on diversity in 40 years',
11:'Stacked sills forming a deep melt-mush feeder conduit beneath Axial Seamount',
12:'Vertical deformation of the Axial Seamount Summit from Repeated 1-m scale bathymetry surveys using AUVs',
13:'Mission Parameter Files and Documentation for GNSS-A data in Cascadia',
14:'Collaborative Research: Multi-scale Geodetic Monitoring at Axial Seamount',
15:'Seafloor deformation and forecasts of the April 2011 eruption at Axial Seamount',
16:'Monitoring transient changes within overpressured regions of subduction zones using ambient seismic noise',
17:'Widespread Very Low Frequency Earthquakes (VLFEs) Activity Offshore Cascadia',
18:"The Seismic Signature of California's Earthquakes, Droughts, and Floods",
19:'Calibrated absolute seafloor pressure measurements for geodesy in Cascadia',
20:'Identifying and removing tilt noise from low-frequency (< 0.1 Hz) seafloor vertical seismic data',
21:'Cascadia Subduction Zone Earthquakes: A Magnitude 9.0 Earthquake Scenario',
22:'Slow and delayed deformation and uplift of the outermost subduction prism following ETS and seismogenic slip events beneath Nicoya Peninsula, Costa Rica',
23:'A Foundation for Innovation: Grand Challenges in Geodesy',
24:'Horizontal deformation rates near the Cascadia subduction zone trench revealed by offshore GNSS-Acoustic time series',
25:'The State of Locking near the Deformation Front of the Central Cascadia Subduction Zone from GNSS-Acoustic',
26:'Characterization of modern and historical seismic–tsunamic events and their global–societal impacts',
27:'The January 1998 earthquake swarm at Axial Volcano, Juan de Fuca Ridge: Hydroacoustic evidence of seafloor volcanic activity',
28:'Very low frequency earthquakes in between the seismogenic and tremor zones in Cascadia?',
29:'LiveOcean',30:'Five years of ground deformation monitoring on Axial Seamount using a bottom pressure recorder',
31:'Improved Seafloor Geodetic Techniques for Understanding Plate Boundary Processes',
32:'Optimizing sensor configurations for the detection of slow-slip earthquakes in seafloor pressure records, using the Cascadia subduction zone as a case study',
33:'Measuring the Restless Earth: Grand Challenges in Geodesy',
34:'Diversity of magmatism, hydrothermal processes and microbial interactions at mid-ocean ridges',
35:'Diversifying the ocean sciences: Thoughts on the challenge ahead',
36:'Building a Diverse and Innovative Ocean Workforce through Collaboration and Partnerships that Integrate Research and Education: HBCUs and Marine Laboratories',
37:'Institutional Barriers, Strategies, and Benefits to Increasing the Representation of Women and Men of Color in the Professoriate',
38:'Oblique strike-slip faulting of the central Cascadia submarine forearc',
39:'Turbidite event history—Methods and implications for Holocene paleoseismicity of the Cascadia subduction zone',
40:'Reducing risk where tectonic plates collide—U.S. Geological Survey subduction zone science plan',
41:'The NOAA vents program 1983 to 2013: Thirty years of ocean exploration and research',
42:'Slab2, a comprehensive subduction zone geometry model',
43:'Seismic potential associated with subduction in the northwestern United States',
44:'Ocean networks Canada: From geohazards research laboratories to smart ocean systems'}

refs={}
for l in SRC.read_text().splitlines():
    x=json.loads(l); n=int(x['id'].split('-')[-1])
    if n<=44: refs[x['id']]=x
res={x['id']:x for x in map(json.loads,(OUT/'results.jsonl').read_text().splitlines())}

def resolve_one(rid):
    r=res[rid]; rec=refs[rid]; n=int(rid[-3:]); title=titles[n]; surname=norm(rec['citation'].split(',')[0]); year=None
    try: year=int(rec['year_as_cited'])
    except: pass
    attempts=[]; candidates=[]
    # Exact-title Crossref and OpenAlex searches correct parser misses and reject fuzzy title collisions.
    cu='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.title':title,'rows':8})
    try:
        cj=fetchj(cu); (RAW/f'{rid}_crossref_title.json').write_text(json.dumps(cj,ensure_ascii=False,indent=2)); attempts.append({'url':cu,'result':'exact-title Crossref response saved'})
        for x in cj.get('message',{}).get('items',[]):
            xt=(x.get('title') or [''])[0]; authors=' '.join(a.get('family','') for a in x.get('author',[])); yy=None
            for k in ('published-print','published-online','published','issued'):
                try: yy=x[k]['date-parts'][0][0]; break
                except: pass
            candidates.append((sim(title,xt),surname in norm(authors),yy,'crossref',x,cu))
    except Exception as e: attempts.append({'url':cu,'result':f'error {type(e).__name__}: {e}'})
    ou='https://api.openalex.org/works?'+urllib.parse.urlencode({'search':title,'per-page':10})
    try:
        oj=fetchj(ou); (RAW/f'{rid}_openalex_title.json').write_text(json.dumps(oj,ensure_ascii=False,indent=2)); attempts.append({'url':ou,'result':'exact-title OpenAlex response saved'})
        for x in oj.get('results',[]):
            xt=x.get('display_name') or ''; authors=' '.join(a.get('author',{}).get('display_name','') for a in x.get('authorships',[])); yy=x.get('publication_year')
            candidates.append((sim(title,xt),surname in norm(authors),yy,'openalex',x,ou))
    except Exception as e: attempts.append({'url':ou,'result':f'error {type(e).__name__}: {e}'})
    candidates.sort(reverse=True,key=lambda z:(z[0],z[1]))
    good=[c for c in candidates if c[0]>=.90 and c[1] and (not year or not c[2] or abs(c[2]-year)<=1)]
    if good:
        c=good[0]; x=c[4]; doi=x.get('DOI') if c[3]=='crossref' else (x.get('doi') or '').replace('https://doi.org/','') or None
        r.update(resolved_title=(x.get('title') or [''])[0] if c[3]=='crossref' else x.get('display_name'), resolved_doi=doi or r.get('resolved_doi'), paper_url=('https://doi.org/'+doi) if doi else (x.get('URL') or x.get('id')), metadata_source_url=c[5])
        a=strip(x.get('abstract')) if c[3]=='crossref' else inv(x.get('abstract_inverted_index'))
        if a and len(a.split())>=50 and (not r.get('abstract') or len(a.split())>len(r['abstract'].split())):
            r['abstract']=a; r['abstract_source_url']=c[5]
        r['notes']=(r.get('notes','')+f' Exact-title QA matched first author {surname}, title similarity {c[0]:.3f}, year {c[2]}.').strip()
    elif r.get('resolved_title') and sim(title,r['resolved_title'])<.88:
        r.update(resolved_title=None,resolved_doi=None,paper_url=None,abstract=None,abstract_source_url=None,metadata_source_url=None)
        r['notes']=(r.get('notes','')+' Existing fuzzy match rejected during exact-title/author QA.').strip()

    doi=r.get('resolved_doi')
    # Europe PMC is a primary bibliographic repository and often carries complete PubMed abstracts.
    if doi:
        eu='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'DOI:'+doi,'resultType':'core','format':'json','pageSize':5})
        try:
            ej=fetchj(eu); (RAW/f'{rid}_europepmc.json').write_text(json.dumps(ej,ensure_ascii=False,indent=2)); attempts.append({'url':eu,'result':'Europe PMC core response saved'})
            for x in ej.get('resultList',{}).get('result',[]):
                if sim(title,x.get('title',''))>=.88 and surname in norm(x.get('authorString','')):
                    a=strip(x.get('abstractText'))
                    if a and len(a.split())>=50 and (not r.get('abstract') or len(a.split())>len(r['abstract'].split())):
                        r['abstract']=a; r['abstract_source_url']=eu; r['notes']=(r.get('notes','')+' Complete abstract selected from Europe PMC core metadata.').strip()
                    break
        except Exception as e: attempts.append({'url':eu,'result':f'error {type(e).__name__}: {e}'})
        su='https://api.semanticscholar.org/graph/v1/paper/'+urllib.parse.quote('DOI:'+doi,safe=':')+'?fields=title,abstract,year,authors,url,openAccessPdf,externalIds'
        try:
            sj=fetchj(su); (RAW/f'{rid}_semanticscholar.json').write_text(json.dumps(sj,ensure_ascii=False,indent=2)); attempts.append({'url':su,'result':'Semantic Scholar record saved'})
            authors=' '.join(a.get('name','') for a in sj.get('authors',[])); a=strip(sj.get('abstract'))
            if sim(title,sj.get('title',''))>=.88 and surname in norm(authors) and a and len(a.split())>=50 and (not r.get('abstract') or len(a.split())>len(r['abstract'].split())):
                r['abstract']=a; r['abstract_source_url']=su; r['notes']=(r.get('notes','')+' Longer verified abstract selected from Semantic Scholar metadata.').strip()
            pdf=(sj.get('openAccessPdf') or {}).get('url')
            if pdf and not r.get('full_text_url'): r['full_text_url']=pdf; r['notes']=(r.get('notes','')+' full_text_url is metadata-advertised; accessibility not independently checked.').strip()
        except Exception as e: attempts.append({'url':su,'result':f'error {type(e).__name__}: {e}'})

    # Reports, grants, datasets, and manuscripts use descriptions, never the abstract field.
    if rec['resource_type'] in {'report_or_book','grant_award','dataset','unpublished_manuscript'}:
        r['source_description']=r.get('abstract')
        r['abstract']=None; r['abstract_source_url']=None; r['abstract_status']='no_abstract_expected'
    else:
        r['source_description']=None
        r['abstract_status']='retrieved' if r.get('abstract') and len(r['abstract'].split())>=50 else ('not_found' if r.get('resolved_title') else 'unresolved_citation')
        if r.get('abstract') and len(r['abstract'].split())<50:
            r['notes']=(r.get('notes','')+' Short metadata teaser removed; no complete abstract found.').strip(); r['abstract']=None; r['abstract_source_url']=None
    r['attempts']=(r.get('attempts') or [])+attempts
    r['retrieved_at']=datetime.now(timezone.utc).isoformat()
    return r

with cf.ThreadPoolExecutor(max_workers=4) as ex:
    futures={ex.submit(resolve_one,rid):rid for rid in sorted(res)}
    done={}
    for f in cf.as_completed(futures):
        rid=futures[f]
        try: done[rid]=f.result(); print(rid,done[rid]['abstract_status'],len((done[rid].get('abstract') or '').split()))
        except Exception as e:
            done[rid]=res[rid]; done[rid]['notes']=(done[rid].get('notes','')+f' Resolver failure: {type(e).__name__}: {e}').strip(); print(rid,'ERROR',e)
        (OUT/'results.stage2.jsonl').write_text('\n'.join(json.dumps(done[k],ensure_ascii=False) for k in sorted(done))+'\n')
(OUT/'results.jsonl').write_text('\n'.join(json.dumps(done[k],ensure_ascii=False) for k in sorted(done))+'\n')
