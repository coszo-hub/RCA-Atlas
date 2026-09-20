#!/usr/bin/env python3
import json, re
from pathlib import Path
from difflib import SequenceMatcher

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'
rows=[json.loads(x) for x in (OUT/'results.jsonl').read_text().splitlines()]
required=['id','resolved_title','resolved_doi','paper_url','abstract','abstract_status','abstract_source_url','retrieved_at','metadata_source_url','license','full_text_url','notes','attempts']
errors=[]; warnings=[]; matches=[]
if len(rows)!=44:errors.append(f'expected 44 rows, found {len(rows)}')
expected=[f'COSZO-REF-{i:03d}' for i in range(90,134)]
if [x['id'] for x in rows]!=expected:errors.append('IDs are not exactly 090-133 in order')
for x in rows:
 miss=[k for k in required if k not in x]
 if miss:errors.append(f"{x['id']} missing keys {miss}")
 if x['abstract_status']=='retrieved' and not x['abstract']:errors.append(f"{x['id']} retrieved without text")
 if x['abstract_status']!='retrieved' and x['abstract'] is not None:errors.append(f"{x['id']} non-retrieved status has abstract text")
 if x['abstract'] and len(x['abstract'])<250:warnings.append(f"{x['id']} short abstract: {len(x['abstract'])}")
 n=int(x['id'].rsplit('-',1)[1])
 if x['resolved_doi'] and (RAW/f"{x['id']}_openalex.json").exists():
  oa=json.loads((RAW/f"{x['id']}_openalex.json").read_text()).get('results',[])
  cands=[z for z in oa if (z.get('doi') or '').lower().endswith(x['resolved_doi'].lower())]
  if cands:
   z=cands[0]; authors=[a['author']['display_name'] for a in z.get('authorships',[])]
   matches.append({'id':x['id'],'doi':x['resolved_doi'],'metadata_title':z.get('title'),'year':z.get('publication_year'),'authors':authors})
  elif n not in (121,122):warnings.append(f"{x['id']} DOI not present in retrieved OpenAlex candidates")
report={'rows':len(rows),'retrieved_abstracts':sum(x['abstract_status']=='retrieved' for x in rows),'status_counts':{},'verified_doi_metadata':matches,'errors':errors,'warnings':warnings}
for x in rows:report['status_counts'][x['abstract_status']]=report['status_counts'].get(x['abstract_status'],0)+1
(OUT/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='verified_doi_metadata'},indent=2))
raise SystemExit(bool(errors))
