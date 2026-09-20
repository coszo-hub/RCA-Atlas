#!/usr/bin/env python3
import json, re, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'
SRC=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')

def norm(s):
 s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+',' ',s).strip()

def score(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()

def title_from_citation(c):
 s=re.split(r'\(\d{4}[a-z]?\)\.?\s*',c,maxsplit=1); rest=s[1] if len(s)>1 else c
 markers=['. The ISME Journal', '. Journal of Geophysical Research', '. Frontiers in Earth Science', '. Science Advances', '. Scientific data', '. Nature Reviews', '. Nature,', '. Science,', '. Geology,', '. Seismological Research Letters', '. Oceanography', '. Annual Review', '. Tectonophysics', '. Journal of Geodynamics', '. Geophys. Res. Lett.', '. Earth and Space Science', '. Geochemistry, Geophysics, Geosystems', '. Bulletin of the Seismological Society', '. Communications on Hydraulic', '. NOAA /', '. IEDA.', ', NSF Award', ', Final Report', '. London:', ' Frontiers in Marine Science,', ', submitted.']
 cuts=[rest.find(m) for m in markers if rest.find(m)>0]
 return rest[:min(cuts)].strip().rstrip('.') if cuts else rest.split('. ')[0].strip().rstrip('.')

rows=[]
for line in SRC.open():
 o=json.loads(line); n=int(o['id'].rsplit('-',1)[1])
 if not 90<=n<=133: continue
 rid=o['id']; target=title_from_citation(o['citation']); cand=[]
 try:
  cr=json.loads((RAW/f'{rid}_crossref.json').read_text())['message']['items']
  for x in cr:
   t=(x.get('title') or [''])[0]; cand.append(('CR',score(target,t),t,x.get('DOI'),bool(x.get('abstract'))))
 except Exception: pass
 try:
  oa=json.loads((RAW/f'{rid}_openalex.json').read_text())['results']
  for x in oa:
   t=x.get('title',''); cand.append(('OA',score(target,t),t,x.get('doi'),bool(x.get('abstract_inverted_index'))))
 except Exception: pass
 cand.sort(key=lambda x:x[1],reverse=True)
 rows.append({'id':rid,'target':target,'type':o['resource_type'],'best':cand[:3]})
print('\n'.join(json.dumps(x,ensure_ascii=False) for x in rows))
