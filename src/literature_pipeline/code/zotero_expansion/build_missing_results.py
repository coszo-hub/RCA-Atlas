"""Build reviewed fallback results from exact-DOI API responses."""
import html,json,re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
choices={
 '6HLEIGXZ':'crossref','7AWSQDK3':'semanticscholar','7HLK4VFF':'crossref',
 '9AZHN5UT':'crossref','RSANY2VW':'europepmc','WLS5VYTM':'europepmc','Y7BN8X2L':'crossref'}
attempts=json.loads((ROOT/'missing_attempts.json').read_text())
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
rows=[]
for key,source in choices.items():
 x=json.loads((ROOT/'missing_raw'/f'{key}_{source}.json').read_text())
 if source=='crossref':
  m=x['message'];abstract=m.get('abstract');title=(m.get('title')or[''])[0];doi=m.get('DOI');url=f'https://api.crossref.org/works/{doi}'
 elif source=='europepmc':
  m=x['resultList']['result'][0];abstract=m.get('abstractText');title=m.get('title');doi=m.get('doi');url=next(a['url'] for a in attempts if a['zotero_key']==key and a['source']==source)
 else:
  abstract=x.get('abstract');title=x.get('title');doi=(x.get('externalIds')or{}).get('DOI');url=next(a['url'] for a in attempts if a['zotero_key']==key and a['source']==source)
 abstract=clean(abstract)
 assert len(abstract.split())>=80 and title and doi
 rows.append({'zotero_key':key,'abstract':abstract,'abstract_status':'retrieved','abstract_source_url':url,
  'retrieved_at':datetime.now(timezone.utc).isoformat(),'notes':f'Formal abstract recovered from {source} using the exact DOI and title.',
  'attempts':[a for a in attempts if a['zotero_key']==key]})
(ROOT/'missing_results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
print({'results':len(rows)})
