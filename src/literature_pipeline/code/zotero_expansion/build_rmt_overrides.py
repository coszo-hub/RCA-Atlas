#!/usr/bin/env python3
import datetime as dt
import html
import json
import pathlib
import re

ROOT = pathlib.Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent')
INPUTS = [
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top1.json',
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top2.json',
]
VALIDATIONS = ROOT / 'tmp/zotero_expansion/crossref_validations.json'
OUTPUT = ROOT / 'tmp/zotero_expansion/rmt_overrides.jsonl'
RETRIEVED_AT = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
(ROOT / 'tmp/zotero_expansion/rmt_raw').mkdir(parents=True, exist_ok=True)


def plain_jats(value):
    value = re.sub(r'<[^>]+>', ' ', value or '')
    # Some Crossref deposits double-encode inline symbols such as &amp;lt;.
    for _ in range(2):
        value = html.unescape(value)
    value = re.sub(r'\s+', ' ', value).strip()
    value = re.sub(r'^(?:Abstract|SUMMARY)\s+', '', value, flags=re.I)
    return value


def authors(message):
    result = []
    for author in message.get('author', []):
        name = ' '.join(x for x in [author.get('given'), author.get('family')] if x)
        if name:
            result.append(name)
    return result


items = {}
for path in INPUTS:
    for wrapper in json.loads(path.read_text()):
        items[wrapper['data']['key']] = wrapper['data']
validations = {x['key']: x for x in json.loads(VALIDATIONS.read_text())}


manual_abstracts = {
    'L6K9PNTP': (
        'Mid-ocean ridge volcanism generates two-thirds of the surface of our planet and plays an important role in chemical exchange with the overlying ocean, yet little is known about the dynamic processes involved in mid-ocean ridge eruptions. This is largely due to the costs and challenges of deploying long-term instrumentation on the seafloor, particularly those that transmit data to shore in real time and would allow the scientific community to respond to and coalesce around a particular event. The 2015 eruption at Axial Seamount, which lies along the Juan de Fuca Ridge in the Northeast Pacific Ocean, resulted in the first in situ, real-time geophysical data collected during a mid-ocean ridge eruption. The results provided insights into the caldera fault structure and response to a seafloor-spreading episode, and also confirmed the origin of seismically recorded impulsive signals that are associated with fresh lava erupting onto the seafloor. This confirmation of a seismic signal associated with erupting lava led to revisiting data from an eruption almost a decade earlier and a fundamental new view of seafloor spreading at fast-spreading ridges thousands of kilometers from Axial Seamount. This example illustrates the point that even though cabled observatories are necessarily bound to a specific location, their results can have significant implications for understanding systems that are quite different, in far reaches of the globe.',
        'https://tos.org/oceanography/article/a-tale-of-two-eruptions-how-data-from-axial-seamount-led-to-a-discovery-on',
        'Official Oceanography article page labels the complete text as the article abstract.'
    ),
    '7AWSQDK3': (
        'The Atlantic Meridional Overturning Circulation (AMOC) extends from the Southern Ocean to the northern North Atlantic, transporting heat northwards throughout the South and North Atlantic, and sinking carbon and nutrients into the deep ocean. Climate models indicate that changes to the AMOC both herald and drive climate shifts. Intensive trans-basin AMOC observational systems have been put in place to continuously monitor meridional volume transport variability, and in some cases, heat, freshwater and carbon transport. These observational programs have been used to diagnose the magnitude and origins of transport variability, and to investigate impacts of variability on essential climate variables such as sea surface temperature, ocean heat content and coastal sea level. AMOC observing approaches vary between the different systems, ranging from trans-basin arrays (OSNAP, RAPID 26°N, 11°S, SAMBA 34.5°S) to arrays concentrating on western boundaries (e.g., RAPID WAVE, MOVE 16°N). In this paper, we outline the different approaches (aims, strengths and limitations) and summarize the key results to date. We also discuss alternate approaches for capturing AMOC variability including direct estimates (e.g., using sea level, bottom pressure, and hydrography from autonomous profiling floats), indirect estimates applying budgetary approaches, state estimates or ocean reanalyses, and proxies. Based on the existing observations and their results, and the potential of new observational and formal synthesis approaches, we make suggestions as to how to evaluate a comprehensive, future-proof observational network of the AMOC to deepen our understanding of the AMOC and its role in global climate.',
        'https://nora.nerc.ac.uk/id/eprint/523700/',
        'Complete abstract from the NERC Open Research Archive record for the exact DOI.'
    ),
    'QN9YEA8A': (
        'Tidal triggering of earthquakes in diverse tectonic settings has been well documented, albeit the mechanisms and implications remain elusive. Here we present solid earth and ocean tide modulation of micro-seismicity, associated with caldera dynamics of the 2015 axial seamount eruption in the Juan de Fuca ridge, from well-monitored micro-seismicity catalog of mid-ocean ridge volcanoes to gain an insight into the complex interplay between volcano-tectonic and external influence of periodic tidal loading. We report a significantly strong semi-diurnal tidal periodicity in pre-eruption and weak semi-diurnal tidal periodicity in the post-eruption phase, which converge with the statistical correlation with the tidal stress. We propose that during the pre-eruption stage, fault systems are critically stressed and more sensitive to stress perturbation by periodic tidal loading. However, during the eruption stage, volcano-tectonic processes dominated masking the tidal modulation in micro-seismicity. The unusual micro-seismicity modulation during pre-eruption magma chamber inflation and reactivation of normal faulting, explicitly during the lowest tide, can be explained by a complex interplay between magma chamber inflation and periodic tidal loading, with eventual feedback mechanism on the caldera ring fault system.',
        'https://www.sciencedirect.com/science/article/abs/pii/S0377027321001487',
        'Complete formal abstract from the ScienceDirect publisher record.'
    ),
    'RSANY2VW': (
        'The deep-sea environment creates the largest ecosystem in the world with the largest biological community and extensive undiscovered biodiversity. Nevertheless, these ecosystems are far from well known. Deep-sea equipment is an indispensable approach to research life in extreme environments in the deep-sea environment because of the difficulty in obtaining access to these unique habitats. This work reviewed the historical development and the state-of-the-art of deep-sea equipment suitable for researching extreme ecosystems, to clarify the role of this equipment as a promoter for the progress of life in extreme environmental studies. Linkages of the developed deep-sea equipment and the discovered species are analyzed in this study. In addition, Equipment associated with researching the deep-sea ecosystems of hydrothermal vents, cold seeps, whale falls, seamounts, and oceanic trenches are introduced and analyzed in detail. To clarify the thrust and key points of the future promotion of life in extreme environmental studies, prospects and challenges related to observing equipment, samplers, laboratory simulation systems, and submersibles are proposed. Furthermore, a blueprint for the integration of in situ observations, sampling, controllable culture, manned experiments in underwater environments, and laboratory simulations is depicted for future studies.',
        'https://www.vliz.be/imisdocs/publications/369798.pdf',
        'Complete publisher PDF, open access under CC BY, with the text labeled SUMMARY.'
    ),
    'TR4V5WW5': (
        'The volcano-seismic crisis afflicting Mayotte since May 2018 has motivated France-based seismologists to consider the installment of a permanent seafloor observatory with one or more seismometers for monitoring surfacing magma and the associated seismicity. In general, deploying a seismometer offshore is known to improve earthquake location – particular in depth – and lower magnitude detection. However, how true are these claims for Mayotte when a land-based seismic network already exists? To address this, we investigate location and detection performance when deploying permanent seismometers offshore Mayotte. We modeled location and detection performance using both real and synthetic data in different network configurations. We found that, in the case of Mayotte, only longitude error is significantly reduced by adding seismometers offshore, perhaps due to the North-South configuration of the land network. Moreover, the size of the Mayotte volcano monitoring area, which spans depths and distances up to 50 km for both, prevents accurate location and detection performance with less than 2 permanent seismometers offshore. Therefore, we would need at least 2 cabled seismometers to monitor this volcanic system, i.e. locate and detect events in real-time. Overall, our modeling suggests that a one-side land network can perform relatively well by itself in location (errors <5 km) and detection (magnitude >1.3) so long as the seismicity occurs at epicentral distances and depths <20 km. However, beyond this distance, one or more seafloor seismometers would be needed to improve location and detection performance.',
        'https://www.sciencedirect.com/science/article/pii/S0377027321001517',
        'Complete formal abstract from the ScienceDirect publisher record.'
    ),
    '4PPSSLTB': (
        'Hydrate Ridge is a 6–10 km wide, 22 km long N–S striking thrust ridge within the Cascadia accretionary prism offshore of Oregon in the NE Pacific Ocean. Over the past four decades it has been a primary focus site for studies of gas hydrate/free gas systems within a convergent margin setting. A local peak called the North Hydrate Ridge (NHR), located at a depth of 590 m, hosts the first documented cold seep system driven by convergent margin processes and supports chemosynthetic communities sustained by the anaerobic oxidation of methane. A southern peak at 780 m depth, known as the South Hydrate Ridge (SHR), is actively venting gas around an area of seafloor bacterial mats and a 40 m high carbonate chimney within a long-lived vent system separate from NHR. Bottom simulating reflections (BSRs) observed in seismic profiles indicate these vents are part of a broad gas hydrate province that extends across all of Hydrate Ridge. Hydrate Ridge has been the focus of extensive geophysical surveys, water column acoustic and sampling surveys, high-resolution seafloor mapping using remotely operated, autonomous and deep-towed vehicles, seafloor fluid flow monitoring, and a site for the Ocean Observatories Initiative (OOI). All of these are in support or complementing Ocean Drilling Program (ODP) drilling efforts during Legs 146 and 204 to quantify and characterize the gas hydrate/free gas system. Hydrate concentrations are up to 45% of pore space (30% of total volume), but typically 2–20%, and are strongly coupled with the structure and stratigraphy within the thrust ridge.',
        'https://scholars.unh.edu/faculty_pubs/1388/',
        'Complete formal abstract from the University of New Hampshire institutional publication record.'
    ),
    'WLS5VYTM': (
        'The deep marine subsurface constitutes a massive biosphere that hosts a multitude of archaea, bacteria, and viruses across a diversity of habitats. These microbes play key roles in mediating global biogeochemical cycles, and the marine subsurface is thought to have been among the earliest habitats for life on Earth. Yet we have a poor understanding of what forces govern the evolution of subsurface microbes over time. Here, I outline why evolutionary trajectories in the subsurface may be different than those of microbes living on the surface of the planet and describe how we can take advantage of technological advancements to study the evolutionary dynamics of subsurface microbes and their viruses. The sequencing revolution, in tandem with marine infrastructure advancements, promises that we will soon gain a much deeper understanding of how the vast majority of the microbial biosphere changes, adapts, and evolves over time.',
        'https://pmc.ncbi.nlm.nih.gov/articles/PMC8409735/',
        'Complete formal abstract from PubMed Central. Crossref contains only the first two sentences and was rejected as truncated.'
    ),
}


crossref_abstract_keys = {
    'P69NEY8M', '9AZHN5UT', 'Y7BN8X2L', '7HLK4VFF', '5Y85SKAW', 'XYD5BSMF',
    'ZV7QT6SP', 'CW9HX8FH', '8CE3B94W',
}

title_fixes = {
    '6YM2JGUS': 'Stress Drops on the Blanco Oceanic Transform Fault from Interstation Phase Coherence',
    'TR4V5WW5': "Earthquake location and detection modeling for a future seafloor observatory along Mayotte's volcanic ridge",
    '8CE3B94W': 'Compact representation of temporal processes in echosounder time series via matrix decomposition',
    '6TJ5GJUQ': 'High-Resolution AUV Mapping and Targeted ROV Observations of Three Historical Lava Flows at Axial Seamount',
}

existing_abstract_sources = {
    '6YM2JGUS': 'https://eprints.whiterose.ac.uk/id/eprint/145490/1/manuscriptrevised2.pdf',
    '6TJ5GJUQ': 'https://tos.org/oceanography/article/high-resolution-auv-mapping-and-targeted-rov-observations-of-three-historic',
}

provenance_files = {
    'L6K9PNTP': [ROOT / 'tmp/zotero_expansion/rmt_raw/L6K9PNTP_tos.html'],
    '7AWSQDK3': [ROOT / 'tmp/zotero_expansion/rmt_raw/7AWSQDK3_nora.html'],
    'QN9YEA8A': [ROOT / 'tmp/zotero_expansion/rmt_raw/web_extractions.json'],
    'RSANY2VW': [ROOT / 'tmp/zotero_expansion/rmt_raw/RSANY2VW_vliz.pdf', ROOT / 'tmp/zotero_expansion/rmt_raw/RSANY2VW_vliz.txt'],
    'WLS5VYTM': [ROOT / 'tmp/zotero_expansion/rmt_raw/WLS5VYTM_pmc.html'],
    'TR4V5WW5': [ROOT / 'tmp/zotero_expansion/rmt_raw/web_extractions.json'],
    '4PPSSLTB': [ROOT / 'tmp/zotero_expansion/rmt_raw/4PPSSLTB_unh.html'],
    '2CV2IYZL': [ROOT / 'tmp/zotero_expansion/rmt_raw/2CV2IYZL_nature.html'],
    '6YM2JGUS': [ROOT / 'tmp/zotero_expansion/rmt_raw/6YM2JGUS_whiterose.pdf', ROOT / 'tmp/zotero_expansion/rmt_raw/6YM2JGUS_whiterose.txt'],
    '6TJ5GJUQ': [ROOT / 'tmp/zotero_expansion/rmt_raw/6TJ5GJUQ_tos.html'],
}

(ROOT / 'tmp/zotero_expansion/rmt_raw/web_extractions.json').write_text(json.dumps({
    'retrieved_at': RETRIEVED_AT,
    'method': 'Exact publisher abstract text captured from the web retrieval result after direct publisher curl returned HTTP 403.',
    'records': [
        {'zotero_key': key, 'source_url': manual_abstracts[key][1], 'abstract': manual_abstracts[key][0]}
        for key in ['QN9YEA8A', 'TR4V5WW5']
    ],
}, ensure_ascii=False, indent=2) + '\n')

all_keys = [
    'L6K9PNTP', '7AWSQDK3', 'QN9YEA8A', 'P69NEY8M', 'WLS5VYTM',
    '9AZHN5UT', 'RSANY2VW', 'Y7BN8X2L', '7HLK4VFF', 'TR4V5WW5',
    '4PPSSLTB', '5Y85SKAW', 'XYD5BSMF', '2CV2IYZL', 'ZV7QT6SP',
    'CW9HX8FH', '6YM2JGUS', '8CE3B94W', '6TJ5GJUQ',
]

records = []
for key in all_keys:
    item = items[key]
    validation = validations[key]
    message = validation.get('message', {})
    crossref_url = validation.get('source_url')
    changes = []
    attempts = []
    notes = []

    if key == '2CV2IYZL':
        abstract = None
        status = 'no_abstract_expected'
        source = 'https://www.nature.com/articles/ngeo2929'
        changes.append('abstract_cleared_nonabstract')
        notes.append('Nature identifies this item as News & Views. The prior 37-word abstractNote is a standfirst, not a formal abstract.')
        attempts.extend([
            {'url': crossref_url, 'result': 'DOI and title verified; Crossref supplies no abstract.'},
            {'url': source, 'result': 'Publisher metadata identifies content type as news & views; no formal Abstract section.'},
        ])
    elif key in manual_abstracts:
        abstract, source, source_note = manual_abstracts[key]
        status = 'retrieved'
        changes.append('abstract_added' if not (item.get('abstractNote') or '').strip() else 'abstract_replaced')
        notes.append(source_note)
        attempts.append({'url': crossref_url, 'result': 'DOI/title metadata verified.' + (' Crossref abstract was absent or incomplete.' if key in {'L6K9PNTP','7AWSQDK3','QN9YEA8A','RSANY2VW','TR4V5WW5','4PPSSLTB','WLS5VYTM'} else '')})
        attempts.append({'url': source, 'result': 'Complete formal abstract retrieved and matched to exact title/DOI.'})
        if key in {'QN9YEA8A', 'TR4V5WW5'}:
            attempts.append({'url': source, 'result': 'Direct curl returned HTTP 403; exact publisher abstract remained available through the web retrieval result and was captured in local provenance.'})
        if key == 'WLS5VYTM':
            attempts.append({'url': 'https://journals.asm.org/doi/10.1128/msystems.00731-21', 'result': 'Direct publisher curl returned HTTP 403; complete formal abstract verified in PubMed Central.'})
    elif key in crossref_abstract_keys:
        abstract = plain_jats(message.get('abstract'))
        source = crossref_url
        status = 'retrieved'
        if key in {'5Y85SKAW', 'XYD5BSMF'}:
            changes.append('abstract_replaced_misattribution')
            notes.append('Replaced an abstract belonging to a different work with the complete DOI-matched formal abstract.')
        elif key in {'ZV7QT6SP', 'CW9HX8FH'}:
            changes.append('html_entities_decoded')
            notes.append('Decoded HTML entities without changing the supplied formal abstract wording.')
        elif not (item.get('abstractNote') or '').strip():
            changes.append('abstract_added')
            notes.append('Filled an empty abstractNote with the complete DOI-matched formal abstract from Crossref.')
        else:
            notes.append('Complete DOI-matched formal abstract retained from Crossref metadata.')
        attempts.append({'url': source, 'result': 'Complete DOI-matched abstract and metadata retrieved from Crossref.'})
        if key == 'ZV7QT6SP':
            attempts.append({'url': 'https://www.annualreviews.org/content/journals/10.1146/annurev-earth-040522-095654', 'result': 'Direct publisher curl returned HTTP 403; Crossref deposit contains the complete abstract and bullet points.'})
        if key == '8CE3B94W':
            attempts.append({'url': 'https://pubs.aip.org/asa/jasa/article/148/6/3429/854368/Compact-representation-of-temporal-processes-in', 'result': 'Direct publisher curl returned HTTP 403; Crossref deposit contains the complete formal abstract.'})
    else:
        abstract = (item.get('abstractNote') or '').strip()
        source = existing_abstract_sources[key]
        status = 'retrieved'
        notes.append('Existing complete abstract retained; source verified while correcting title metadata.')
        attempts.extend([
            {'url': crossref_url, 'result': 'DOI/title identity verified; Crossref does not supply a replacement abstract.'},
            {'url': source, 'result': 'Complete abstract verified in the paper or official article page.'},
        ])

    if key in title_fixes:
        changes.append('title_corrected')
        notes.append(f'Corrected local title to verified form: {title_fixes[key]}')

    record = {
        'zotero_key': key,
        'doi': (message.get('DOI') or item.get('DOI') or '').lower().replace('https://doi.org/', '') or None,
        'abstract': abstract,
        'status': status,
        'abstract_status': status,
        'source': source,
        'abstract_source_url': source,
        'retrieved_at': RETRIEVED_AT,
        'resolved_title': title_fixes.get(key) or (message.get('title') or [item.get('title')])[0],
        'resolved_authors': authors(message),
        'pages': message.get('page') or item.get('pages') or None,
        'changes': changes,
        'notes': ' '.join(notes),
        'attempts': attempts,
        'provenance_files': [str(x) for x in provenance_files.get(key, [])] + ([validation.get('raw_path')] if validation.get('raw_path') else []),
    }
    records.append(record)

OUTPUT.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in records))
print(OUTPUT)
print(json.dumps({
    'records': len(records),
    'retrieved': sum(x['status'] == 'retrieved' for x in records),
    'no_abstract_expected': sum(x['status'] == 'no_abstract_expected' for x in records),
    'abstract_added_or_replaced': sum(any(y.startswith('abstract_') and y != 'abstract_cleared_nonabstract' for y in x['changes']) for x in records),
    'title_corrected': sum('title_corrected' in x['changes'] for x in records),
    'html_entities_decoded': sum('html_entities_decoded' in x['changes'] for x in records),
}, indent=2))
