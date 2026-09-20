#!/usr/bin/env python3
import concurrent.futures, json, re, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'; UA='COSZO-bibliography-audit/1.0'
exec(open('analyze.py').read().split('rows=[]')[0])
links={
 'COSZO-REF-095':'https://earthquake.usgs.gov/cfusion/external_grants/reports/G17AP00046.pdf',
 'COSZO-REF-113':'https://geophysics.uoregon.edu/pdf/wang_trehu_2016.pdf',
 'COSZO-REF-120':'https://usoceandiscovery.org/wp-content/uploads/2016/06/Cascadia-Report.pdf',
}
for line in SRC.open():
 o=json.loads(line); n=int(o['id'].rsplit('-',1)[1])
 if not 90<=n<=133: continue
 target=title_from_citation(o['citation'])
 try: xs=json.loads((RAW/f"{o['id']}_openalex.json").read_text())['results']
 except Exception: continue
 xs.sort(key=lambda x:score(target,x.get('title','')),reverse=True)
 if xs and score(target,xs[0].get('title',''))>.85:
  pdf=(xs[0].get('best_oa_location') or {}).get('pdf_url') or (xs[0].get('primary_location') or {}).get('pdf_url')
  if pdf: links.setdefault(o['id'],pdf)

def check(item):
 rid,url=item
 try:
  req=Request(url,headers={'User-Agent':UA,'Range':'bytes=0-63'})
  with urlopen(req,timeout=30) as r:
   head=r.read(64); return rid,{'url':url,'verified':r.status in (200,206),'status':r.status,'final_url':r.geturl(),'content_type':r.headers.get('content-type'),'magic':head[:8].hex()}
 except Exception as e:return rid,{'url':url,'verified':False,'result':repr(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex: results=dict(ex.map(check,links.items()))
(RAW/'fulltext_link_checks.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
for k,v in results.items(): print(k,v)
