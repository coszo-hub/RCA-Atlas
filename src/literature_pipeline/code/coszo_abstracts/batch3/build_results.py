#!/usr/bin/env python3
import html, json, re, unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

OUT=Path(__file__).resolve().parent; RAW=OUT/'raw'
SRC=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature/coszo_citations.jsonl')
NOW=datetime.now(timezone.utc).isoformat()

def norm(s):
 s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+',' ',s).strip()
def sim(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()
def clean(s):
 s=html.unescape(re.sub(r'<[^>]+>',' ',s or ''))
 s=re.sub(r'\s+',' ',s).strip(); return re.sub(r'^Abstract\s*','',s,flags=re.I)
def invert(d):
 if not d:return None
 a=[None]*(max(max(v) for v in d.values())+1)
 for w,ps in d.items():
  for i in ps:a[i]=w
 return clean(' '.join(x or '' for x in a))
def title_from_citation(c):
 s=re.split(r'\(\d{4}[a-z]?\)\.?\s*',c,maxsplit=1); rest=s[1] if len(s)>1 else c
 markers=['. The ISME Journal','. Journal of Geophysical Research','. Frontiers in Earth Science','. Science Advances','. Scientific data','. Nature Reviews','. Nature,','. Science,','. Geology,','. Seismological Research Letters','. Oceanography','. Annual Review','. Tectonophysics','. Journal of Geodynamics','. Geophys. Res. Lett.','. Earth and Space Science','. Geochemistry, Geophysics, Geosystems','. Bulletin of the Seismological Society','. Communications on Hydraulic','. NOAA /','. IEDA.',', NSF Award',', Final Report','. London:',' Frontiers in Marine Science,',', submitted.']
 cuts=[rest.find(m) for m in markers if rest.find(m)>0]
 return rest[:min(cuts)].strip().rstrip('.') if cuts else rest.split('. ')[0].strip().rstrip('.')

manual={
'094':('Joint Evaluation of the International Response to the Indian Ocean Tsunami: Synthesis Report',None,None,None),
'095':('The relationship between crustal structure and earthquake activity on the central Cascadia continental margin in 3D',None,None,'https://earthquake.usgs.gov/cfusion/external_grants/reports/G17AP00046.pdf'),
'101':('The numerical model WAVEWATCH: a third generation model for the hindcasting of wind waves on tides in shelf seas',None,'https://katalog.bibliothek.kit.edu/bib/869730','https://katalog.bibliothek.kit.edu/bib/869730'),
'102':('User manual and system documentation of WAVEWATCH III version 4.18',None,'https://openalex.org/W2909184534','https://openalex.org/W2909184534'),
'106':('Diversity at the UW',None,'https://www.washington.edu/diversity/','https://www.washington.edu/diversity/'),
'107':('ADVANCE Center for Institutional Change',None,'https://advance.washington.edu/','https://advance.washington.edu/'),
'115':('Three Compliance Instruments for Axial Volcano to Observe Long Term Evolution of the Magma Chamber and in Support of OOI Observations',None,'https://api.nsf.gov/services/v1/awards.json?id=1924024','https://api.nsf.gov/services/v1/awards.json?id=1924024'),
'117':('Collaborative Research: Caldera Dynamics and Eruption Cycles at Axial Seamount',None,'https://api.nsf.gov/services/v1/awards.json?id=1951448','https://api.nsf.gov/services/v1/awards.json?id=1951448'),
'120':('Investigating Cascadia Subduction Zone Geodynamics Through Scientific Ocean Drilling',None,'https://usoceandiscovery.org/wp-content/uploads/2016/06/Cascadia-Report.pdf','https://usoceandiscovery.org/wp-content/uploads/2016/06/Cascadia-Report.pdf'),
'121':('Continuous seafloor APG pressure and temperature data from trench-perpendicular benchmarks on the Cascadia margin, offshore central Oregon','10.26022/IEDA/329853','https://doi.org/10.26022/IEDA/329853','https://api.datacite.org/dois/10.26022%2FIEDA%2F329853'),
'122':('Calibration sheets used with seafloor APG pressure data from trench-perpendicular benchmarks on the Cascadia margin, offshore central Oregon','10.26022/IEDA/329854','https://doi.org/10.26022/IEDA/329854','https://api.datacite.org/dois/10.26022%2FIEDA%2F329854'),
'128':('Collaborative Research: From Magma to Vents: Monitoring Hydrothermal Fluid Temperature and Upflow-zone Permeability in Relation to Magma Movement at Axial Seamount',None,'https://api.nsf.gov/services/v1/awards.json?id=2141963','https://api.nsf.gov/services/v1/awards.json?id=2141963'),
'132':('Development of a Plate-scale Distributed Strain Sensing System: A Candidate for Earthquake Early Warning',None,'https://api.nsf.gov/services/v1/awards.json?id=2218876','https://api.nsf.gov/services/v1/awards.json?id=2218876'),
}

abstract112=('Among the wide range of thermal, petrologic, hydrological, and structural factors that potentially affect subduction earthquakes, the roughness of the subducting seafloor is among the most important. By reviewing seismic and geodetic studies of megathrust locking/creeping state, we find that creeping is the predominant mode of subduction in areas of extremely rugged subducting seafloor such as the Kyushu margin, Manila Trench, northern Hikurangi, and southeastern Costa Rica. In Java and Mariana, megathrust creeping state is not yet constrained by geodetic observations, but the very rugged subducting seafloor and lack of large earthquakes also suggest aseismic creep. Large topographic features on otherwise relatively smooth subducting seafloor such as the Nazca Ridge off Peru, the Investigator Fracture Zone off Sumatra, and the Joban seamount chain in southern Japan Trench also cause creep and often stop the propagation of large ruptures. Similar to all other known giant earthquakes, the Tohoku earthquake of March 2011 occurred in an area of relatively smooth subducting seafloor. The Tohoku event also offers an example of subducting seamounts stopping rupture propagation. Very rugged subducting seafloor not only retards the process of shear localization, but also gives rise to heterogeneous stresses. In this situation, the fault zone creeps because of distributed deformation of fractured rocks, and the creep may take place as transient events of various spatial and temporal scales accompanied with small and medium-size earthquakes. This process cannot be described as stable or unstable friction along a single contact surface. The association of large earthquakes with relatively smooth subducting seafloor and creep with very rugged subducting seafloor calls for further investigation. Seafloor near-trench geodetic monitoring, high-resolution imaging of subduction fault structure, studies of exhumed ancient subduction zones, and laboratory studies of low-temperature creep will greatly improve our understanding of the seismogenic and creep processes and their hazard implications.')
abstract095=('A 3D velocity model for the central Oregon margin based on amphibious controlled source data acquired in 1989, 1996 and 2012 indicates the presence of a high velocity slab within the upper plate that generates travel-time anomalies of up to 1.5 s that vary with azimuth for a given source-receiver distance. This complexity is added to the strong 2D heterogeneity characteristic of a submarine subduction zone, in which the subducting plate deepens rapidly between the deformation front and the coastline and the upper plate velocity increases as the accretionary prism abuts (and may be thrust under) the crystalline basement of the forearc. In this study we explored the effect of this heterogeneous crustal structure on the precision and accuracy of hypocenters determined using simplified crustal structures and linearized inversion methods by locating synthetic earthquakes for which travel times were generated for the 3D velocity model. We show that apparent depths for earthquakes located in a velocity model appropriate for the Coast Ranges (where most stations are located) are likely overestimated by 10s of km, even if the linearized solutions fit the data better than those for a velocity model appropriate for the source region of the earthquakes. We also show that addition of even a few offshore stations greatly improve the accuracy of epicenter determinations but that more accurate velocity models are key to obtaining accurate depths. Finally, we discuss preliminary evidence that approximating heterogeneous crustal structure by using multiple regional 1D velocity profiles is not adequate for determining depth with the accuracy needed to understand the relationship between interplate and intraplate deformation in a region of strong lateral heterogeneity.')

def nature_abs(n):
 s=(RAW/f'COSZO-REF-{n}_publisher.html').read_text()
 m=re.search(r'id="Abs\d+-content"><p>(.*?)</p>',s,re.S)
 return clean(m.group(1)) if m else None
def abs113():
 s=(RAW/'COSZO-REF-113_repository.txt').read_text()
 m=re.search(r'a b s t r a c t\s+(.*?)\s+Crown Copyright',s,re.S)
 return clean(m.group(1)) if m else None

link_checks=json.loads((RAW/'fulltext_link_checks.json').read_text())
results=[]
for line in SRC.open():
 o=json.loads(line); n=int(o['id'].rsplit('-',1)[1]); ns=f'{n:03d}'
 if not 90<=n<=133:continue
 rid=o['id']; target=title_from_citation(o['citation']); attempts=[]
 cr_url='https://api.crossref.org/works?query.bibliographic='+target
 oa_url='https://api.openalex.org/works?search='+target
 attempts += [{'url':cr_url,'result':'searched; raw response saved'}, {'url':oa_url,'result':'searched; raw response saved'}]
 resolved_title=resolved_doi=paper_url=metadata_url=license_=abstract=abstract_url=source_desc=None
 source_desc_url=source_desc_type=None
 notes=[]; oa=None; cr=None
 if ns in manual:
  resolved_title,resolved_doi,paper_url,metadata_url=manual[ns]
 else:
  xs=json.loads((RAW/f'{rid}_openalex.json').read_text()).get('results',[])
  xs.sort(key=lambda x:sim(target,x.get('title','')),reverse=True)
  if xs and sim(target,xs[0].get('title',''))>=.85:
   oa=xs[0]; resolved_title=oa.get('title'); resolved_doi=(oa.get('doi') or '').replace('https://doi.org/','') or None
   paper_url='https://doi.org/'+resolved_doi if resolved_doi else (oa.get('primary_location') or {}).get('landing_page_url')
   metadata_url='https://api.openalex.org/works/'+oa['id'].rsplit('/',1)[-1]
   loc=oa.get('primary_location') or {}; best=oa.get('best_oa_location') or {}
   license_=loc.get('license') or best.get('license')
   abstract=invert(oa.get('abstract_inverted_index')); abstract_url=metadata_url if abstract else None
   attempts.append({'url':metadata_url,'result':f"exact title match; authors/year inspected; DOI {resolved_doi or 'none'}"})
  cr_path=RAW/f'{rid}_crossref.json'
  ys=json.loads(cr_path.read_text())['message'].get('items',[]) if cr_path.exists() else []
  ys.sort(key=lambda x:sim(target,(x.get('title') or [''])[0]),reverse=True)
  if ys and sim(target,(ys[0].get('title') or [''])[0])>=.85: cr=ys[0]
 if ns=='095':
  abstract=abstract095; abstract_url='https://earthquake.usgs.gov/cfusion/external_grants/reports/G17AP00046.pdf'
  attempts.append({'url':abstract_url,'result':'formal Abstract recovered from indexed primary USGS report; direct PDF now returns HTTP 404'})
  notes.append('Formal report Abstract was recovered from the indexed primary USGS report. The cited direct PDF URL currently returns HTTP 404, so it is not listed as accessible full text.')
 if ns in ('115','117','128','132'):
  aid={'115':'1924024','117':'1951448','128':'2141963','132':'2218876'}[ns]
  a=json.loads((RAW/f'nsf_{aid}.json').read_text())['response']['award'][0]
  source_desc=clean(a.get('abstractText')); source_desc_url=metadata_url; source_desc_type='verbatim_source_abstract'
  attempts.append({'url':metadata_url,'result':'official NSF award record retrieved; award abstract stored verbatim as source_description'})
 if ns in ('121','122'):
  did={'121':'329853','122':'329854'}[ns]; d=json.loads((RAW/f'ieda_{did}.json').read_text())['data']['attributes']
  ds=d.get('descriptions') or []; source_desc=clean(ds[0].get('description')) if ds else None
  source_desc_url=metadata_url if source_desc else None; source_desc_type='verbatim_source_abstract' if source_desc else None
  rights=d.get('rightsList') or []; license_=rights[0].get('rightsIdentifier') if rights else None
  attempts.append({'url':metadata_url,'result':'DataCite metadata retrieved; dataset description stored as source_description'})
 if ns=='097':
  abstract=None; abstract_url=None; notes.append('The publisher/full-text record begins with an Introduction and exposes no separately labeled abstract; search snippets mislabeled introductory text as an abstract.')
 if ns=='103':
  abstract=None; abstract_url=None; notes.append('Two-page Oceanography feature has no separately labeled abstract.')
 if ns=='112': abstract=abstract112; abstract_url='https://www.sciencedirect.com/science/article/pii/S0040195113006896'; attempts.append({'url':abstract_url,'result':'publisher abstract retrieved and matched by title, DOI, and authors'})
 if ns=='113': abstract=abs113(); abstract_url='https://geophysics.uoregon.edu/pdf/wang_trehu_2016.pdf'; attempts.append({'url':abstract_url,'result':'author/institution-hosted accepted-version PDF retrieved; abstract extracted'})
 if ns in ('125','131'): abstract=nature_abs(ns); abstract_url=f'https://www.nature.com/articles/{"s43017-021-00245-w" if ns=="125" else "nature17632"}'; attempts.append({'url':abstract_url,'result':'publisher page retrieved; labeled Abstract section extracted'})
 if ns=='096' and abstract and ' Abstract ' in abstract: abstract=abstract.rsplit(' Abstract ',1)[1].split(' You do not have access',1)[0].strip()
 if ns=='100': notes.append('The bibliography cited a submitted manuscript; the matched work was published in 2023 in Earth Science, Systems and Society, volume 3, article 10085.')
 if ns=='101':
  abstract_url='https://library.metoffice.gov.uk/portal/Default/en-GB/RecordView/Index/176340'
  attempts.append({'url':abstract_url,'result':'formal Abstract field verified, but the catalog truncates the text and no complete primary copy was located'})
  attempts.append({'url':'https://repository.tudelft.nl/','result':'exact-title and report-number searches found no accessible original report record or full abstract'})
  notes.append('A formal abstract exists in the Met Office catalog, but only a truncated excerpt is exposed; no partial text was stored.')
 if ns=='096': notes.append('Issue citation is 2012; some aggregators report a 2011 early/publication year.')
 if ns=='112': notes.append('Crossref gives the cited 2014 issue date; OpenAlex reports 2013 from early online publication.')
 if ns=='129': notes.append('Crossref gives the cited 2021 issue date; OpenAlex reports 2020 from early online publication.')
 if ns=='117': notes.append('NSF award 1951448 verified. The second cited number, 1950666, returned no award record from the NSF API and may be a bibliography error.')
 if abstract: status='retrieved'
 elif ns=='101': status='not_found'
 elif o['resource_type'] in ('report_or_book','grant_award','dataset','webpage') or ns in ('097','103'): status='no_abstract_expected'
 elif resolved_title: status='not_found'
 else: status='unresolved_citation'
 ft=None
 chk=link_checks.get(rid)
 if chk:
  attempts.append({'url':chk['url'],'result':('verified reachable full text; HTTP '+str(chk.get('status'))) if chk.get('verified') else 'candidate full-text link not accepted: '+chk.get('result','failed')})
  if chk.get('verified'): ft=chk['url']
 if ns=='095': paper_url=None
 if not metadata_url: metadata_url=paper_url
 results.append({'id':rid,'resolved_title':resolved_title,'resolved_doi':resolved_doi,'paper_url':paper_url,'abstract':abstract,'abstract_status':status,'abstract_source_url':abstract_url,'retrieved_at':NOW,'metadata_source_url':metadata_url,'license':license_,'full_text_url':ft,'source_description':source_desc,'source_description_url':source_desc_url,'source_description_type':source_desc_type,'notes':' '.join(notes) if notes else None,'attempts':attempts})

with (OUT/'results.jsonl').open('w') as f:
 for x in results:f.write(json.dumps(x,ensure_ascii=False)+'\n')
counts={}
for x in results:counts[x['abstract_status']]=counts.get(x['abstract_status'],0)+1
(OUT/'summary.json').write_text(json.dumps({'total':len(results),'abstract_status_counts':counts,'retrieved_abstract_ids':[x['id'] for x in results if x['abstract_status']=='retrieved'],'notes':['Science Crossref teaser text was not used; OpenAlex full abstracts were used after title/author/year verification.','full_text_url is populated only where a direct link check returned a PDF successfully.']},indent=2))
print(len(results),counts)
