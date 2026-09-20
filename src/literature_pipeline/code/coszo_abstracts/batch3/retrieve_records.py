#!/usr/bin/env python3
import concurrent.futures, json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'; UA='COSZO-bibliography-audit/1.0'

targets=[]
for rid in ('329853','329854'):
 targets.append((f'ieda_{rid}','https://api.datacite.org/dois/'+quote('10.26022/IEDA/'+rid,safe='')))
for aid in ('1924024','1951448','1950666','2141963','2140989','2142095','2218876'):
 targets.append((f'nsf_{aid}',f'https://api.nsf.gov/services/v1/awards.json?id={aid}'))

def fetch(item):
 name,url=item
 try:
  with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json'}),timeout=30) as r:
   data=r.read().decode('utf-8','replace'); meta={'url':url,'status':r.status,'final_url':r.geturl(),'content_type':r.headers.get('content-type')}
  (RAW/f'{name}.json').write_text(data); (RAW/f'{name}.meta.json').write_text(json.dumps(meta,indent=2)); return name,'ok',len(data)
 except Exception as e:
  (RAW/f'{name}.error.txt').write_text(repr(e)); return name,'error',repr(e)

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
 for result in ex.map(fetch,targets): print(*result)
