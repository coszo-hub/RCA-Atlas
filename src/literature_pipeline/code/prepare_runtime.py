"""Separate the runtime literature corpus from pipeline code and provenance."""
import hashlib,json,os,shutil
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

WORK=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent')
PROJECT=Path('/Users/quakehunter/Documents/RCN Agent ')
DATA=PROJECT/'data'
LIT=DATA/'Literature'
OLD_CODE=DATA/'Source Code'
SRC=PROJECT/'src'
PIPE=SRC/'literature_pipeline'

def read_jsonl(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

records=read_jsonl(LIT/'literature.jsonl')
occurrences=read_jsonl(LIT/'literature_occurrences.jsonl')
assert len(records)==336 and len(occurrences)==398
assert len({r['id'] for r in records})==len(records)
byid={r['id']:r for r in records};edges=defaultdict(list)
for o in occurrences:
    assert o['canonical_id'] in byid
    edges[o['canonical_id']].append(o)
for r in records:
    expected=r.get('source_occurrence_ids') or []
    actual=[o['occurrence_id'] for o in edges[r['id']]]
    assert expected==actual,(r['id'],expected,actual)
    r['source_occurrences']=edges[r['id']]
    r['source_occurrence_count']=len(actual)
    r.pop('abstract_file',None);r.pop('record_file',None)
    r['schema_version']='1.3-runtime'
assert sum(r['source_occurrence_count'] for r in records)==398

# Reuse the existing empty code folder as the requested lowercase src folder.
if not SRC.exists() and OLD_CODE.exists():
    assert not any(OLD_CODE.iterdir()),'Source Code is not empty; refusing to rename it.'
    OLD_CODE.rename(SRC)
SRC.mkdir(exist_ok=True)
archive=PIPE/'archive';provenance=PIPE/'provenance';code=PIPE/'code';reports=PIPE/'reports'
for p in [archive,provenance,code,reports]:p.mkdir(parents=True,exist_ok=True)

# Install the self-contained corpus atomically.
tmp=LIT/'.literature.jsonl.tmp'
tmp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
os.replace(tmp,LIT/'literature.jsonl')

# Move large provenance trees out of the runtime data folder.
for name in ['coszo_retrieval_provenance','zotero_retrieval_provenance']:
    src=LIT/name
    if src.exists():
        dst=provenance/name
        if dst.exists():shutil.rmtree(dst)
        shutil.move(str(src),str(dst))

# Archive every redundant/source-specific view. The runtime folder keeps only
# the self-contained canonical JSONL and the user's glossary PDF.
keep={'literature.jsonl','Glossary.pdf'}
for item in list(LIT.iterdir()):
    if item.name in keep:continue
    dst=archive/item.name
    if dst.exists():
        if dst.is_dir():shutil.rmtree(dst)
        else:dst.unlink()
    shutil.move(str(item),str(dst))

# Copy all reproducible pipeline Python sources into src, preserving stages.
sources={
    'coszo_abstracts':WORK/'tmp/coszo_abstracts',
    'coszo_products':WORK/'tmp/coszo_products',
    'zotero_expansion':WORK/'tmp/zotero_expansion',
}
for label,root in sources.items():
    if not root.exists():continue
    for p in root.rglob('*.py'):
        if '/package/' in str(p):continue
        dst=code/label/p.relative_to(root);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
shutil.copy2(Path(__file__),code/'prepare_runtime.py')

# Keep concise reports and manifests next to the code rather than agent data.
report_sources=[
    WORK/'tmp/zotero_expansion/final_qa_report.json',
    WORK/'tmp/zotero_expansion/rmt_audit.json',
    WORK/'tmp/zotero_expansion/endurance_audit.json',
    WORK/'tmp/zotero_expansion/dedup_audit.json',
]
for p in report_sources:
    if p.exists():shutil.copy2(p,reports/p.name)

readme='''# Literature pipeline support files

`../../data/Literature/literature.jsonl` is the runtime Graph-RAG corpus. Each JSONL row is one canonical work and embeds its `source_occurrences`, so the runtime does not need a second edge file.

- `code/`: extraction, retrieval, assembly, validation, and runtime-preparation scripts.
- `provenance/`: raw API responses, retrieved pages, extraction evidence, and agent retrieval logs.
- `archive/`: source-specific snapshots, redundant Markdown views, manifests, checksums, and review queues from corpus construction.
- `reports/`: final audits and QA reports.

The runtime `Literature` folder intentionally contains only the canonical corpus and `Glossary.pdf`.
'''
(PIPE/'README.md').write_text(readme)
manifest={
    'created_at':datetime.now(timezone.utc).isoformat(),
    'runtime_folder':str(LIT),
    'runtime_files':sorted(p.name for p in LIT.iterdir()),
    'canonical_records':len(records),'embedded_source_occurrences':len(occurrences),
    'abstracts_retrieved':sum(bool(r.get('abstract')) for r in records),
    'literature_sha256':sha(LIT/'literature.jsonl'),
    'glossary_sha256':sha(LIT/'Glossary.pdf') if (LIT/'Glossary.pdf').exists() else None,
    'support_folder':str(PIPE),
}
(PIPE/'runtime_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

assert sorted(p.name for p in LIT.iterdir())==['Glossary.pdf','literature.jsonl']
check=read_jsonl(LIT/'literature.jsonl')
assert len(check)==336 and sum(len(r['source_occurrences']) for r in check)==398
assert all(r.get('abstract') and r['abstract_status']=='retrieved' for r in check if r['id'].startswith('OOI-ZOT-'))
print(json.dumps(manifest))
