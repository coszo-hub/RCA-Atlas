#!/usr/bin/env python3
import json, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

OUT=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1')
rows=[json.loads(l) for l in (OUT/'results.jsonl').read_text().splitlines()]
log=[]
for r in rows:
    url=r.get('full_text_url')
    if not url: continue
    entry={'id':r['id'],'url':url}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'COSZO bibliography link verification','Range':'bytes=0-1023'})
        with urllib.request.urlopen(req,timeout=30) as x:
            chunk=x.read(1024); entry.update(status=x.status,final_url=x.geturl(),content_type=x.headers.get('Content-Type'),bytes_read=len(chunk),verified_at=datetime.now(timezone.utc).isoformat())
            valid=x.status in (200,206) and (len(chunk)>0 or x.headers.get('Content-Length'))
    except Exception as e:
        entry['error']=f'{type(e).__name__}: {e}'; valid=False
    log.append(entry)
    r.setdefault('attempts',[]).append({'url':url,'result':('verified live full-text response: '+str({k:entry.get(k) for k in ('status','final_url','content_type')})) if valid else ('full-text link verification failed: '+entry.get('error','empty response'))})
    if valid:
        r['notes']=((r.get('notes') or '')+' full_text_url returned a live nonempty response during retrieval.').strip()
    else:
        r['notes']=((r.get('notes') or '')+' Removed metadata-advertised full_text_url because live verification failed.').strip(); r['full_text_url']=None
(OUT/'full_text_link_checks.json').write_text(json.dumps(log,ensure_ascii=False,indent=2))
(OUT/'results.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
