#!/usr/bin/env python3
import json, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'; UA='COSZO-bibliography-audit/1.0'
dois={'097':'10.1785/0220140207','112':'10.1016/j.tecto.2013.11.024','113':'10.1016/j.jog.2016.03.010'}
for n,doi in dois.items():
 url='https://api.semanticscholar.org/graph/v1/paper/DOI:'+quote(doi,safe='')+'?fields=title,authors,year,abstract,openAccessPdf,url,externalIds,publicationTypes,journal'
 try:
  req=Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
  with urlopen(req,timeout=30) as r:data=r.read().decode('utf-8','replace')
  (RAW/f'COSZO-REF-{n}_semanticscholar.json').write_text(data)
  x=json.loads(data); print(n,len(x.get('abstract') or ''),x.get('title'))
 except Exception as e:
  (RAW/f'COSZO-REF-{n}_semanticscholar.error.txt').write_text(repr(e)); print(n,'ERROR',repr(e))
 time.sleep(2)

elsevier={
 '112':'https://api.elsevier.com/content/article/PII:S0040195113006896?httpAccept=text/xml',
 '113':'https://api.elsevier.com/content/article/PII:S026437071530017X?httpAccept=text/xml',
}
for n,url in elsevier.items():
 try:
  req=Request(url,headers={'User-Agent':UA,'Accept':'text/xml'})
  with urlopen(req,timeout=30) as r:data=r.read().decode('utf-8','replace')
  (RAW/f'COSZO-REF-{n}_elsevier.xml').write_text(data); print(n,'Elsevier',len(data))
 except Exception as e:
  (RAW/f'COSZO-REF-{n}_elsevier.error.txt').write_text(repr(e)); print(n,'Elsevier ERROR',repr(e))
