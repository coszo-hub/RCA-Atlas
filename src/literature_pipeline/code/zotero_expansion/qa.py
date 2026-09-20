"""Integrity and known-error regression checks for the unified literature package."""
import hashlib,json,re
from collections import Counter,defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent/'package'
def read(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
r=read(P/'literature.jsonl');o=read(P/'literature_occurrences.jsonl');z=read(P/'ooi_zotero_literature.jsonl')
assert len(r)==336 and len(z)==153 and len(o)==398
assert len({x['id'] for x in r})==336 and len({x['occurrence_id'] for x in o})==398
ids={x['id'] for x in r};assert all(x['canonical_id'] in ids for x in o)
assert len(list((P/'records').glob('*.md')))==336
assert len(list((P/'abstracts').glob('*.md')))==291
assert all(x.get('abstract') and x['abstract_status']=='retrieved' for x in z)
assert all(x.get('abstract_source_url') for x in r if x.get('abstract'))
assert all(not re.search(r'<\/?(?:jats|p|abstract)\b|access denied|enable javascript|captcha',x.get('abstract') or '',re.I) for x in r)
assert all('&⋕' not in (x.get('resolved_title') or '') for x in r)
dois=defaultdict(list)
for x in r:
    if x.get('resolved_doi'):dois[x['resolved_doi'].lower()].append(x['id'])
assert not {d:v for d,v in dois.items() if len(v)>1}
bykey={x.get('zotero_item_key'):x for x in z}
assert 'hydrothermal discharge' not in bykey['5Y85SKAW']['abstract'].lower()
assert 'autoencoder' in bykey['5Y85SKAW']['abstract'].lower()
assert 'tsunami' in bykey['XYD5BSMF']['abstract'].lower()
assert 'atlantic meridional' not in bykey['XYD5BSMF']['abstract'].lower()
assert 'download pdf' not in bykey['92BSGBND']['abstract'].lower()
assert bykey['6YM2JGUS']['resolved_title']=='Stress Drops on the Blanco Oceanic Transform Fault from Interstation Phase Coherence'
assert bykey['TR4V5WW5']['resolved_title']=="Earthquake location and detection modeling for a future seafloor observatory along Mayotte's volcanic ridge"
assert any(x['id']=='COSZO-REF-103' and x['abstract_status']=='retrieved' for x in r)
assert any(x.get('zotero_key')=='PU7BMBHB' and x['canonical_id']=='COSZO-REF-019' for x in o)
assert Counter(x['abstract_status'] for x in r)=={'retrieved':291,'no_abstract_expected':38,'not_found':6,'unresolved_citation':1}
checks=json.loads((P/'literature_collection_checksums.json').read_text())
for rel,h in checks.items():assert hashlib.sha256((P/rel).read_bytes()).hexdigest()==h,rel
print(json.dumps({'records':len(r),'occurrences':len(o),'abstracts':sum(bool(x.get('abstract')) for x in r),'status_counts':dict(Counter(x['abstract_status'] for x in r))}))
