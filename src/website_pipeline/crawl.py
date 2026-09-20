"""Collect public COSZO/RCA website content with traceable selection and artifacts."""
import argparse,concurrent.futures as cf,hashlib,html,json,re,time,urllib.request,urllib.error,urllib.parse,urllib.robotparser,shutil
from pathlib import Path
from datetime import datetime,timezone
from lxml import html as LH,etree

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'cache';CACHE.mkdir(exist_ok=True)
OUT=ROOT/'package';OUT.mkdir(exist_ok=True)
UA='COSZO-RCA-ResearchCorpus/1.0'
HOSTS=['coszo.org','interactiveoceans.washington.edu','oceanobservatories.org']
STRONG=re.compile(r'COSZO|Regional\s+Cabled\s+Array|Regional\s+Scale\s+Nodes|\bcabled\s+(?:array|observatory|network|continental margin|axial seamount)|\bRCA\b|\bRSN\b|Axial\s+(?:Seamount|Volcano|Caldera|Base)|(?:Southern\s+)?Hydrate\s+Ridge|(?:Oregon\s+)?Slope\s+Base|Oregon\s+(?:Shelf|Offshore|Mid[ -]?Slope)|Mid[ -]?Plate|\bASHES\b|International\s+District|VISIONS[\s’\x27-]*\d',re.I)
OTHER=re.compile(r'\b(?:Pioneer|Irminger|Argentine|Southern Ocean|Station Papa|Endurance|Global Array|Ocean Networks Canada|NEPTUNE Canada|Endeavour)\b',re.I)
UTILITY=re.compile(r'privacy|cookie|terms-of-use|^search$|^contact$|acknowledg|login|register',re.I)
now=lambda:datetime.now(timezone.utc).isoformat()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def jsonl(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in x))
def sid(prefix,s):return prefix+hashlib.sha256(s.encode()).hexdigest()[:16]
def norm(u,base=''):
 u=urllib.parse.urljoin(base,html.unescape(u or ''));p=urllib.parse.urlsplit(u)
 if p.scheme not in ['http','https']:return None
 host=p.netloc.lower().removeprefix('www.')
 return urllib.parse.urlunsplit(('https',host,p.path or '/',p.query,''))
def fetch(u):
 key=hashlib.sha256(u.encode()).hexdigest();meta=CACHE/(key+'.json');body=CACHE/(key+'.bin')
 if meta.exists():
  m=json.loads(meta.read_text())
  if m.get('status')==200 and body.exists():return m,body.read_bytes()
  try:
   if (datetime.now(timezone.utc)-datetime.fromisoformat(m['retrieved_at'])).total_seconds()<21600:return m,b''
  except:pass
 for i in range(2):
  try:
   req=urllib.request.Request(u,headers={'User-Agent':UA,'Accept':'*/*'})
   with urllib.request.urlopen(req,timeout=30) as res:
    data=res.read(24_000_001)
    if len(data)>24_000_000:raise ValueError('Resource exceeds 24 MB limit')
    m={'url':u,'final_url':res.url,'status':res.status,'content_type':res.headers.get('Content-Type',''),'retrieved_at':now(),'headers':dict(res.headers)}
   body.write_bytes(data);dump(meta,m);return m,data
  except Exception as e:
   m={'url':u,'status':getattr(e,'code',None),'error':str(e),'retrieved_at':now()}
   if getattr(e,'code',None) not in [429,500,502,503,504] and not isinstance(e,TimeoutError):break
   time.sleep(2**i)
 dump(meta,m);return m,b''
def getjson(u):
 m,b=fetch(u)
 try:return m,json.loads(b)
 except:return m,None
def plain(s):
 try:return ' '.join(LH.fromstring('<div>'+s+'</div>').text_content().split())
 except:return html.unescape(s or '')
def wp_get(host,typ,query=None):
 query=dict(query or {});query.update({'per_page':100,'page':1})
 base=f'https://{host}/wp-json/wp/v2/{typ}?'
 m,a=getjson(base+urllib.parse.urlencode(query))
 if not isinstance(a,list):return [],[m]
 pages=int(next((v for k,v in m.get('headers',{}).items() if k.lower()=='x-wp-totalpages'),'1'))
 out=list(a);errors=[]
 urls=[base+urllib.parse.urlencode({**query,'page':n}) for n in range(2,pages+1)]
 with cf.ThreadPoolExecutor(max_workers=3) as ex:
  for mm,aa in ex.map(getjson,urls):
   if isinstance(aa,list):out+=aa
   else:errors.append(mm)
 return out,errors
def discover():
 candidates={};fail=[];sitemaps={};wp_records={}
 for host in HOSTS:
  robots,b=fetch(f'https://{host}/robots.txt');dump(ROOT/'discovery'/f'{host}_robots.json',robots)
  if host=='coszo.org':continue
  m,b=fetch(f'https://{host}/wp-sitemap.xml')
  try:maps=etree.fromstring(b).xpath('//*[local-name()="loc"]/text()')
  except:maps=[]
  maps=[u for u in maps if 'sitemap-posts-' in u and not any(z in u for z in ['oceanwp_library','staff'])]
  allurls=[]
  for u in maps:
   mm,bb=fetch(u)
   try:allurls+=etree.fromstring(bb).xpath('//*[local-name()="loc"]/text()')
   except:fail.append(mm)
  sitemaps[host]=allurls
  types=(getjson(f'https://{host}/wp-json/wp/v2/types')[1] or {})
  allowed=['posts','pages','glossary'] if host.startswith('interactive') else ['posts','pages','kbe_knowledgebase','tribe_events','additional_asset','array','data_product','instrument_class','newsletter','pi_instrument','science_theme','site']
  for typ in allowed:
   if typ not in {x.get('rest_base') for x in types.values()}:continue
   # Full API content lacks navigation and allows reliable body relevance tests.
   rows,errs=wp_get(host,typ,{'_fields':'id,link,type,date,modified,title,content,excerpt,featured_media,parent,categories,tags'})
   fail+=errs
   for r in rows:
    u=norm(r['link']);wp_records[u]={**r,'site_host':host}
   print('INDEX',host,typ,len(rows),flush=True)
  for u in allurls:
   nu=norm(u)
   if nu not in wp_records and (host.startswith('interactive') or STRONG.search(urllib.parse.unquote(u))):
    candidates[nu]={'url':nu,'site_host':host,'discovery':'sitemap_non_api'}
 # Static COSZO site: crawl every same-site HTML page once, ignoring query/search URLs.
 queue=['https://coszo.org/'];seen=set()
 while queue:
  u=queue.pop(0)
  if u in seen:continue
  seen.add(u);m,b=fetch(u)
  if not b:fail.append(m);continue
  try:doc=LH.fromstring(b)
  except:continue
  candidates[u]={'url':u,'site_host':'coszo.org','discovery':'internal_link','html_cache_url':u}
  for href in doc.xpath('//a/@href'):
   v=norm(href,u)
   if not v:continue
   p=urllib.parse.urlsplit(v)
   if p.netloc=='coszo.org' and not p.query and (not Path(p.path).suffix or p.path.endswith(('.html','.htm'))):
    if v not in seen:queue.append(v)
 dump(ROOT/'wp_records.json',wp_records);dump(ROOT/'html_candidates.json',candidates);dump(ROOT/'sitemap_urls.json',sitemaps);dump(ROOT/'discovery_failures.json',fail)
 print('DISCOVERY COMPLETE',len(wp_records),len(candidates),flush=True)

def extract(fragment,url):
 doc=LH.fromstring('<div>'+fragment+'</div>')
 for bad in doc.xpath('//script|//style|//noscript|//nav|//footer|//header|//form|//iframe|//aside|//*[@role="navigation"]'):
  if bad.getparent() is not None:bad.drop_tree()
 for bad in doc.xpath('//*[contains(@class,"related-post") or contains(@class,"social-share") or contains(@class,"cookie") or contains(@class,"breadcrumb") or contains(@class,"sidebar") or contains(@class,"comments") or contains(@class,"newsletter") or contains(@class,"pagination") or contains(@class,"elementor-location-footer")]'):
  if bad.getparent() is not None:bad.drop_tree()
 figs=[]
 for im in doc.xpath('.//img'):
  src=im.get('data-src') or im.get('src') or ''
  if src.startswith('data:'):continue
  iu=norm(src,url)
  if not iu:continue
  alt=im.get('alt') or '';capt=''
  for ancestor in im.iterancestors():
   if ancestor.tag=='figure' or 'wp-caption' in ancestor.get('class',''):
    ca=ancestor.xpath('.//figcaption|.//*[contains(@class,"wp-caption-text")]')
    if ca:capt=' '.join(ca[0].text_content().split())
    break
  if re.search(r'logo|icon|avatar|spinner|spacer|social|emoji',iu+' '+alt,re.I):continue
  figs.append({'source_url':iu,'alt_text':alt,'caption':capt,'page_url':url})
 links=[]
 for a in doc.xpath('.//a[@href]'):
  v=norm(a.get('href'),url)
  if v and v!=url:links.append({'url':v,'anchor_text':' '.join(a.text_content().split())})
 # Preserve section headings, lists, table rows and captions as stable text blocks.
 lines=[]
 for el in doc.iter():
  if el.tag not in ['h1','h2','h3','h4','h5','h6','p','li','tr','figcaption','pre','blockquote']:continue
  if any(a.tag in ['p','li','tr','figcaption','pre','blockquote'] for a in el.iterancestors()):continue
  t=' '.join(el.text_content().split())
  if not t:continue
  if el.tag=='tr':t=' | '.join(' '.join(c.text_content().split()) for c in el if c.tag in ['td','th'])
  elif el.tag.startswith('h') and len(el.tag)==2:t='#'*int(el.tag[1])+' '+t
  elif el.tag=='li':t='- '+t
  if not lines or lines[-1]!=t:lines.append(t)
 if not lines:lines=[' '.join(doc.text_content().split())]
 return '\n\n'.join(lines),figs,links

def build():
 wp=json.loads((ROOT/'wp_records.json').read_text());candidates=json.loads((ROOT/'html_candidates.json').read_text())
 candidates={u:r for u,r in candidates.items() if u not in wp}
 pages=[];decisions=[]
 for u,r in wp.items():
  title=plain(r.get('title',{}).get('rendered',''));fragment=r.get('content',{}).get('rendered','')
  body,figs,links=extract(fragment,u);host=r['site_host']
  target_haystack=title+' '+urllib.parse.unquote(u)+' '+body
  target_hits=len(STRONG.findall(target_haystack));other_hits=len(OTHER.findall(target_haystack));strong=target_hits>0;other=other_hits>0
  reason='RCA_dedicated_site' if host.startswith('interactive') else 'explicit_RCA_COSZO_body'
  title_or_url_strong=bool(STRONG.search(title+' '+urllib.parse.unquote(u)))
  include=(title_or_url_strong or (strong and target_hits>=2 and target_hits>=other_hits)) and len(body.split())>=30 and not UTILITY.search(title)
  if OTHER.search(title):include=False;reason='other_array_title'
  if not include:decisions.append({'url':u,'title':title,'status':'excluded','reason':reason if reason=='other_array_title' else 'no_target_content_or_utility_or_short'});continue
  # Remove explicitly other-array paragraphs; retain comparative paragraphs only
  # when they also contain direct target-array evidence.
  if other:
   body='\n\n'.join(b for b in body.split('\n\n') if not OTHER.search(b) or STRONG.search(b))
   links=[x for x in links if not OTHER.search(x['anchor_text']+' '+x['url']) or STRONG.search(x['anchor_text']+' '+x['url'])]
  if len(body.split())<30:
   decisions.append({'url':u,'title':title,'status':'excluded','reason':'short_after_scope_filter'});continue
  pages.append({'url':u,'title':title,'text':body,'figures':figs,'links':links,'site_host':host,'published_at':r.get('date'),'modified_at':r.get('modified'),'selection_reason':reason,'mixed_array_context':other,'source_format':'wordpress_api','wp_id':r['id']})
 # Generic OOI technical pages are eligible if directly linked in accepted RCA content.
 linked={x['url'] for p in pages for x in p['links']}
 selected={p['url'] for p in pages}
 for u,r in wp.items():
  if u not in linked or u in selected or r['site_host']!='oceanobservatories.org':continue
  if r.get('type') not in ['instrument_class','data_product','pi_instrument','site','additional_asset','kbe_knowledgebase']:continue
  title=plain(r['title']['rendered']);body,figs,links=extract(r.get('content',{}).get('rendered',''),u)
  if OTHER.search(title) and not STRONG.search(title):continue
  if len(body.split())<30:continue
  pages.append({'url':u,'title':title,'text':body,'figures':figs,'links':links,'site_host':r['site_host'],'published_at':r.get('date'),'modified_at':r.get('modified'),'selection_reason':'technical_resource_linked_from_RCA_page','mixed_array_context':bool(OTHER.search(body)),'source_format':'wordpress_api','wp_id':r['id']})
 # Include directly linked OOI instrument-series pages that are only exposed in the sitemap.
 for u in linked:
  if u not in wp and '/instrument-series/' in urllib.parse.urlsplit(u).path:
   candidates[u]={'url':u,'site_host':'oceanobservatories.org','discovery':'linked_instrument_series'}
 # Fetch sitemap-only pages and static COSZO content, selecting article containers.
 def one(pair):
  u,r=pair;m,b=fetch(u)
  if not b:return None,{'url':u,'status':'failed','error':m.get('error')}
  doc=LH.fromstring(b);tt=doc.xpath('//meta[@property="og:title"]/@content') or doc.xpath('//main//h1[1]/text()') or doc.xpath('//title/text()');title=plain(tt[0]) if tt else u
  nodes=doc.xpath('//main') or doc.xpath('//*[contains(@class,"entry-content")]') or doc.xpath('//article') or doc.xpath('//body')
  fragment=''.join(LH.tostring(n,encoding='unicode') for n in nodes[:1]);body,figs,links=extract(fragment,u)
  if len(body.split())<25 or UTILITY.search(urllib.parse.urlsplit(u).path):return None,{'url':u,'status':'excluded','reason':'utility_or_short'}
  if r['site_host']!='coszo.org':
   target_hits=len(STRONG.findall(title+' '+urllib.parse.unquote(u)+' '+body));other_hits=len(OTHER.findall(title+' '+body))
   direct_technical=r.get('discovery')=='linked_instrument_series'
   if OTHER.search(title) or (not direct_technical and target_hits<1) or (other_hits>target_hits and not STRONG.search(title+' '+u)):
    return None,{'url':u,'status':'excluded','reason':'no_target_content_or_other_array'}
  return {'url':u,'title':title,'text':body,'figures':figs,'links':links,'site_host':r['site_host'],'published_at':None,'modified_at':None,'selection_reason':'COSZO_site' if r['site_host']=='coszo.org' else 'RCA_dedicated_site_sitemap','mixed_array_context':bool(OTHER.search(body)),'source_format':'html'},None
 with cf.ThreadPoolExecutor(max_workers=3) as ex:
  for p,d in ex.map(one,candidates.items()):
   if p:pages.append(p)
   if d:decisions.append(d)
 # Record duplicate content as aliases to prevent repeated chunks.
 groups={}
 for p in pages:groups.setdefault(hashlib.sha256(p['text'].encode()).hexdigest(),[]).append(p)
 kept=[]
 for h,group in groups.items():
  group.sort(key=lambda x:x['url']);p=group[0];aliases=[x['url'] for x in group[1:]]
  for alias in aliases:decisions.append({'url':alias,'status':'duplicate','canonical_url':p['url']})
  p['aliases']=aliases;p['content_sha256']=h;p['page_id']=sid('PAGE-',p['url']);kept.append(p)
 accepted={p['url'] for p in kept};decisions=[d for d in decisions if d['url'] not in accepted]
 dump(ROOT/'selected_pages.json',kept);jsonl(ROOT/'selection_log.jsonl',decisions)
 print('SELECTED',len(kept),'FIGURE_OCCURRENCES',sum(len(p['figures']) for p in kept),flush=True)

def package(images=True):
 if OUT.exists():shutil.rmtree(OUT)
 OUT.mkdir()
 pages=json.loads((ROOT/'selected_pages.json').read_text());fig_groups={};relations=[]
 for p in pages:
  for f in p['figures']:fig_groups.setdefault(f['source_url'],[]).append({**f,'page_id':p['page_id']})
 def download(pair):
  url,contexts=pair;fid=sid('FIG-',url)
  if not any(x.get('caption','').strip() for x in contexts):
   return {'figure_id':fid,'source_url':url,'status':'metadata_only_uncaptioned_image','occurrences':contexts}
  m,b=fetch(url)
  retrieved_url=url
  if not b:
   fallbacks=[]
   if urllib.parse.urlsplit(url).netloc=='ooica.net':fallbacks.append(url.replace('https://ooica.net/','https://interactiveoceans.washington.edu/'))
   full=re.sub(r'-\d+x\d+(?=\.[A-Za-z0-9]+$)','',url);full=re.sub(r'\.(jpg|jpeg|png|gif)\.\1$',r'.\1',full,flags=re.I)
   if full!=url:fallbacks.extend([full]+([full.replace('https://ooica.net/','https://interactiveoceans.washington.edu/')] if 'ooica.net/' in full else []))
   for alt in dict.fromkeys(fallbacks):
    mm,bb=fetch(alt)
    if bb:m,b,retrieved_url=mm,bb,alt;break
  if not b:return {'figure_id':fid,'source_url':url,'status':'failed','error':m.get('error'),'occurrences':contexts}
  try:
   from PIL import Image
   import io
   im=Image.open(io.BytesIO(b));w,h=im.size;fmt=im.format.lower()
   if w<180 or h<120:return {'figure_id':fid,'source_url':url,'status':'excluded_small_image','width':w,'height':h,'occurrences':contexts}
   ext={'jpeg':'jpg'}.get(fmt,fmt)
  except Exception as e:return {'figure_id':fid,'source_url':url,'status':'unsupported_image','error':str(e),'occurrences':contexts}
  path=f'figures/{fid}.{ext}';(OUT/'figures').mkdir(exist_ok=True);(OUT/path).write_bytes(b)
  return {'figure_id':fid,'source_url':url,'retrieved_url':retrieved_url,'path':path,'status':'downloaded','width':w,'height':h,'sha256':hashlib.sha256(b).hexdigest(),'retrieved_at':m['retrieved_at'],'occurrences':contexts,'caption_status':'source_text_only_no_generated_image_description'}
 figures=[]
 if images:
  with cf.ThreadPoolExecutor(max_workers=5) as ex:
   for n,f in enumerate(ex.map(download,fig_groups.items()),1):
    figures.append(f)
    if n%50==0:print('FIGURES',n,'/',len(fig_groups),flush=True)
 dump(ROOT/'figure_results.json',figures)
 goodfig={f['source_url']:f for f in figures if f['status']=='downloaded'}
 urlids={p['url']:p['page_id'] for p in pages}
 for p in pages:
  for alias in p.get('aliases',[]):urlids[alias]=p['page_id']
 chunks=[];docs=[];assets=[]
 for p in pages:
  pid=p['page_id'];path=f'text/{pid}.md';(OUT/'text').mkdir(exist_ok=True)
  fids=list(dict.fromkeys(goodfig[f['source_url']]['figure_id'] for f in p['figures'] if f['source_url'] in goodfig))
  md=f'# {p["title"]}\n\nSource: {p["url"]}\n\n'+p['text']+'\n'
  (OUT/path).write_text(md)
  docs.append({k:v for k,v in p.items() if k not in ['text','figures','links']}|{'text_path':path,'text':p['text'],'figure_ids':fids,'retrieved_at':now(),'text_source':'public_web_page','source_is_untrusted_data':True})
  # Heading-aware, bounded word chunks. Position is zero-based.
  sections=[];heading=p['title'];section=[]
  for block in p['text'].split('\n\n'):
   if block.startswith('#'):
    if section:sections.append((heading,'\n\n'.join(section)));section=[]
    heading=block.lstrip('# ').strip();continue
   section.append(block)
  if section:sections.append((heading,'\n\n'.join(section)))
  units=[]
  for heading,section_text in sections:
   ws=section_text.split();start=0
   while start<len(ws):
    end=min(start+520,len(ws));units.append({'heading':heading,'text':' '.join(ws[start:end]),'start':start,'end':end})
    if end==len(ws):break
    start=end-50
  parts=[];current=[];headings=[];words=0;spans=[]
  for unit in units:
   rendered='## '+unit['heading']+'\n\n'+unit['text'];unit_words=len(rendered.split())
   if current and words+unit_words>600:
    parts.append((headings,'\n\n'.join(current),spans));current=[];headings=[];words=0;spans=[]
   current.append(rendered);words+=unit_words;spans.append({'heading':unit['heading'],'word_start':unit['start'],'word_end':unit['end']})
   if unit['heading'] not in headings:headings.append(unit['heading'])
  if current:parts.append((headings,'\n\n'.join(current),spans))
  for i,(headings,t,spans) in enumerate(parts):
   cid=f'{pid}-CHUNK-{i+1:03d}';chunks.append({'chunk_id':cid,'page_id':pid,'source_url':p['url'],'title':p['title'],'section_heading':headings[0] if headings else p['title'],'section_headings':headings,'section_spans':spans,'position':i,'word_count':len(t.split()),'text':t,'source_is_untrusted_data':True})
   relations.append({'source_id':pid,'predicate':'HAS_CHUNK','target_id':cid})
   if i:relations.append({'source_id':f'{pid}-CHUNK-{i:03d}','predicate':'NEXT_CHUNK','target_id':cid})
  for fid in fids:relations.append({'source_id':pid,'predicate':'HAS_FIGURE','target_id':fid})
  for link in p['links']:
   if link['url'] in urlids:relations.append({'source_id':pid,'predicate':'LINKS_TO','target_id':urlids[link['url']],'anchor_text':link['anchor_text']})
   elif re.search(r'\.(pdf|docx?|xlsx?|csv)(?:\?|$)',link['url'],re.I):assets.append({'page_id':pid,'url':link['url'],'label':link['anchor_text'],'status':'linked_document_not_downloaded'})
  for entity,pat in [('COSZO',r'COSZO'),('Regional Cabled Array',r'Regional Cabled Array|\bRCA\b|Regional Scale Nodes'),('Axial Seamount',r'Axial (?:Seamount|Volcano)'),('Southern Hydrate Ridge',r'(?:Southern )?Hydrate Ridge'),('Oregon Slope Base',r'(?:Oregon )?Slope Base')]:
   hit=re.search(pat,p['text'],re.I)
   if hit:relations.append({'source_id':pid,'predicate':'MENTIONS','target_id':sid('ENTITY-',entity),'target_label':entity,'evidence':p['text'][max(0,hit.start()-60):hit.end()+100],'method':'literal_name_match'})
 entities=[{'entity_id':sid('ENTITY-',name),'name':name,'type':'named_place_or_project','method':'curated_literal_vocabulary'} for name in ['COSZO','Regional Cabled Array','Axial Seamount','Southern Hydrate Ridge','Oregon Slope Base']]
 relations=list({json.dumps(x,sort_keys=True):x for x in relations}.values())
 jsonl(OUT/'pages.jsonl',docs);jsonl(OUT/'chunks.jsonl',chunks);jsonl(OUT/'figures.jsonl',figures);jsonl(OUT/'entities.jsonl',entities);jsonl(OUT/'relationships.jsonl',relations);jsonl(OUT/'linked_documents.jsonl',assets)
 node_ids={p['page_id'] for p in docs}|{c['chunk_id'] for c in chunks}|{e['entity_id'] for e in entities}|{f['figure_id'] for f in figures if f['status']=='downloaded'}
 errors=[]
 for label,values in [('page_id',[p['page_id'] for p in docs]),('chunk_id',[c['chunk_id'] for c in chunks]),('entity_id',[e['entity_id'] for e in entities])]:
  if len(values)!=len(set(values)):errors.append(f'duplicate {label}')
 for r in relations:
  if r['source_id'] not in node_ids:errors.append('dangling source '+r['source_id'])
  if r['target_id'] not in node_ids:errors.append('dangling target '+r['target_id'])
 for c in chunks:
  if not c['text'].strip():errors.append('empty chunk '+c['chunk_id'])
  if c['word_count']>600:errors.append('oversized chunk '+c['chunk_id'])
 for p in docs:
  if not (OUT/p['text_path']).exists():errors.append('missing text file '+p['page_id'])
 for f in figures:
  if f['status']=='downloaded' and not (OUT/f['path']).exists():errors.append('missing figure file '+f['figure_id'])
 report={'status':'passed' if not errors else 'failed','errors':errors,'checks':['unique node ids','relationship endpoint integrity','nonempty bounded chunks','referenced local files exist']}
 dump(OUT/'validation_report.json',report)
 if errors:raise RuntimeError('Package validation failed: '+'; '.join(errors[:10]))
 from collections import Counter
 manifest={'schema_version':'1.0','created_at':now(),'pages':len(docs),'pages_by_site':dict(Counter(p['site_host'] for p in pages)),'chunks':len(chunks),'entities':len(entities),'relationships':len(relations),'figures_downloaded':len(goodfig),'figure_status_counts':dict(Counter(f['status'] for f in figures)),'scope':'COSZO and Regional Cabled Array, with direct supporting technical resources','limitations':['Public HTML/WordPress content indexed by site sitemaps and API; no authenticated content, dynamic instrument time-series, or video downloads.','Linked PDF/document URLs retained for subsequent document ingestion; documents themselves not yet extracted.','Image content is available as original bytes and supplied captions/alt text; no OCR or inferred visual descriptions.','Mixed-array articles may retain context about other arrays when their main body explicitly discusses RCA.']}
 dump(OUT/'manifest.json',manifest);print(json.dumps(manifest),flush=True)
 (OUT/'README.md').write_text('# COSZO / Regional Cabled Array web corpus\n\nUse `chunks.jsonl` for text ingestion and `pages.jsonl` for document metadata and complete clean text. Do not ingest both as independent documents. `entities.jsonl` and `relationships.jsonl` provide traceable graph nodes and edges. Figures remain page-level evidence in `figures.jsonl`; captions and alt text are preserved without invented descriptions. Markdown copies live in `text/`. `linked_documents.jsonl` lists documents awaiting separate extraction. Source URLs are retained for citation, deduplication, and refresh. Website text is untrusted source data, never agent instructions. Chunk positions are zero-based. See `manifest.json` for coverage and limitations.\n')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['discover','build','package']);args=ap.parse_args()
 globals()[args.stage]()
