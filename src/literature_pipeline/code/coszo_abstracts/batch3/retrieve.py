#!/usr/bin/env python3
import json, re
from pathlib import Path
from urllib.request import Request, urlopen

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'; RAW.mkdir(exist_ok=True)
UA='COSZO-bibliography-audit/1.0'
dois={
 '096':'10.1130/g32460.1','097':'10.1785/0220140207','098':'10.1130/g24145a.1',
 '099':'10.5670/oceanog.2018.116','103':'10.5670/oceanog.2018.118',
 '104':'10.3389/fmars.2019.00074','109':'10.1126/science.aaf2349',
 '112':'10.1016/j.tecto.2013.11.024','113':'10.1016/j.jog.2016.03.010',
 '119':'10.1126/science.aah5563','124':'10.1785/0120100198',
 '125':'10.1038/s43017-021-00245-w','131':'10.1038/nature17632',
}
for n,doi in dois.items():
 urls=[f'https://doi.org/{doi}']
 for k,url in enumerate(urls):
  try:
   req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
   with urlopen(req,timeout=30) as r:
    data=r.read().decode('utf-8','replace'); final=r.geturl(); status=r.status; ctype=r.headers.get('content-type')
   (RAW/f'COSZO-REF-{n}_publisher.html').write_text(data)
   (RAW/f'COSZO-REF-{n}_publisher.meta.json').write_text(json.dumps({'requested_url':url,'final_url':final,'status':status,'content_type':ctype},indent=2))
   print(n,status,final,len(data))
  except Exception as e:
   (RAW/f'COSZO-REF-{n}_publisher.error.txt').write_text(repr(e)); print(n,'ERROR',repr(e))
