"""Build a unified literature corpus from the COSZO extraction and two public OOI Zotero collections."""
import hashlib, html, json, re, shutil, unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature')
RAW=ROOT.parent/'coszo_products'
OUT=ROOT/'package'
COLLECTIONS={
    'RMTSE2IH':{'name':'Regional Cabled Array','files':['zotero_RMTSE2IH_top1.json','zotero_RMTSE2IH_top2.json']},
    'E5UH7L89':{'name':'Coastal Endurance Array','files':['zotero_E5UH7L89_top1.json']},
}

def read_jsonl(p): return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def write_jsonl(p,rows): p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
def norm_doi(s): return re.sub(r'^https?://(?:dx\.)?doi.org/','',(s or '').strip(),flags=re.I).lower().rstrip('.,;')
def norm_title(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]','',s)
def clean_abstract(s):
    s=re.sub(r'\s+',' ',html.unescape((s or '').strip())).strip()
    return re.sub(r'^Abstract\s*:?\s+','',s,flags=re.I)
def clean_literal(s): return html.unescape((s or '').replace('&⋕x27;',"'"))
def split_urls(s): return re.findall(r'https?://\S+',s or '')
def creator_name(c):
    return c.get('name') or ' '.join(x for x in [c.get('firstName','').strip(),c.get('lastName','').strip()] if x).strip()
def citation(d):
    authors=', '.join(creator_name(c) for c in d.get('creators',[]) if c.get('creatorType') in ('author','editor'))
    fields=[authors or None, f'({d.get("date")}).' if d.get('date') else None, d.get('title'),
            d.get('publicationTitle') or d.get('university') or d.get('bookTitle')]
    c=' '.join(str(x).strip().rstrip('.')+'.' for x in fields if x)
    if d.get('volume'): c+=f' {d["volume"]}'
    if d.get('issue'): c+=f'({d["issue"]})'
    if d.get('pages'): c+=f': {d["pages"]}'
    if d.get('DOI'): c+=f'. https://doi.org/{norm_doi(d["DOI"])}'
    elif d.get('url'): c+=f'. {d["url"]}'
    return c.strip()
def resource_type(t):
    return {'journalArticle':'journal_article','bookSection':'book_chapter','thesis':'thesis'}.get(t,t or 'unclassified')
def record_markdown(r):
    lines=[f'# {r.get("resolved_title") or r["id"]}','','## Citation','',r['citation'],'','## Record','',
           f'- Citation ID: {r["id"]}',f'- Resource type: {r.get("resource_type") or "Unclassified"}',
           f'- Abstract status: {r.get("abstract_status")}',f'- Paper/source: {r.get("paper_url") or "No verified public link"}',
           f'- DOI: {r.get("resolved_doi") or "Not identified"}',f'- Source occurrences: {", ".join(r.get("source_occurrence_ids",[]))}']
    if r.get('abstract'):
        lines += ['', '## Abstract','',r['abstract'],'',f'Abstract source: {r.get("abstract_source_url") or "Not recorded"}']
    elif r.get('source_description'):
        lines += ['', '## Source description','',r['source_description'],'',
                  f'Description type: {r.get("source_description_type") or "source description"}',
                  f'Description source: {r.get("source_description_url") or r.get("metadata_source_url") or "Not recorded"}']
    else:
        lines += ['', '## Abstract availability','',
                  'No formal abstract was retrieved. See the status and notes below.']
    if r.get('notes'): lines += ['', '## Notes','',r['notes'] if isinstance(r['notes'],str) else json.dumps(r['notes'],ensure_ascii=False)]
    return '\n'.join(lines)+'\n'

def main():
    base=read_jsonl(BASE/'coszo_literature.jsonl')
    old_occ=read_jsonl(BASE/'coszo_citation_occurrences.jsonl')
    shutil.rmtree(OUT,ignore_errors=True)
    shutil.copytree(BASE,OUT)
    for folder in ['records','abstracts']:(OUT/folder).mkdir(exist_ok=True)
    existing_doi={norm_doi(r.get('resolved_doi')):r['id'] for r in base if r.get('resolved_doi')}
    existing_title={norm_title(r.get('resolved_title')):r['id'] for r in base if r.get('resolved_title')}
    overrides={}
    for name in ['missing_results.jsonl','rmt_overrides.jsonl','endurance_overrides.jsonl']:
        if (ROOT/name).exists():
            for r in read_jsonl(ROOT/name):overrides[r['zotero_key']]=r
    manual_key_match={'PU7BMBHB':'COSZO-REF-019'}
    occurrences=[]; groups={}; order=[]
    for ckey,cmeta in COLLECTIONS.items():
        for file in cmeta['files']:
            for item in json.loads((RAW/file).read_text()):
                d=item['data']; doi=norm_doi(d.get('DOI')); title=norm_title(d.get('title'))
                identity='doi:'+doi if doi else 'title:'+title
                if identity not in groups: groups[identity]={'items':[],'collections':[]};order.append(identity)
                groups[identity]['items'].append(item)
                if ckey not in groups[identity]['collections']: groups[identity]['collections'].append(ckey)
                occurrences.append({'occurrence_id':f'ZOTERO-{ckey}-{item["key"]}','zotero_key':item['key'],
                    'collection_key':ckey,'collection_name':cmeta['name'],'title':d.get('title'),
                    'doi':doi or None,'item_type':d.get('itemType'),'date':d.get('date'),
                    'zotero_item_url':item['links']['alternate']['href'],'zotero_api_url':item['links']['self']['href']})
    nextid=1; novel=[]; id_for_identity={}; existing_matches=[];matched_overrides={}
    for identity in order:
        g=groups[identity];item=g['items'][0];d=item['data'];doi=norm_doi(d.get('DOI'));title=norm_title(d.get('title'))
        ov=overrides.get(item['key'])
        cid=manual_key_match.get(item['key']) or (existing_doi.get(doi) if doi else existing_title.get(title))
        if cid:
            id_for_identity[identity]=cid;existing_matches.append({'canonical_id':cid,'identity':identity,'zotero_key':item['key'],'collections':g['collections']})
            if ov:matched_overrides[cid]=ov
            continue
        cid=f'OOI-ZOT-{nextid:03d}';nextid+=1;id_for_identity[identity]=cid
        a=clean_abstract(ov['abstract']) if ov and ov.get('abstract') else clean_abstract(d.get('abstractNote'))
        status='retrieved' if a else (ov.get('abstract_status') if ov else 'not_found')
        year=(item.get('meta',{}).get('parsedDate') or d.get('date') or '')[:4]
        if not re.fullmatch(r'\d{4}',year): year=None
        item_api=item['links']['self']['href'];urls=split_urls(d.get('url'))
        paper='https://doi.org/'+doi if doi else (urls[0] if urls else item['links']['alternate']['href'])
        collections=[{'key':k,'name':COLLECTIONS[k]['name'],'url':f'https://www.zotero.org/groups/5351356/ooipublications/collections/{k}/collection'} for k in g['collections']]
        notes='Abstract and bibliographic metadata were supplied by the public OOI Zotero group; the abstract is source text, not an agent-generated summary.' if a else 'No abstract was present in the public Zotero item metadata.'
        if ov and ov.get('notes'): notes+=' '+ov['notes']
        dc=dict(d);dc['title']=clean_literal((ov or {}).get('resolved_title') or d.get('title'))
        if ov and ov.get('resolved_creators'):dc['creators']=ov['resolved_creators']
        elif ov and ov.get('resolved_authors'):dc['creators']=[{'creatorType':'author','name':n} for n in ov['resolved_authors']]
        if ov and ov.get('pages'):dc['pages']=ov['pages']
        rec={'id':cid,'canonical_id':cid,'duplicate_of':None,'citation_as_extracted':citation(d),'citation':citation(dc),
             'year_as_cited':year,'resource_type':resource_type(d.get('itemType')),
             'resource_type_status':'classified_from_zotero_item_type','dois_as_cited':[doi] if doi else [],
             'source_links':[{'url':item['links']['alternate']['href'],'provenance':'OOI Zotero item','verification_status':'retrieved'},
                             *[{'url':u,'provenance':'Zotero URL field','verification_status':'not_checked'} for u in urls]],
             'verified_metadata':[],'abstract':a or None,'abstract_status':status,'full_text_url':None,
             'full_text_status':'not_checked','review_notes':[],'provenance':{'source_document':'OOIPublications public Zotero group',
             'source_url':'https://www.zotero.org/groups/5351356/ooipublications','collections':collections,'zotero_key':item['key'],
             'retrieved_date':datetime.now(timezone.utc).date().isoformat()},'source_occurrence_ids':[],
             'resolved_title':dc.get('title'),'resolved_doi':doi or None,'paper_url':paper,
             'abstract_source_url':(ov.get('abstract_source_url') if ov else None) or (item_api if a else None),
             'retrieved_at':(ov.get('retrieved_at') if ov else None) or datetime.now(timezone.utc).isoformat(),
             'metadata_source_url':item_api,'license':None,'source_rights':d.get('rights') or None,
             'landing_page_url':(urls[0] if urls else None),'zotero_item_url':item['links']['alternate']['href'],
             'zotero_item_key':item['key'],'source_collections':collections,'notes':notes,
             'attempts':ov.get('attempts',[]) if ov else [],'schema_version':'1.2'}
        if ov and ov.get('resolved_authors'):rec['resolved_authors']=ov['resolved_authors']
        if dc.get('title')!=d.get('title'):rec['zotero_title_as_supplied']=d.get('title')
        novel.append(rec)
    for o in occurrences:
        identity='doi:'+o['doi'] if o['doi'] else 'title:'+norm_title(o['title'])
        o['canonical_id']=id_for_identity[identity]
    occurrence_ids=defaultdict(list)
    for o in old_occ+occurrences:occurrence_ids[o['canonical_id']].append(o['occurrence_id'])
    unified=[]
    for r in base+novel:
        r=dict(r)
        ov=matched_overrides.get(r['id'])
        if ov and ov.get('abstract') and not r.get('abstract'):
            r['abstract']=clean_abstract(ov['abstract']);r['abstract_status']='retrieved'
            r['abstract_source_url']=ov['abstract_source_url'];r['retrieved_at']=ov.get('retrieved_at') or datetime.now(timezone.utc).isoformat()
            r['notes']=((r.get('notes') or '')+' '+ov.get('notes','')).strip();r['attempts']=(r.get('attempts') or [])+ov.get('attempts',[])
            if ov.get('resolved_authors'):r['resolved_authors']=ov['resolved_authors']
        r['source_occurrence_ids']=occurrence_ids[r['id']];r['schema_version']='1.2'
        r['abstract_file']=f'abstracts/{r["id"]}.md' if r.get('abstract') else None
        r['record_file']=f'records/{r["id"]}.md';unified.append(r)
    # Cross-work integrity checks.
    bydoi=defaultdict(list)
    for r in unified:
        if r.get('resolved_doi'):bydoi[norm_doi(r['resolved_doi'])].append(r['id'])
    assert not {k:v for k,v in bydoi.items() if len(v)>1}
    ah={}
    for r in unified:
        if r.get('abstract'):
            assert r['abstract_status']=='retrieved' and r.get('abstract_source_url')
            assert len(r['abstract'].split())>=20
            h=hashlib.sha256(r['abstract'].encode()).hexdigest()
            # Same-source duplicates are disallowed across canonical records.
            assert h not in ah,(r['id'],ah.get(h));ah[h]=r['id']
        else: assert r['abstract_status']!='retrieved'
        (OUT/r['record_file']).write_text(record_markdown(r))
        if r.get('abstract'):
            lines=[f'# {r["resolved_title"]}','','## Citation','',r['citation'],'','## Abstract','',r['abstract'],'',
                   '## Retrieval provenance','',f'- Citation ID: {r["id"]}',f'- Paper: {r["paper_url"]}',
                   f'- DOI: {r.get("resolved_doi") or "Not identified"}',f'- Abstract source: {r["abstract_source_url"]}',
                   f'- Retrieved: {r["retrieved_at"]}','- Source abstract; not an agent-generated summary.']
            (OUT/r['abstract_file']).write_text('\n'.join(lines)+'\n')
    write_jsonl(OUT/'literature.jsonl',unified)
    write_jsonl(OUT/'ooi_zotero_literature.jsonl',[r for r in unified if r['id'].startswith('OOI-ZOT-')])
    write_jsonl(OUT/'literature_occurrences.jsonl',old_occ+occurrences)
    write_jsonl(OUT/'ooi_zotero_occurrences.jsonl',occurrences)
    write_jsonl(OUT/'literature_review_queue.jsonl',[r for r in unified if not r.get('abstract')])
    (OUT/'zotero_existing_matches.json').write_text(json.dumps(existing_matches,ensure_ascii=False,indent=2)+'\n')
    prov=OUT/'zotero_retrieval_provenance';prov.mkdir(exist_ok=True)
    for f in ['zotero_RMTSE2IH_top1.json','zotero_RMTSE2IH_top2.json','zotero_E5UH7L89_top1.json',
              'zotero_RMTSE2IH_collection.json','zotero_E5UH7L89_collection.json']:
        shutil.copy2(RAW/f,prov/f)
    for f in ['rmt_audit.json','endurance_audit.json','dedup_audit.json','crossref_validations.json','endurance_crossref.json','missing_results.jsonl','rmt_overrides.jsonl','endurance_overrides.jsonl','missing_attempts.json']:
        if (ROOT/f).exists():shutil.copy2(ROOT/f,prov/f)
    for f in ROOT.glob('*.py'):
        if f.name!='install.py':shutil.copy2(f,prov/f.name)
    for folder in ['missing_raw','raw_crossref','rmt_raw','raw']:
        if (ROOT/folder).exists():shutil.copytree(ROOT/folder,prov/folder,dirs_exist_ok=True)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'canonical_records':len(unified),
              'coszo_pdf_records':len(base),'new_zotero_records':len(novel),'zotero_top_level_occurrences':len(occurrences),
              'unique_zotero_works':len(groups),'zotero_matches_to_existing':len(existing_matches),
              'abstracts_retrieved':sum(bool(r.get('abstract')) for r in unified),
              'status_counts':dict(Counter(r['abstract_status'] for r in unified)),
              'collections':[{'key':k,'name':v['name'],'url':f'https://www.zotero.org/groups/5351356/ooipublications/collections/{k}/collection'} for k,v in COLLECTIONS.items()],
              'primary_graph_rag_file':'literature.jsonl','occurrence_edge_file':'literature_occurrences.jsonl'}
    (OUT/'literature_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    readme=['# Literature dataset','',f'{len(unified)} canonical literature records with {manifest["abstracts_retrieved"]} source abstracts.','',
            '## Primary Graph-RAG inputs','',
            '- `literature.jsonl`: unified canonical records from the COSZO PDF and the two OOI Zotero collections.',
            '- `literature_occurrences.jsonl`: source occurrence edges; join `canonical_id` to `literature.jsonl`.',
            '- `records/`: one readable Markdown record per canonical work.',
            '- `abstracts/`: one Markdown file per retrieved source abstract.',
            '- `literature_review_queue.jsonl`: records without a retrieved formal abstract.',
            '', '## Source-specific snapshots','',
            '- `coszo_literature.jsonl` and `coszo_citation_occurrences.jsonl`: COSZO PDF extraction.',
            '- `ooi_zotero_literature.jsonl` and `ooi_zotero_occurrences.jsonl`: new works and collection occurrences from Zotero.',
            '', '## Deduplication','',
            'Zotero works were merged by normalized DOI, with exact normalized title used only when no DOI was supplied. Matching Zotero items add source-occurrence edges to existing COSZO records. Cross-collection duplicates remain separate occurrences but share one canonical record.',
            '', '## Abstract handling','',
            'Zotero `abstractNote` text is stored as a source abstract after whitespace and HTML-entity normalization. Empty fields remain explicit retrieval outcomes. Descriptions, standfirsts, manuals, books, grants, datasets, and websites are not silently promoted to formal abstracts.']
    (OUT/'README.md').write_text('\n'.join(readme)+'\n')
    assert len(list((OUT/'records').glob('*.md')))==len(unified)
    assert len(list((OUT/'abstracts').glob('*.md')))==manifest['abstracts_retrieved']
    checks={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='literature_collection_checksums.json'}
    (OUT/'literature_collection_checksums.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
