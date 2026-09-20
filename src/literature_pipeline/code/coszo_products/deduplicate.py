import json,re,unicodedata,hashlib
from pathlib import Path
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parent
LIB=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature')
def read(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
def norm(t):
 t=unicodedata.normalize('NFKD',t or '').encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]','',t)
def doi_norm(t):return re.sub(r'^https?://(?:dx\.)?doi.org/','',t.strip(),flags=re.I).rstrip('.,;').lower()
existing=read(LIB/'coszo_literature.jsonl')
lookup={x['id']:x for x in existing}
doimap={}
citationmap={norm(x['citation']):x['id'] for x in existing}
for x in existing:
 for d in (x.get('dois_as_cited') or [])+([x['resolved_doi']] if x.get('resolved_doi') else []):doimap[doi_norm(d)]=x['id']
occ=[]
for name in ['extraction_a.jsonl','extraction_b.jsonl','extraction_extra.jsonl']:
 p=ROOT/name
 if p.exists():occ+=read(p)
occ.sort(key=lambda r:(min(r['pdf_pages_1_based']),r.get('extraction_order',0)))
manual=json.loads((ROOT/'manual_matches.json').read_text()) if (ROOT/'manual_matches.json').exists() else {}
review=[];new=[];nextid=134
for i,o in enumerate(occ,1):
 oid=f'COSZO-ADD-{i:03d}'
 o['occurrence_id']=oid
 c=o['citation'];cn=norm(c)
 ds=o.get('doi_as_cited') or o.get('dois_as_cited') or []
 if isinstance(ds,str):ds=[ds]
 matches={doimap[doi_norm(d)] for d in ds if doi_norm(d) in doimap}
 method='doi'
 if not matches and cn in citationmap:
  matches={citationmap[cn]};method='exact_citation'
 if not matches:
  method='title'
  for key,x in lookup.items():
   tn=norm(x.get('resolved_title') or x.get('title'))
   if len(tn)>=35 and tn in cn:matches.add(key)
 if oid in manual:
  target=manual[oid]
  if target and target.startswith('occ:'):target=next(x['canonical_id'] for x in occ[:i-1] if x['occurrence_id']==target[4:])
  matches={target} if target else set();method='manual_review'
 if len(matches)==1:
  cid=next(iter(matches))
 else:
  cid=f'COSZO-REF-{nextid:03d}';nextid+=1
  # A new source-order ID is assigned; fuzzy candidates are reviewed before retrieval.
  scored=sorted([(SequenceMatcher(None,cn,norm(x['citation'])).ratio(),key) for key,x in lookup.items()],reverse=True)[:3]
  review.append({'occurrence_id':oid,'proposed_id':cid,'citation':c,'candidates':[(round(score,3),key,lookup[key]['citation']) for score,key in scored],'conflicting_exact_matches':list(matches)})
  year=re.search(r'\b(?:19|20)\d{2}[a-z]?\b',c)
  pgs=o['pdf_pages_1_based']
  rec={'id':cid,'canonical_id':cid,'duplicate_of':None,'citation_as_extracted':c,'citation':c,'year_as_cited':year.group(0) if year else None,'resource_type':o.get('resource_type','unclassified'),'resource_type_status':'pending_metadata_resolution','dois_as_cited':ds,'source_links':[{'url':'https://doi.org/'+doi_norm(d),'provenance':'source_product_citation','verification_status':'not_checked'} for d in ds],'verified_metadata':[],'abstract':None,'abstract_status':'not_yet_retrieved','full_text_url':None,'full_text_status':'not_yet_checked','review_notes':o.get('notes',[]),'provenance':{'source_document':'COSZO Project DataMSRI.pdf','source_relative_path':'../Project info/COSZO Project DataMSRI.pdf','source_sha256':existing[0]['provenance']['source_sha256'],'section':o['section'],'pdf_pages_1_based':pgs,'printed_packet_pages':o.get('printed_packet_pages',[]),'extracted_date':'2026-09-18'},'source_occurrence_ids':[oid]}
  new.append(rec);lookup[cid]=rec;citationmap[cn]=cid
  for d in ds:doimap[doi_norm(d)]=cid
  method='new_work'
 o['canonical_id']=cid;o['match_method']=method
(ROOT/'additional_occurrences.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in occ))
(ROOT/'new_citations.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in new))
(ROOT/'dedup_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
print('Additional occurrences',len(occ),'new works',len(new),'matched occurrences',len(occ)-len(new))
for r in review:print(r['occurrence_id'],r['proposed_id'],r['citation'][:110],[(x[0],x[1]) for x in r['candidates']])
