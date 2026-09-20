"""Fetch public metadata candidates for Zotero records whose abstractNote is empty."""
import json, time, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'missing_raw';RAW.mkdir(exist_ok=True)
records=[json.loads(s) for s in (ROOT/'package/ooi_zotero_literature.jsonl').read_text().splitlines() if s.strip()]
records=[r for r in records if not r.get('abstract') and r.get('resolved_doi')]
headers={'User-Agent':'COSZO-literature-collector/1.0 (research metadata retrieval)'}
attempts=[]
for r in records:
    doi=r['resolved_doi'];key=r['zotero_item_key']
    urls={
      'crossref':'https://api.crossref.org/works/'+urllib.parse.quote(doi,safe=''),
      'openalex':'https://api.openalex.org/works/https://doi.org/'+urllib.parse.quote(doi,safe=''),
      'europepmc':'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':'DOI:'+doi,'resultType':'core','format':'json','pageSize':5}),
      'semanticscholar':'https://api.semanticscholar.org/graph/v1/paper/DOI:'+urllib.parse.quote(doi,safe='')+'?fields=title,abstract,year,authors,url,openAccessPdf,externalIds',
    }
    for source,url in urls.items():
        try:
            req=urllib.request.Request(url,headers=headers)
            with urllib.request.urlopen(req,timeout=30) as resp:data=resp.read()
            (RAW/f'{key}_{source}.json').write_bytes(data)
            attempts.append({'zotero_key':key,'source':source,'url':url,'result':f'HTTP 200; {len(data)} bytes'})
        except Exception as e:
            attempts.append({'zotero_key':key,'source':source,'url':url,'result':f'{type(e).__name__}: {e}'})
        time.sleep(.35)
(ROOT/'missing_attempts.json').write_text(json.dumps(attempts,indent=2)+'\n')
print(json.dumps({'records':len(records),'responses':len(list(RAW.glob('*.json'))),'attempts':len(attempts)}))
