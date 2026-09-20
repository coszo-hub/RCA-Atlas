#!/usr/bin/env python3
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

SRC = Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')
OUT = Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1')
RAW = OUT / 'raw'
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(exist_ok=True)

UA = 'COSZO-abstract-retrieval/1.0 (mailto:research@example.org)'

def fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))

def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())

def extract_title(citation):
    # title lies between the parenthesized year and source; sentence abbreviations are uncommon here.
    m = re.search(r'\(\d{4}\)[,.]?\s*[“\"]?(.+?)[”\"]?\.\s+(?:In\s+|[A-Z][A-Za-z&:, ]+[,\d])', citation)
    if m: return m.group(1).strip(' “”.')
    m = re.search(r'\b(?:19|20)\d{2}\)?[,.]?\s+(.+?)\.\s+(?:[A-Z]|In\s)', citation)
    return m.group(1).strip(' “”.') if m else citation

def year_of(item):
    for k in ('published-print','published-online','published','issued','created'):
        try: return item[k]['date-parts'][0][0]
        except Exception: pass
    return None

def strip_jats(s):
    if not s: return None
    s = re.sub(r'<[^>]+>', ' ', s)
    return ' '.join(html.unescape(s).split())

def inv_to_text(inv):
    if not inv: return None
    words=[]
    for word, poss in inv.items():
        for p in poss: words.append((p, word))
    return ' '.join(w for _,w in sorted(words))

records=[]
for line in SRC.read_text().splitlines():
    o=json.loads(line)
    n=int(o['id'].split('-')[-1])
    if 1 <= n <= 44: records.append(o)

results=[]
for i, rec in enumerate(records, 1):
    rid=rec['id']; citation=rec['citation']
    try: cited_year=int(rec['year_as_cited'])
    except Exception:
        ym=re.search(r'\b((?:19|20)\d{2})\b', citation)
        cited_year=int(ym.group(1)) if ym else None
    guessed=extract_title(citation)
    attempts=[]; cr_items=[]; oa_items=[]
    qurl='https://api.crossref.org/works?' + urllib.parse.urlencode({'query.bibliographic': citation, 'rows': 5, 'select':'DOI,title,author,published,published-print,published-online,issued,created,URL,abstract,link,license,type,publisher'})
    try:
        cr=fetch_json(qurl); (RAW/f'{rid}_crossref.json').write_text(json.dumps(cr,ensure_ascii=False,indent=2))
        cr_items=cr.get('message',{}).get('items',[])
        attempts.append({'url':qurl,'result':f'{len(cr_items)} Crossref candidates'})
    except Exception as e: attempts.append({'url':qurl,'result':f'error: {type(e).__name__}: {e}'})
    ourl='https://api.openalex.org/works?' + urllib.parse.urlencode({'search':guessed,'per-page':10,'mailto':'research@example.org'})
    try:
        oa=fetch_json(ourl); (RAW/f'{rid}_openalex.json').write_text(json.dumps(oa,ensure_ascii=False,indent=2))
        oa_items=oa.get('results',[])
        attempts.append({'url':ourl,'result':f'{len(oa_items)} OpenAlex candidates'})
    except Exception as e: attempts.append({'url':ourl,'result':f'error: {type(e).__name__}: {e}'})

    # Score candidates by title similarity, year, and first-author surname in citation.
    first_surname=norm(citation.split(',')[0])
    cands=[]
    for x in cr_items:
        title=(x.get('title') or [''])[0]
        yr=year_of(x)
        au=' '.join(a.get('family','') for a in x.get('author',[]))
        sim=SequenceMatcher(None,norm(guessed),norm(title)).ratio()
        score=sim + (0.08 if yr and cited_year and abs(yr-cited_year)<=1 else 0) + (0.08 if first_surname and first_surname in norm(au) else 0)
        cands.append((score,'crossref',x,title,yr,sim))
    for x in oa_items:
        title=x.get('display_name') or x.get('title') or ''
        yr=x.get('publication_year')
        au=' '.join(a.get('author',{}).get('display_name','') for a in x.get('authorships',[]))
        sim=SequenceMatcher(None,norm(guessed),norm(title)).ratio()
        score=sim + (0.08 if yr and cited_year and abs(yr-cited_year)<=1 else 0) + (0.08 if first_surname and first_surname in norm(au) else 0)
        cands.append((score,'openalex',x,title,yr,sim))
    cands.sort(key=lambda z:z[0],reverse=True)
    best=cands[0] if cands else None
    verified=bool(best and best[5] >= .80 and (not cited_year or (best[4] and abs(best[4]-cited_year)<=1)))
    title=best[3] if verified else guessed
    doi=None; abstract=None; source=None; meta=None; license_=None; full=None; paper=None; notes=[]
    if verified:
        typ=best[1]; x=best[2]
        if typ=='crossref':
            doi=x.get('DOI'); abstract=strip_jats(x.get('abstract')); meta=qurl
            paper='https://doi.org/'+doi if doi else x.get('URL')
            source=paper if abstract else None
            ls=x.get('license') or []; license_=ls[0].get('URL') if ls else None
            for lk in x.get('link') or []:
                if lk.get('content-type')=='application/pdf': full=lk.get('URL'); break
        else:
            doi=(x.get('doi') or '').replace('https://doi.org/','') or None
            abstract=inv_to_text(x.get('abstract_inverted_index')); meta=x.get('id')
            paper='https://doi.org/'+doi if doi else (x.get('primary_location') or {}).get('landing_page_url') or x.get('id')
            source=x.get('id') if abstract else None
            loc=x.get('best_oa_location') or {}
            full=loc.get('pdf_url')
            license_=loc.get('license')
        # Prefer an abstract-bearing exact match among either provider.
        for cand in cands:
            if cand[5] < .90 or (cited_year and (not cand[4] or abs(cand[4]-cited_year)>1)): continue
            xx=cand[2]
            aa=strip_jats(xx.get('abstract')) if cand[1]=='crossref' else inv_to_text(xx.get('abstract_inverted_index'))
            if aa:
                abstract=aa
                source=('https://doi.org/'+xx.get('DOI')) if cand[1]=='crossref' and xx.get('DOI') else xx.get('id')
                if not doi:
                    doi=xx.get('DOI') if cand[1]=='crossref' else (xx.get('doi') or '').replace('https://doi.org/','') or None
                break
        notes.append(f'verified by title similarity {best[5]:.3f}, year {best[4]}, and bibliographic search; best source {best[1]}')
    else:
        notes.append('No candidate passed title-and-year verification threshold.' + (f' Best similarity {best[5]:.3f}, year {best[4]}.' if best else ''))
    # Preserve cited DOI when resolver metadata search did not surface it.
    if not doi and rec.get('dois_as_cited'):
        doi=rec['dois_as_cited'][0]; paper='https://doi.org/'+doi
        notes.append('DOI taken from source citation; title match still requires resolver verification.' if not verified else 'DOI taken from source citation.')
    rtype=rec.get('resource_type')
    if abstract:
        status='retrieved'
    elif rtype in {'grant_award','dataset'}:
        status='no_abstract_expected'
    elif verified:
        status='not_found'
    else:
        status='unresolved_citation'
    result={'id':rid,'resolved_title':title if verified else None,'resolved_doi':doi,'paper_url':paper,'abstract':abstract,'abstract_status':status,'abstract_source_url':source,'retrieved_at':datetime.now(timezone.utc).isoformat(),'metadata_source_url':meta,'license':license_,'full_text_url':full,'notes':' '.join(notes),'attempts':attempts}
    results.append(result)
    (OUT/'results.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in results)+'\n')
    print(rid,status,doi,title[:70])
    time.sleep(.12)
