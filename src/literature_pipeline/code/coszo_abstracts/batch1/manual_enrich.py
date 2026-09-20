#!/usr/bin/env python3
import html, json, re, subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT=Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent/tmp/coszo_abstracts/batch1')
RAW=OUT/'raw'
rows={r['id']:r for r in map(json.loads,(OUT/'results.jsonl').read_text().splitlines())}

def clean(fragment):
    fragment=re.sub(r'<sup.*?</sup>','',fragment,flags=re.S)
    fragment=re.sub(r'<[^>]+>',' ',fragment)
    return ' '.join(html.unescape(fragment).split())
def meta(path,name='description'):
    s=Path(path).read_text(errors='ignore')
    m=re.search(r'<meta name="'+re.escape(name)+r'" content="(.*?)"\s*/?>',s,re.S|re.I)
    return clean(m.group(1)) if m else None
def note(r,text): r['notes']=((r.get('notes') or '')+' '+text).strip()
def retrieved(r,abstract,source):
    r['abstract']=abstract; r['abstract_status']='retrieved'; r['abstract_source_url']=source
    r['retrieved_at']=datetime.now(timezone.utc).isoformat()
    r.setdefault('attempts',[]).append({'url':source,'result':'complete abstract retrieved and manually checked against exact title and authors'})

# Nature full abstracts, explicitly labeled Abstract in publisher HTML.
for n,url in [(15,'https://www.nature.com/articles/ngeo1464'),(34,'https://www.nature.com/articles/s43017-022-00364-y')]:
    r=rows[f'COSZO-REF-{n:03d}']; s=(RAW/f'COSZO-REF-{n:03d}_nature.html').read_text(errors='ignore')
    m=re.search(r'<section[^>]+data-title="Abstract".*?<div[^>]+id="Abs\d+-content">(.*?)</div>\s*</div>\s*</section>',s,re.S)
    if m:
        retrieved(r,clean(m.group(1)),url); r['metadata_source_url']=url
        note(r,'Publisher page labels this text as the article Abstract.')

# Exact published abstract from the first page of a verified author-hosted article PDF.
r=rows['COSZO-REF-022']
t=subprocess.check_output(['pdftotext','-f','1','-l','1','-nopgbrk',str(RAW/'COSZO-REF-022_fulltext.pdf'),'-'],text=True)
m=re.search(r'a b s t r a c t\s*(.*?)\s*©\s*2014',t,re.S)
if m:
    a=' '.join(m.group(1).replace('ﬁ','fi').replace('ﬂ','fl').split())
    retrieved(r,a,'https://earthweb.ess.washington.edu/gomberg/SZOSeminar/Papers/DavisetalEPSL15.pdf')
    r['full_text_url']='https://earthweb.ess.washington.edu/gomberg/SZOSeminar/Papers/DavisetalEPSL15.pdf'
    note(r,'Abstract transcribed from the explicitly labeled abstract on page 1 of the verified article PDF.')

# University of Washington dissertation record; citation title is imprecise, repository title is authoritative.
r=rows['COSZO-REF-031']; a=meta(RAW/'COSZO-REF-031_uw.html')
r.update(resolved_title='Circulation-Informed Seafloor Geodetic Techniques for Understanding Plate Boundary Processes',resolved_doi=None,paper_url='http://hdl.handle.net/1773/49950',metadata_source_url='https://digital.lib.washington.edu/researchworks/items/b95fa219-8bf7-400e-b0cf-76cc581f8a08/full',license='CC BY-NC',full_text_url='https://digital.lib.washington.edu/bitstreams/8f3c8cbe-5791-4939-b866-607ba7a97386/download')
retrieved(r,a,'https://digital.lib.washington.edu/researchworks/items/b95fa219-8bf7-400e-b0cf-76cc581f8a08/full')
note(r,'Repository title differs from the cited title; author, year, degree, institution, subject, and 235-page dissertation identity verify the match.')

# Complete article abstract recovered from the indexed published article/PDF.
r=rows['COSZO-REF-036']
a=('Historically Black Colleges and Universities (HBCUs) attract, retain and award science degrees to African Americans at a higher rate than majority institutions. Because they offer life-changing and career-orienting experiences for students, field stations and marine laboratories are well positioned to help increase the number of students opting for science, technology, engineering and mathematics (STEM) careers and ocean science and education careers, in particular. Two kinds of partnerships have developed between Savannah State University (SSU), an HBCU, and marine laboratories as a result of federal funding: a Research Experiences for Undergraduates (REU) program between SSU and the Harbor Branch Oceanographic Institution, and an internship/graduate program between SSU and the Skidaway Institute of Oceanography. These collaborations and other funded projects since 1998 have resulted in an increase in the percent of graduates from SSU\'s Bachelor of Science in Marine Science degree who had a significant research experience from 25% before 1999 to 66% percent afterwards and an increase in the number graduating with honors from 30% prior to 1999 to 41% after 1999. The growth and productivity of marine science degree and research experience programs at Savannah State University illustrates how collaboration and partnerships can be an effective way to increase access and eventually pay big dividends by increasing diversity in geoscience professions.')
r.update(resolved_title='Building a Diverse and Innovative Ocean Workforce through Collaboration and Partnerships that Integrate Research and Education: HBCUs and Marine Laboratories',resolved_doi='10.5408/1089-9995-55.6.531',paper_url='https://doi.org/10.5408/1089-9995-55.6.531',metadata_source_url='https://api.crossref.org/works/10.5408/1089-9995-55.6.531')
src='https://www.researchgate.net/publication/290947004_Building_a_Diverse_and_Innovative_Ocean_Workforce_through_Collaboration_and_Partnerships_that_Integrate_Research_and_Education_HBCUs_and_Marine_Laboratories'
retrieved(r,a,src); note(r,'Complete labeled abstract manually checked against the indexed scan; publisher page returned HTTP 403.')
(RAW/'COSZO-REF-036_manual_source_record.json').write_text(json.dumps({'source_url':src,'title':r['resolved_title'],'doi':r['resolved_doi'],'abstract':a,'retrieval_note':'Search-indexed text of the published article scan; publisher page returned HTTP 403.'},ensure_ascii=False,indent=2))

# Springer chapter JSON-LD contains its full description and exact author/title metadata.
r=rows['COSZO-REF-037']; s=(RAW/'COSZO-REF-037_springer.html').read_text(errors='ignore')
descs=[]
for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>',s,re.S):
    try:
        x=json.loads(m.group(1));
        if x.get('headline','').startswith('Institutional Barriers'): descs.append(x.get('description'))
    except: pass
if descs and descs[0]:
    retrieved(r,descs[0],'https://link.springer.com/referenceworkentry/10.1007/978-3-030-31365-4_4')
    r['metadata_source_url']='https://link.springer.com/referenceworkentry/10.1007/978-3-030-31365-4_4'
    note(r,'Springer page provides the chapter description in ScholarlyArticle JSON-LD; treated as the chapter abstract.')

# NOAA institutional page reproduces the complete Oceanography article abstract.
r=rows['COSZO-REF-041']; s=(RAW/'COSZO-REF-041_noaa.html').read_text(errors='ignore')
m=re.search(r'property="schema:articleBody content:encoded"><p>(.*?)</p>',s,re.S)
if m:
    retrieved(r,clean(m.group(1)),'https://www.pmel.noaa.gov/eoi/featured-publication/noaa-vents-program-1983-2013-thirty-years-ocean-exploration-and-research')
    r['full_text_url']='https://tos.org/oceanography/assets/docs/28-1_hammond.pdf'; r['license']='CC BY 4.0'
    note(r,'NOAA institutional publication page reproduces the complete article abstract; Oceanography PDF link is verified by publisher metadata.')

# Caltech institutional repository abstract and attached published PDF.
r=rows['COSZO-REF-043']; a=meta(RAW/'COSZO-REF-043_caltech.html')
r.update(resolved_title='Seismic potential associated with subduction in the northwestern United States',resolved_doi='10.1785/BSSA0740030933',paper_url='https://doi.org/10.1785/BSSA0740030933',metadata_source_url='https://authors.library.caltech.edu/records/ahz5c-cnv07',license=None,full_text_url='https://authors.library.caltech.edu/records/ahz5c-cnv07/files/933.full.pdf')
retrieved(r,a,'https://authors.library.caltech.edu/records/ahz5c-cnv07')
note(r,'Corrected an automated fuzzy match to the 1985 reply; exact 1984 paper verified by title, both authors, journal, volume, issue, and pages in CaltechAUTHORS.')

# Conference papers: verify exact landing records even when no abstract can be retrieved.
r=rows['COSZO-REF-012']; r.update(resolved_title='Vertical deformation of the Axial Seamount Summit from Repeated 1-m scale bathymetry surveys using AUVs',resolved_doi=None,paper_url='https://ui.adsabs.harvard.edu/abs/2020AGUFMV040.0017C/abstract',metadata_source_url='https://ui.adsabs.harvard.edu/abs/2020AGUFMV040.0017C/abstract',abstract=None,abstract_status='not_found',abstract_source_url=None)
note(r,'Exact AGU abstract bibcode inferred and cross-checked against author/title/year/session citations; ADS blocked automated abstract retrieval (HTTP 405/429).')
r.setdefault('attempts',[]).append({'url':r['paper_url'],'result':'exact conference landing record identified; abstract endpoint blocked automated access'})
r=rows['COSZO-REF-024']; r.update(resolved_title='Horizontal deformation rates near the Cascadia subduction zone trench revealed by offshore GNSS-Acoustic time series',resolved_doi=None,paper_url='https://agu.confex.com/agu/fm22/meetingapp.cgi/Paper/1193941',metadata_source_url='https://agu.confex.com/agu/fm22/meetingapp.cgi/Paper/1193941',abstract=None,abstract_status='not_found',abstract_source_url=None)
note(r,'Exact AGU meeting record verified through institutional bibliography. A later peer-reviewed version is DOI 10.1016/j.epsl.2025.119463; its abstract was not substituted for the 2022 conference abstract.')
r.setdefault('attempts',[]).append({'url':r['paper_url'],'result':'exact AGU meeting record identified; abstract text not retrievable'})

# Nature Comment has only an unlabeled standfirst; TOS sidebar has body text, not an Article Abstract.
r=rows['COSZO-REF-010']; r.update(resolved_title='No progress on diversity in 40 years',resolved_doi='10.1038/s41561-018-0116-6',paper_url='https://doi.org/10.1038/s41561-018-0116-6',metadata_source_url='https://www.nature.com/articles/s41561-018-0116-6',abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None,source_description=meta(RAW/'COSZO-REF-010_nature.html'))
note(r,'Nature classifies this as Comment and exposes a short unlabeled standfirst, retained as source_description rather than abstract.')
r=rows['COSZO-REF-044']; s=(RAW/'COSZO-REF-044_tos.html').read_text(errors='ignore'); m=re.search(r'<p>(Ocean Networks Canada \(ONC;.*?)</p>',s,re.S)
r.update(abstract=None,abstract_status='no_abstract_expected',abstract_source_url=None,source_description=clean(m.group(1)) if m else None,full_text_url='https://tos.org/oceanography/assets/docs/27-2_heesemann.pdf',license='CC BY')
note(r,'Oceanography labels this item Sidebar and provides no Article Abstract section; opening body paragraph retained as source_description.')

# Automated exact-title search selected the preprint DOI for the later journal article; retain published identity and note the version relation.
r=rows['COSZO-REF-018']; r['resolved_doi']='10.1029/2022JB025553'; r['paper_url']='https://doi.org/10.1029/2022JB025553'
note(r,'Corrected resolved DOI to the published journal version; DOI 10.31223/X5RQ0G is the matching EarthArXiv preprint.')

(OUT/'results.jsonl').write_text('\n'.join(json.dumps(rows[k],ensure_ascii=False) for k in sorted(rows))+'\n')
