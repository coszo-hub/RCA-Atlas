#!/usr/bin/env python3
import html, json, re
from pathlib import Path

OUT=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1'); RAW=OUT/'raw'
rows=[json.loads(l) for l in (OUT/'results.jsonl').read_text().splitlines()]
by={r['id']:r for r in rows}
def clean(s): return ' '.join(html.unescape(re.sub(r'<[^>]+>',' ',s or '')).split())
def note(r,s): r['notes']=((r.get('notes') or '')+' '+s).strip()

# Replace provisional PP 1707 summary with the authoritative official API text.
x=json.loads((RAW/'COSZO-REF-006_usgs.json').read_text())['records'][0]
r=by['COSZO-REF-006']; r['source_description']=clean(re.sub(r'^\s*<h1>Summary</h1>','',x['docAbstract']))
r['source_description_source_url']='https://pubs.usgs.gov/pubs-services/publication/?page_size=1&q=pp1707'
r.setdefault('attempts',[]).append({'url':r['source_description_source_url'],'result':'official USGS API returned text explicitly headed Summary; raw JSON saved'})

# API-specific source endpoints for the remaining automatically supplied abstracts.
by['COSZO-REF-020']['abstract_source_url']='https://api.openalex.org/works/W2135346331'
by['COSZO-REF-032']['abstract_source_url']='https://api.crossref.org/works/10.1029%2F2019jb018053'

# Nature PDF-looking links redirected to HTML landing pages and are not retained as verified full text.
for rid in ('COSZO-REF-015','COSZO-REF-034'):
    r=by[rid]; r['full_text_url']=None; note(r,'Nature PDF URL redirected to an HTML landing page, so it was not retained as verified full text.')

r=by['COSZO-REF-025']; r['resolved_title']='The State of Locking near the Deformation Front of the Central Cascadia Subduction Zone from GNSS-Acoustic'; r['abstract_status']='unresolved_citation'
note(r,'Manuscript was cited as in preparation; no public record established whether it appeared under this exact title. The related 2025 paper was not treated as the same work.')

# Remove structural JATS heading accidentally prepended by some Crossref records.
for r in rows:
    if (r.get('abstract') or '').startswith('Abstract '): r['abstract']=r['abstract'][9:]
    if r.get('source_description') and not r.get('source_description_source_url'):
        r['source_description_source_url']=r.get('metadata_source_url') or r.get('paper_url')

# Explicit reasoned outcomes for the four unavailable abstracts.
reasons={
'COSZO-REF-003':'Exact 2020 AGU record identified at ADS; Crossref and OpenAlex searches returned no full abstract, and ADS blocked automated abstract access.',
'COSZO-REF-012':'Exact 2020 AGU V040-0017 record identified; Crossref/OpenAlex had no matching abstract and ADS returned HTTP 405/429 to automated retrieval.',
'COSZO-REF-024':'Exact 2022 AGU T56A-05 record identified; the meeting landing record did not yield abstract text. A 2025 journal version exists but was not substituted.',
'COSZO-REF-029':'Exact Elsevier chapter DOI verified using the official Elsevier API; its record contains no abstract, and Crossref, OpenAlex, Europe PMC, and Semantic Scholar yielded none.'}
for rid,reason in reasons.items():
    r=by[rid]; r['abstract_status']='not_found'; note(r,reason)

# Validate required shape and one row per assigned id.
required=['id','resolved_title','resolved_doi','paper_url','abstract','abstract_status','abstract_source_url','retrieved_at','metadata_source_url','license','full_text_url','notes','attempts']
assert len(rows)==44 and len({r['id'] for r in rows})==44
assert [r['id'] for r in rows]==[f'COSZO-REF-{i:03d}' for i in range(1,45)]
for r in rows:
    for k in required: assert k in r,(r['id'],k)
    assert r['abstract_status'] in {'retrieved','not_found','no_abstract_expected','blocked','unresolved_citation'}
    if r['abstract_status']=='retrieved': assert r['abstract'] and r['abstract_source_url'] and r['retrieved_at']
    assert isinstance(r['attempts'],list) and r['attempts']
(OUT/'results.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
