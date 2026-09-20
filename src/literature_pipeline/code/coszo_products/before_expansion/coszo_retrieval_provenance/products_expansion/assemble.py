"""Assemble expanded COSZO corpus; preserve original extraction and retrieval evidence."""
import json, hashlib, shutil, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / 'coszo_abstracts/package'
OUT = ROOT / 'package'
def read(p):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def write(p, records):
    p.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
def text(v):
    return v if isinstance(v,str) else json.dumps(v,ensure_ascii=False)

def main():
    old = read(OLD/'coszo_literature.jsonl')
    seeds = read(ROOT/'new_citations.jsonl')
    added = read(ROOT/'additional_occurrences.jsonl')
    occmap = {r['occurrence_id']:r['canonical_id'] for r in added}
    results = {}; mappings = {}
    for batch in ['a','b','extra','parent']:
        for r in read(ROOT/f'retrieval_{batch}/results.jsonl'):
            source_id = r['id']
            if batch == 'b':
                key = occmap[f'COSZO-ADD-{40+int(source_id.rsplit("-",1)[1]):03d}']
            elif batch == 'extra':
                key = occmap[f'COSZO-ADD-{55+int(source_id.rsplit("-",1)[1]):03d}']
            else:
                key = source_id
            assert key not in results, key
            mappings[source_id] = key
            results[key] = {**r,'id':key,'retrieval_batch':f'products_{batch}'}
    assert set(results) == {s['id'] for s in seeds}
    records = old + [{**s, **results[s['id']], 'canonical_id':s['id'],
                      'citation':s['citation'], 'citation_as_extracted':s['citation_as_extracted'],
                      'provenance':s['provenance']} for s in seeds]
    # This citation's title contains 1998–2008; the printed publication year is 2010.
    next(r for r in records if r['id']=='COSZO-REF-151')['year_as_cited']='2010'
    # Do not silently create duplicate canonical nodes when retrieval reveals a DOI match.
    dois = defaultdict(list)
    for r in records:
        if r.get('resolved_doi'): dois[r['resolved_doi'].lower().strip()].append(r['id'])
    collisions = {k:v for k,v in dois.items() if len(v)>1}
    assert not collisions, ('DOI collisions require review',collisions)
    occurrences = []
    for s in read(ROOT.parent/'coszo/deliverables/coszo_citations.jsonl'):
        occurrences.append({'occurrence_id':s['id'],'canonical_id':s['canonical_id'],
            'citation':s['citation'],'citation_as_extracted':s['citation_as_extracted'],
            'section':s['provenance']['section'],
            'pdf_pages_1_based':s['provenance']['pdf_pages_1_based'],
            'printed_packet_pages':s['provenance']['printed_packet_pages'],
            'owner':None,'owner_status':'not_applicable','match_method':'original_bibliography',
            'doi_as_cited':s.get('dois_as_cited',[])})
    for o in added:
        o = dict(o)
        ds = o.get('doi_as_cited') or []
        o['doi_as_cited'] = [ds] if isinstance(ds,str) else ds
        o['owner_status'] = 'inferred' if 'inferred' in text(o.get('notes','')).lower() else ('explicit_or_section_context' if o.get('owner') else 'not_applicable')
        occurrences.append(o)
    byid = {r['id']:r for r in records}
    assert len(byid)==len(records)
    assert len({o['occurrence_id'] for o in occurrences})==len(occurrences)
    edges=defaultdict(list)
    for o in occurrences:
        assert o['canonical_id'] in byid
        edges[o['canonical_id']].append(o['occurrence_id'])
    shutil.copytree(OLD,OUT,dirs_exist_ok=True)
    for p in (ROOT.parent/'coszo/deliverables').glob('coszo_citations*'):
        shutil.copy2(p,OUT/p.name)
    hashes={}
    for r in records:
        r['schema_version']='1.1'
        r['source_occurrence_ids']=edges[r['id']]
        a=r.get('abstract')
        if a and r['id']=='COSZO-REF-164':
            a=a.replace('tools.Marine','tools. Marine')
        if a:
            a=a.strip();r['abstract']=a
            assert r['abstract_status']=='retrieved'
            assert r.get('abstract_source_url') and r.get('retrieved_at')
            assert len(a.split())>=20
            assert not re.search(r'<\/?(?:jats|p|abstract)\b|access denied|enable javascript|captcha',a,re.I),r['id']
            h=hashlib.sha256(a.encode()).hexdigest()
            assert h not in hashes, ('identical abstracts',r['id'],hashes.get(h))
            hashes[h]=r['id']
        else:
            assert r['abstract_status'] not in ('retrieved','not_yet_retrieved')
        if r.get('resource_type')=='unclassified':
            r['resource_type']='journal_article' if r['id'] in {f'COSZO-REF-{n:03d}' for n in range(168,176)} else 'unclassified'
            r['resource_type_status']='classified_from_verified_metadata' if r['resource_type']!='unclassified' else 'unclassified'
        r['full_text_status']=r.get('full_text_status') or ('verified_reachable_during_collection' if r.get('full_text_url') else 'no_verified_link_in_collection')
        if r.get('source_description'):
            r['source_description_url']=r.get('source_description_url') or r.get('metadata_source_url')
            r['source_description_type']=r.get('source_description_type') or 'source_description_see_notes'
        r['abstract_file']=f'abstracts/{r["id"]}.md' if a else None
        if a and r['id'] in results:
            lines=[f'# {r.get("resolved_title") or r["id"]}','','## Citation','',r['citation'],'','## Abstract','',a,'','## Provenance','',f'- Citation ID: {r["id"]}',f'- Paper: {r.get("paper_url") or "Unresolved"}',f'- DOI: {r.get("resolved_doi") or "Not identified"}',f'- Abstract source: {r["abstract_source_url"]}',f'- Retrieved: {r["retrieved_at"]}',f'- Source occurrences: {", ".join(r["source_occurrence_ids"])}','- Source abstract; not an agent-generated summary.']
            if r.get('notes'): lines+=['',text(r['notes'])]
            (OUT/r['abstract_file']).write_text('\n'.join(lines)+'\n')
    write(OUT/'coszo_literature.jsonl',records)
    write(OUT/'coszo_citation_occurrences.jsonl',occurrences)
    write(OUT/'coszo_additional_citations.jsonl',added)
    queue=[{k:r.get(k) for k in ['id','citation','resource_type','abstract_status','paper_url','notes','source_occurrence_ids','attempts']} for r in records if not r.get('abstract')]
    write(OUT/'coszo_abstracts_review_queue.jsonl',queue)
    counts=Counter(r['abstract_status'] for r in records)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),
        'source_document':'COSZO Project DataMSRI.pdf','source_sha256':records[0]['provenance']['source_sha256'],
        'source_pdf_pages':542,'source_occurrences':len(occurrences),'unique_references':len(records),
        'additional_occurrences':len(added),'additional_canonical_records':len(seeds),
        'abstracts_retrieved':len(hashes),'source_descriptions_retrieved':sum(bool(r.get('source_description')) for r in records),
        'status_counts':dict(counts),'collection_pass_complete':True,'all_abstracts_available':not queue,
        'scope':'Main bibliography, available biosketch product lists, execution-plan references, and technical literature/manual lists.',
        'limits':['The supplied PDF has 542 physical pages with discontinuous printed packet pagination; missing packet pages cannot be reconstructed.',
                  'Professional activities, bare software filenames, and internal engineering document-number tables are excluded; see coverage audit.',
                  'An unavailable abstract remains null; source descriptions are separate.']}
    (OUT/'coszo_abstracts_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    lines=['# COSZO literature collection','',f'{len(records)} canonical records from {len(occurrences)} citation occurrences; {len(hashes)} retrieved abstracts.','',
           'Expanded to include the available “Products Most Closely Related to the Proposed Project,” “Other Significant Products,” main “References Cited,” execution-plan references, and technical literature lists.','',
           '## Files','',
           '- `coszo_literature.jsonl`: canonical works, real abstracts, paper links, retrieval metadata and source-occurrence IDs.',
           '- `coszo_citation_occurrences.jsonl`: every extracted occurrence, original citation, section and page location; join `canonical_id` to a literature record.',
           '- `coszo_all_citations.md`: readable citation list grouped by source section/page.',
           '- `abstracts/`: one Markdown file per retrieved abstract.',
           '- `coszo_abstracts_review_queue.jsonl`: entries without a retrieved abstract and the reasons.',
           '- `coszo_retrieval_provenance/products_expansion/`: additional extraction, coverage audit, raw retrieval responses and ID mapping.',
           '- `coszo_citations.*`: preserved first-pass snapshot of the main bibliography only. Use the occurrence table for expanded coverage.','',
           '## Coverage and interpretation','',
           'The supplied 542-page PDF omits portions of the original packet. Some product lists start mid-list or mid-citation. We preserve what is visible and document gaps rather than reconstruct absent entries. Product-list owner names inferred from context are marked `owner_status: inferred`; authorship remains in the citation.','',
           'Repeated citations map to one canonical work while retaining separate occurrence edges. Professional activity statements, bare software filenames and internal engineering reference-number tables are excluded. All 50 text-poor pages were visually reviewed as contact sheets and contain engineering diagrams or test forms; no bibliography lists were observed. This is not an OCR transcription of those forms.','',
           'A null abstract is an explicit retrieval outcome. Book, website and manual descriptions, when found, are stored as `source_description`, not as abstracts. A DOI or landing-page link does not imply full-text access. Original citations are preserved separately from resolved metadata; retrieved source license metadata does not imply a blanket reuse license.','',
           '## Status counts','']
    lines += [f'- {k}: {v}' for k,v in sorted(counts.items())]
    lines += ['','## Index','','| ID | Work | Abstract status |','| --- | --- | --- |']
    for r in records:
        label=(r.get('resolved_title') or r['citation']).replace('|','\\|').replace('\n',' ')
        link=f'[{r["id"]}]({r["abstract_file"]})' if r['abstract_file'] else r['id']
        lines.append(f'| {link} | {label} | {r["abstract_status"]} |')
    (OUT/'coszo_abstracts_README.md').write_text('\n'.join(lines)+'\n')
    lines=['# COSZO citations across the supplied PDF','',f'{len(occurrences)} occurrences mapped to {len(records)} canonical records. Physical PDF page numbers are one-based; printed packet page numbers are separate.','']
    previous=None
    for o in occurrences:
        group=(o['section'],tuple(o['pdf_pages_1_based']),o.get('owner'))
        if group!=previous:
            lines += [f'## {o["section"]} — PDF pages {", ".join(map(str,o["pdf_pages_1_based"]))}', '']
            if o.get('owner'): lines += [f'Product-list owner: {o["owner"]} ({o["owner_status"]}).','']
            previous=group
        r=byid[o['canonical_id']]
        extra=f' [Paper / source]({r["paper_url"]})' if r.get('paper_url') else ''
        if len(o['citation'])<60 and r.get('resolved_title'):
            extra=f' Resolved work: {r["resolved_title"]}.'+extra
        lines += [f'- **{o["occurrence_id"]} → {o["canonical_id"]}**: {o["citation"]} (Printed packet pages {", ".join(map(str,o["printed_packet_pages"]))}.){extra}','']
    (OUT/'coszo_all_citations.md').write_text('\n'.join(lines)+'\n')
    dest=OUT/'coszo_retrieval_provenance/products_expansion'
    dest.mkdir(parents=True,exist_ok=True)
    for name in ['a','b','retrieval_a','retrieval_b','retrieval_extra','retrieval_parent']:
        shutil.copytree(ROOT/name,dest/name,dirs_exist_ok=True)
    for name in ['extraction_a.jsonl','extraction_b.jsonl','extraction_extra.jsonl','additional_occurrences.jsonl','new_citations.jsonl','coverage_audit.json','manual_matches.json','deduplicate.py','assemble.py']:
        shutil.copy2(ROOT/name,dest/name)
    (dest/'retrieval_id_mapping.json').write_text(json.dumps(mappings,indent=2)+'\n')
    (dest/'visual_audit').mkdir(exist_ok=True)
    for p in (ROOT/'visual_audit').glob('sheet*.png'): shutil.copy2(p,dest/'visual_audit'/p.name)
    expected={r['id']+'.md' for r in records if r.get('abstract')}
    assert expected=={p.name for p in (OUT/'abstracts').glob('*.md')}
    checksums={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='coszo_collection_checksums.json'}
    (OUT/'coszo_collection_checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
