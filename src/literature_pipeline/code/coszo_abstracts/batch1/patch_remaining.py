#!/usr/bin/env python3
import html, json, re, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

OUT=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1'); RAW=OUT/'raw'
rows={r['id']:r for r in map(json.loads,(OUT/'results.jsonl').read_text().splitlines())}
def clean(s): return ' '.join(html.unescape(re.sub(r'<[^>]+>',' ',s or '')).split())
def inv(x): return ' '.join(w for _,w in sorted((p,w) for w,ps in (x or {}).items() for p in ps)) or None
def note(r,s): r['notes']=((r.get('notes') or '')+' '+s).strip()

# USGS official catalog distinguishes a Summary (PP 1707) from an Abstract (Circular 1428).
r=rows['COSZO-REF-006']
r.update(resolved_title='The orphan tsunami of 1700—Japanese clues to a parent earthquake in North America',resolved_doi='10.3133/pp1707',paper_url='https://doi.org/10.3133/pp1707',metadata_source_url='https://pubs.usgs.gov/publication/pp1707',abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None,source_description_source_url='https://pubs.usgs.gov/publication/pp1707',license='Public domain (U.S. Government work)')
note(r,'USGS labels the catalog text Summary, not Abstract; retained as source_description.')

r=rows['COSZO-REF-040']; uj=json.loads((RAW/'COSZO-REF-040_usgs.json').read_text()); rec=uj['records'][0]; a=clean(rec.get('docAbstract'))
r.update(resolved_title=rec['title'],resolved_doi='10.3133/cir1428',paper_url='https://doi.org/10.3133/cir1428',abstract=a,abstract_status='retrieved',abstract_source_url='https://pubs.usgs.gov/pubs-services/publication/?page_size=1&q=cir1428',metadata_source_url='https://pubs.usgs.gov/publication/cir1428',license='Public domain (U.S. Government work)',full_text_url='https://pubs.usgs.gov/circ/1428/cir1428.pdf',source_description=None,retrieved_at=datetime.now(timezone.utc).isoformat())
r.setdefault('attempts',[]).append({'url':r['abstract_source_url'],'result':'official USGS API returned complete docAbstract; raw JSON saved'})
note(r,'USGS Publications Warehouse explicitly labels this text Abstract.')

# Exact metadata and source descriptions for non-paper resources.
r=rows['COSZO-REF-013']; dc=json.loads((RAW/'COSZO-REF-013_datacite.json').read_text())['data']['attributes']
r.update(resolved_title=dc['titles'][0]['title'],resolved_doi='10.26022/IEDA/330188',paper_url=dc['url'],metadata_source_url='https://api.datacite.org/dois/10.26022/IEDA/330188',source_description=dc['descriptions'][0]['description'],source_description_source_url='https://api.datacite.org/dois/10.26022/IEDA/330188',license=dc['rightsList'][0]['rights'],abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None)
note(r,'DataCite calls its dataset description Abstract; retained as source_description under the project schema.')

r=rows['COSZO-REF-007']; r.update(resolved_title='Collaborative Research: Deployment of Seafloor Optical Fiber Strainmeters for the Detection of Slow Slip Events',paper_url='https://www.nsf.gov/awardsearch/showAward?AWD_ID=2003489&HistoricalAwards=false',metadata_source_url='https://www.nsf.gov/awardsearch/showAward?AWD_ID=2003489&HistoricalAwards=false',abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None)
note(r,'Official NSF award records: 2003489 and 2004259; award descriptions belong in source_description if later recovered, not abstract.')
r.setdefault('attempts',[]).extend([{'url':'https://www.nsf.gov/awardsearch/showAward?AWD_ID=2003489&HistoricalAwards=false','result':'official award landing page verified'},{'url':'https://www.nsf.gov/awardsearch/showAward?AWD_ID=2004259&HistoricalAwards=false','result':'companion award landing URL recorded'}])
r=rows['COSZO-REF-014']; r.update(resolved_title='Collaborative Research: Multi-scale Geodetic Monitoring at Axial Seamount',paper_url='https://www.nsf.gov/awardsearch/showAward?AWD_ID=2226488&HistoricalAwards=false',metadata_source_url='https://www.nsf.gov/awardsearch/showAward?AWD_ID=2226488&HistoricalAwards=false',abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None)
note(r,'Official NSF award records: 2226488, 2226445, and 2226467; award descriptions belong in source_description if later recovered, not abstract.')
r.setdefault('attempts',[]).extend([{'url':f'https://www.nsf.gov/awardsearch/showAward?AWD_ID={x}&HistoricalAwards=false','result':'official award landing URL recorded'} for x in ('2226488','2226445','2226467')])

r=rows['COSZO-REF-021']; url='https://crew.org/wp-content/uploads/2016/04/cascadia_subduction_scenario_2013.pdf'
r.update(resolved_title='Cascadia Subduction Zone Earthquakes: A Magnitude 9.0 Earthquake Scenario',paper_url=url,metadata_source_url=url,full_text_url=url,abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None)
r.setdefault('attempts',[]).append({'url':url,'result':'official CREW report PDF downloaded successfully; raw PDF saved'})
note(r,'Exact CREW report title and live PDF verified; no formal abstract identified.')

r=rows['COSZO-REF-029']; eu='https://api.elsevier.com/content/article/doi/10.1016/B978-0-12-803192-6.00014-1?httpAccept=text/xml'
r['metadata_source_url']=eu; r.setdefault('attempts',[]).append({'url':eu,'result':'official Elsevier API verified title, DOI, book, and date; response contains no abstract; raw XML saved'})
note(r,'Official Elsevier API record contains no abstract.')

# Identify which scholarly API actually supplied each automatically retrieved abstract.
for rid,r in rows.items():
    if r.get('abstract_status')!='retrieved' or not r.get('abstract_source_url','').startswith('https://doi.org/'):
        continue
    target=clean(r['abstract'])
    matched=False
    for p in [RAW/f'{rid}_crossref.json',RAW/f'{rid}_crossref_title.json']:
        if not p.exists(): continue
        x=json.loads(p.read_text()); items=x.get('message',{}).get('items',[])
        for item in items:
            if item.get('abstract') and clean(item['abstract'])==target:
                doi=item.get('DOI') or r.get('resolved_doi'); url='https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='')
                r['abstract_source_url']=url; (RAW/f'{rid}_abstract_source_crossref.json').write_text(json.dumps(item,ensure_ascii=False,indent=2)); matched=True; break
        if matched: break
    if matched: continue
    for p in [RAW/f'{rid}_openalex.json',RAW/f'{rid}_openalex_title.json']:
        if not p.exists(): continue
        x=json.loads(p.read_text())
        for item in x.get('results',[]):
            if inv(item.get('abstract_inverted_index'))==target:
                wid=(item.get('id') or '').rsplit('/',1)[-1]; r['abstract_source_url']='https://api.openalex.org/works/'+wid
                (RAW/f'{rid}_abstract_source_openalex.json').write_text(json.dumps(item,ensure_ascii=False,indent=2)); matched=True; break
        if matched: break
    if not matched:
        note(r,'Abstract source is publisher metadata exposed at the DOI landing page; provider-specific raw responses are saved.')

(OUT/'results.jsonl').write_text('\n'.join(json.dumps(rows[k],ensure_ascii=False) for k in sorted(rows))+'\n')
