import json,urllib.request,urllib.parse,concurrent.futures
from pathlib import Path
P=Path(__file__).parent
rows=[r for r in map(json.loads,(P.parent/'new_citations.jsonl').read_text().splitlines()) if 156<=int(r['id'][-3:])<=167]
def work(r):
 u='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':r['citation'],'rows':4})
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'COSZO-literature-collection/1.0'}),timeout=35) as f:s=f.read()
  (P/'raw'/f"{r['id']}_crossref.json").write_bytes(s)
  return {'id':r['id'],'url':u,'result':'retrieved'}
 except Exception as e:return {'id':r['id'],'url':u,'result':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:out=list(ex.map(work,rows))
(P/'attempts.json').write_text(json.dumps(out,indent=2));print(out)
