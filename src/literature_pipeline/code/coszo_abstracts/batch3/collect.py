#!/usr/bin/env python3
import concurrent.futures, html, json, re, time, unicodedata
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

SRC = Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')
OUT = Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch3')
RAW = OUT / 'raw'
OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(exist_ok=True)
UA = 'COSZO-bibliography-audit/1.0'

def get(url, timeout=25):
    req=Request(url, headers={'User-Agent':UA, 'Accept':'application/json'})
    with urlopen(req, timeout=timeout) as r: return r.read().decode('utf-8','replace')

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def title_from_citation(c):
    # The bibliography uses a year followed by the title. Stop at known venue/report markers.
    s=re.split(r'\(\d{4}[a-z]?\)\.?\s*',c,maxsplit=1)
    rest=s[1] if len(s)>1 else c
    markers=['. The ISME Journal', '. Journal of Geophysical Research', '. Frontiers in Earth Science',
      '. Science Advances', '. Scientific data', '. Nature Reviews', '. Nature,', '. Science,',
      '. Geology,', '. Seismological Research Letters', '. Oceanography', '. Annual Review',
      '. Tectonophysics', '. Journal of Geodynamics', '. Geophys. Res. Lett.', '. Earth and Space Science',
      '. Geochemistry, Geophysics, Geosystems', '. Bulletin of the Seismological Society',
      '. Communications on Hydraulic', '. NOAA /', '. IEDA.', ', NSF Award', ', Final Report',
      '. London:', ' Frontiers in Marine Science,', ', submitted.']
    cuts=[rest.find(m) for m in markers if rest.find(m)>0]
    return rest[:min(cuts)].strip().rstrip('.') if cuts else rest.split('. ')[0].strip().rstrip('.')

rows=[]
for line in SRC.open():
    o=json.loads(line); n=int(o['id'].rsplit('-',1)[1])
    if 90<=n<=133: rows.append(o)

def collect(o):
    rid=o['id']; title=title_from_citation(o['citation']); attempts=[]
    urls={
      'crossref': 'https://api.crossref.org/works?query.bibliographic='+quote(o['citation'])+'&rows=5&select=DOI,title,author,published,issued,URL,abstract,type,license,link,publisher',
      'openalex': 'https://api.openalex.org/works?search='+quote(title)+'&per-page=5',
    }
    for name,url in urls.items():
        try:
            data=get(url); (RAW/f'{rid}_{name}.json').write_text(data)
            attempts.append({'url':url,'result':'retrieved'})
        except Exception as e:
            (RAW/f'{rid}_{name}.error.txt').write_text(repr(e)); attempts.append({'url':url,'result':'error: '+repr(e)})
    return rid,title,attempts

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    gathered=list(ex.map(collect,rows))
(OUT/'initial_attempts.json').write_text(json.dumps(gathered,ensure_ascii=False,indent=2))
print('collected',len(gathered))
