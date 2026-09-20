#!/usr/bin/env python3
exec(open('analyze.py').read().split('rows=[]')[0])
for line in SRC.open():
 o=json.loads(line); n=int(o['id'].rsplit('-',1)[1])
 if not 90<=n<=133: continue
 target=title_from_citation(o['citation']); xs=json.loads((RAW/f"{o['id']}_openalex.json").read_text()).get('results',[])
 xs.sort(key=lambda x:score(target,x.get('title','')),reverse=True)
 if not xs or score(target,xs[0].get('title',''))<.85: continue
 x=xs[0]; d=x.get('abstract_inverted_index') or {}; arr=[None]*(max((max(v) for v in d.values()),default=-1)+1)
 for word,positions in d.items():
  for i in positions: arr[i]=word
 abstract=' '.join(y or '' for y in arr)
 print(o['id'],round(score(target,x.get('title','')),2),len(abstract),repr(abstract[:220]))
