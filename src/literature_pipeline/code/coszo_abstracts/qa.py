import json,re,unicodedata
from pathlib import Path
from collections import Counter
root=Path(__file__).resolve().parent
seed={r['id']:r for r in map(json.loads,Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl').read_text().splitlines())}
def words(s):
 s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
 return set(re.findall(r'[a-z0-9]+',s))
for p in sorted(root.glob('batch*/results.jsonl')):
 rs=[json.loads(s) for s in p.read_text().splitlines() if s]
 print(p.parent.name,len(rs),dict(Counter(r.get('abstract_status') for r in rs)))
 for r in rs:
  if not r.get('abstract'):continue
  title=words(r.get('resolved_title'))
  coverage=len(title&words(seed[r['id']]['citation']))/len(title) if title else 0
  text=r['abstract'];n=len(text.split())
  problems=[]
  if coverage<.78:problems.append(f'title token coverage {coverage:.2f}')
  if n<50:problems.append(f'short abstract {n} words')
  if n>650:problems.append(f'long abstract {n} words')
  if re.search(r'<[^>]*>|copyright|all rights reserved|access denied|captcha|enable javascript|download pdf',text,re.I):problems.append('possible artifact/legal footer')
  if problems:print(r['id'],problems,r.get('resolved_title'))
