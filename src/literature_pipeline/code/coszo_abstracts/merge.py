"""Validate independent abstract batches and assemble the literature corpus."""
import json, re, hashlib, shutil
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
SEED=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')
OUT=ROOT/'package'

def read_jsonl(p):
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

def main():
    seed=read_jsonl(SEED)
    canonical={r['id']:r for r in seed if not r.get('duplicate_of')}
    occurrences=defaultdict(list)
    for r in seed: occurrences[r['canonical_id']].append(r['id'])
    results={}
    for batch in range(1,4):
        p=ROOT/f'batch{batch}'/'results.jsonl'
        for r in read_jsonl(p):
            assert r['id'] in canonical, ('Unexpected ID',r['id'])
            assert r['id'] not in results, ('Duplicate output ID',r['id'])
            r['retrieval_batch']=batch
            results[r['id']]=r
    overrides=ROOT/'parent_overrides.jsonl'
    if overrides.exists():
        for r in read_jsonl(overrides): results[r['id']]=r
    assert set(results)==set(canonical), ('Missing records',sorted(set(canonical)-set(results)))
    OUT.mkdir(exist_ok=True)
    (OUT/'abstracts').mkdir(exist_ok=True)
    merged=[]; issues=[]; abstract_hashes={}
    for key,s in canonical.items():
        r=results[key]
        a=r.get('abstract')
        if a is not None:
            a=a.strip()
            assert a and r.get('abstract_status')=='retrieved', ('Invalid abstract/status',key)
            assert r.get('abstract_source_url'), ('Missing abstract provenance',key)
            assert r.get('retrieved_at'), ('Missing retrieval date',key)
            assert len(a.split())>=20, ('Unexpectedly short abstract',key)
            h=hashlib.sha256(a.encode()).hexdigest()
            assert h not in abstract_hashes, ('Identical abstracts for distinct works',key,abstract_hashes.get(h))
            abstract_hashes[h]=key
            if re.search(r'<\/?(?:jats|p|title|abstract)\b|access denied|enable javascript|captcha',a,re.I):
                issues.append({'id':key,'issue':'Check extraction artifacts or access-error text'})
        else:
            assert r.get('abstract_status')!='retrieved', ('Missing retrieved abstract',key)
        doc={**s,**r,'abstract':a,'source_occurrence_ids':occurrences[key], 'schema_version':'1.0'}
        doc['provenance']=s['provenance']
        doc['citation']=s['citation']
        doc['full_text_status']=r.get('full_text_status') or ('verified_reachable_during_collection' if r.get('full_text_url') else 'no_verified_link_in_collection')
        if doc.get('source_description') and not doc.get('source_description_url'):
            doc['source_description_url']=r.get('metadata_source_url')
        if doc.get('source_description') and not doc.get('source_description_type'):
            doc['source_description_type']='source_description_see_notes' 
        doc['abstract_file']=f'abstracts/{key}.md' if a else None
        if a:
            title=r.get('resolved_title') or key
            lines=[f'# {title}','','## Citation','',s['citation'],'','## Abstract','',a,'','## Retrieval provenance','',f'- Citation ID: {key}',f'- Paper: {r.get("paper_url") or "Unresolved"}',f'- DOI: {r.get("resolved_doi") or "Not identified"}',f'- Abstract source: {r["abstract_source_url"]}',f'- Retrieved: {r["retrieved_at"]}',f'- License metadata: {json.dumps(r.get("license"),ensure_ascii=False) if r.get("license") else "Not specified by retrieved metadata"}','- Text is a source abstract, not an agent-generated summary.']
            if r.get('notes'): lines+=['', 'Notes: '+ (r['notes'] if isinstance(r['notes'],str) else json.dumps(r['notes'],ensure_ascii=False))]
            (OUT/'abstracts'/f'{key}.md').write_text('\n'.join(lines)+'\n')
        merged.append(doc)
    (OUT/'coszo_literature.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in merged))
    unresolved=[{'id':r['id'],'citation':r['citation'],'resource_type':r['resource_type'],'abstract_status':r['abstract_status'],'paper_url':r.get('paper_url'),'notes':r.get('notes'),'attempts':r.get('attempts',[])} for r in merged if not r['abstract']]
    (OUT/'coszo_abstracts_review_queue.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in unresolved))
    counts=Counter(r['abstract_status'] for r in merged)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'source_bibliography':SEED.name,'source_bibliography_sha256':hashlib.sha256(SEED.read_bytes()).hexdigest(),'source_occurrences':len(seed),'unique_references':len(merged),'abstracts_retrieved':len(abstract_hashes),'source_descriptions_retrieved':sum(bool(r.get('source_description')) for r in merged),'status_counts':dict(counts),'quality_flags':issues,'collection_complete':True,'all_abstracts_available':not unresolved}
    (OUT/'coszo_abstracts_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    summary=['# COSZO literature abstract collection','',f'{len(abstract_hashes)} source abstracts retrieved across {len(merged)} unique references ({len(seed)} original bibliography occurrences).','', '## Files','', '- `coszo_literature.jsonl`: canonical citation records enriched with abstracts, paper links, metadata sources, retrieval dates, attempt logs, and availability status.','- `abstracts/`: one readable Markdown file per retrieved abstract.','- `coszo_abstracts_review_queue.jsonl`: references without a retrieved abstract and their recorded reasons.','- `coszo_abstracts_manifest.json`: counts and validation results.','- `coszo_retrieval_provenance/`: agent retrieval outputs and available raw source responses.','','Original `coszo_citations.*` files remain the citation-extraction snapshot; use `coszo_literature.jsonl` for the enriched corpus.','','## Status counts','']
    summary += [f'- {k}: {v}' for k,v in sorted(counts.items())]
    summary += ['', '## Interpretation','', 'A null abstract is an explicit collection outcome, not a fabricated summary. Non-article descriptions, where available, are stored separately as `source_description`. Some reports, grants, institutional pages, and unpublished works may not have a conventional abstract. Unavailable and blocked records remain in the review queue.','','The two occurrences of MacCready et al. (2021), COSZO-REF-064 and COSZO-REF-066, map to canonical record COSZO-REF-064. `source_occurrence_ids` retains both citation edges. Source citations and their PDF provenance remain intact. Resolved metadata and version notes are separate from the original citation.','','An article landing page or DOI link does not imply full-text access. `full_text_url` records links located during retrieval; this is not a full-text paper collection. Selected supporting PDFs used to extract or verify abstracts are retained under retrieval provenance. License metadata is retained where provided and does not imply a blanket reuse license for all records.','','## Index','', '| ID | Resolved work / citation | Abstract status |','| --- | --- | --- |']
    for r in merged:
        label=r.get('resolved_title') or r['citation']
        label=label.replace('|','\\|').replace('\n',' ')
        rid=f'[{r["id"]}]({r["abstract_file"]})' if r['abstract_file'] else r['id']
        summary.append(f'| {rid} | {label} | {r["abstract_status"]} |')
    (OUT/'coszo_abstracts_README.md').write_text('\n'.join(summary)+'\n')
    provenance=OUT/'coszo_retrieval_provenance'
    for name in ['batch1','batch2','batch3','parent']:
        src=ROOT/name
        dst=provenance/name
        dst.mkdir(parents=True,exist_ok=True)
        if (src/'raw').exists(): shutil.copytree(src/'raw',dst/'raw',dirs_exist_ok=True)
        for f in src.glob('*.jsonl'): shutil.copy2(f,dst/f.name)
        for f in src.glob('*.py'): shutil.copy2(f,dst/f.name)
        for f in src.glob('*.json'): shutil.copy2(f,dst/f.name)
        for f in src.glob('*.md'): shutil.copy2(f,dst/f.name)
    if overrides.exists(): shutil.copy2(overrides,provenance/overrides.name)
    expected={r['id']+'.md' for r in merged if r['abstract']}
    actual={p.name for p in (OUT/'abstracts').glob('*.md')}
    assert expected==actual, ('Abstract file coverage mismatch',expected^actual)
    file_hashes={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='coszo_collection_checksums.json'}
    (OUT/'coszo_collection_checksums.json').write_text(json.dumps(file_hashes,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
