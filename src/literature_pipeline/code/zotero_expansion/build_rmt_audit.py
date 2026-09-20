#!/usr/bin/env python3
import collections
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import unicodedata

ROOT = pathlib.Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent')
INPUTS = [
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top1.json',
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top2.json',
]
VALIDATIONS = ROOT / 'tmp/zotero_expansion/crossref_validations.json'
OUTPUT = ROOT / 'tmp/zotero_expansion/rmt_audit.json'


def clean_doi(value):
    value = (value or '').strip()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    return value.rstrip(' .').lower()


def norm_title(value):
    value = html.unescape(value or '').lower()
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', value)


def brief(item):
    return {
        'zotero_key': item.get('key'),
        'source_file': item['_source_file'],
        'item_type': item.get('itemType'),
        'title': item.get('title'),
        'doi': clean_doi(item.get('DOI')) or None,
        'url': item.get('url') or None,
    }


items = []
for path in INPUTS:
    for wrapper in json.loads(path.read_text()):
        item = dict(wrapper.get('data', {}))
        item['_source_file'] = path.name
        items.append(item)

by_key = {item['key']: item for item in items}
validations = {x['key']: x for x in json.loads(VALIDATIONS.read_text())}

empty = []
for item in items:
    if (item.get('abstractNote') or '').strip():
        continue
    record = brief(item)
    validation = validations[item['key']]
    message = validation.get('message', {})
    crossref_abstract = message.get('abstract') or ''
    record.update({
        'severity': 'high' if crossref_abstract else 'medium',
        'crossref_abstract_available': bool(crossref_abstract),
        'crossref_abstract_length': len(crossref_abstract),
        'crossref_source_url': validation.get('source_url'),
        'recommendation': (
            'Retrieve and verify the formal abstract from Crossref/publisher metadata.'
            if crossref_abstract else
            'Check the publisher or an institutional repository; leave empty if no formal abstract exists.'
        ),
    })
    empty.append(record)

wrong_abstracts = []
for key, details in {
    '5Y85SKAW': {
        'severity': 'critical',
        'problem': 'Abstract is copied from a different paper in this collection (DLSBXNKZ, DOI 10.1029/2020EA001269). It describes COVIS hydrothermal discharge rather than location-guided autoencoders.',
        'evidence': 'The abstract text is an exact normalized duplicate of DLSBXNKZ. Crossref supplies a different, title-consistent abstract for DOI 10.1002/rob.21961.',
        'copied_from_zotero_key': 'DLSBXNKZ',
    },
    'XYD5BSMF': {
        'severity': 'critical',
        'problem': 'Abstract is for an Atlantic Meridional Overturning Circulation review, not the cited tsunami-frequency paper.',
        'evidence': 'Crossref supplies a title-consistent abstract about a 32-year Axial Seamount bottom-pressure record for DOI 10.1029/2020GL087372. The current text instead describes AMOC observing and matches the subject of collection item 7AWSQDK3.',
        'likely_copied_from_zotero_key': '7AWSQDK3',
    },
}.items():
    item = by_key[key]
    v = validations[key]
    wrong_abstracts.append({
        **brief(item),
        **details,
        'current_abstract_length': len((item.get('abstractNote') or '').strip()),
        'correct_crossref_abstract_available': bool(v.get('message', {}).get('abstract')),
        'crossref_source_url': v.get('source_url'),
        'recommendation': 'Replace only after checking the Crossref text against the publisher abstract.',
    })

non_abstract = [{
    **brief(by_key['2CV2IYZL']),
    'severity': 'high',
    'problem': 'The 37-word text is a publisher standfirst for a Nature Geoscience News & Views commentary, not a formal abstract.',
    'evidence': {
        'publisher_page': 'https://www.nature.com/articles/ngeo2929',
        'local_publisher_capture': str(ROOT / 'tmp/coszo_products/retrieval_a/raw/COSZO-REF-144_publisher.html'),
        'publisher_content_type': 'news & views',
    },
    'recommendation': 'Clear abstractNote or store the text in a separately labeled description/standfirst field.',
}]

html_artifacts = []
for key, artifact, replacement in [
    ('ZV7QT6SP', '&apos;', "'"),
    ('CW9HX8FH', '&lt;', '<'),
]:
    item = by_key[key]
    html_artifacts.append({
        **brief(item),
        'severity': 'low',
        'field': 'abstractNote',
        'artifact': artifact,
        'replacement': replacement,
        'recommendation': 'Decode the HTML entity while preserving the abstract text.',
    })

title_artifacts = []
for key, severity, problem in [
    ('6YM2JGUS', 'high', 'The complete title is concatenated twice without a separator.'),
    ('TR4V5WW5', 'medium', "The apostrophe in “Mayotte's” is corrupted as “&⋕x27;”."),
    ('8CE3B94W', 'low', 'A trailing “a)” footnote marker is appended to the title.'),
    ('6TJ5GJUQ', 'low', 'Zotero says “Historic Lava Flows”; Crossref says “Historical Lava Flows”.'),
]:
    item = by_key[key]
    v = validations[key]
    title_artifacts.append({
        **brief(item),
        'severity': severity,
        'problem': problem,
        'crossref_title': (v.get('message', {}).get('title') or [None])[0],
        'crossref_source_url': v.get('source_url'),
        'doi_identity_consistent': True,
        'recommendation': 'Normalize the local title to the verified Crossref/publisher title.',
    })

doi_groups = collections.defaultdict(list)
title_groups = collections.defaultdict(list)
abstract_groups = collections.defaultdict(list)
for item in items:
    doi = clean_doi(item.get('DOI'))
    title = norm_title(item.get('title'))
    abstract = re.sub(r'\s+', ' ', html.unescape((item.get('abstractNote') or '').strip())).lower()
    if doi:
        doi_groups[doi].append(item)
    if title:
        title_groups[title].append(item)
    if abstract:
        abstract_groups[hashlib.sha256(abstract.encode()).hexdigest()].append(item)

exact_doi_duplicates = [[brief(x) for x in group] for group in doi_groups.values() if len(group) > 1]
exact_title_duplicates = [[brief(x) for x in group] for group in title_groups.values() if len(group) > 1]
duplicate_abstracts = []
for digest, group in abstract_groups.items():
    if len(group) > 1:
        duplicate_abstracts.append({
            'sha256_normalized_abstract': digest,
            'items': [brief(x) for x in group],
            'assessment': 'Erroneous cross-item abstract duplication; DLSBXNKZ is correct and 5Y85SKAW is misattributed.',
        })

missing_doi = [
    {
        **brief(item),
        'severity': 'informational',
        'assessment': 'No DOI is expected for this University of Washington senior thesis; its institutional repository URL is present.',
    }
    for item in items if not clean_doi(item.get('DOI'))
]

types = collections.Counter(item.get('itemType') for item in items)
present = len(items) - len(empty)
crossref_ok = sum(v.get('status') == 'ok' for v in validations.values())

report = {
    'schema_version': '1.0',
    'generated_at': dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    'collection': 'Regional Cabled Array',
    'collection_key': 'RMTSE2IH',
    'scope': {
        'input_files': [str(x) for x in INPUTS],
        'items_audited': len(items),
        'read_only_audit': True,
    },
    'methodology': [
        'Inspected Zotero abstractNote, title, DOI, item type, and URL fields.',
        'Compared normalized DOI and title keys for exact duplicates and reviewed high-similarity title pairs.',
        'Compared normalized abstract hashes across all records to detect copied abstracts.',
        'Validated every supplied DOI against the Crossref works API and compared returned titles.',
        'Compared Zotero abstracts with available Crossref abstracts to detect gross misattribution; Crossref editorial summaries were not treated as replacements for formal abstracts.',
    ],
    'summary': {
        'item_count': len(items),
        'item_types': dict(sorted(types.items())),
        'abstract_present_count': present,
        'abstract_empty_count': len(empty),
        'empty_with_crossref_abstract_available_count': sum(x['crossref_abstract_available'] for x in empty),
        'wrong_or_misattributed_abstract_count': len(wrong_abstracts),
        'non_abstract_text_in_abstract_field_count': len(non_abstract),
        'placeholder_text_count': 0,
        'html_entity_artifact_count': len(html_artifacts),
        'exact_duplicate_doi_group_count': len(exact_doi_duplicates),
        'exact_duplicate_title_group_count': len(exact_title_duplicates),
        'duplicate_abstract_group_count': len(duplicate_abstracts),
        'doi_present_count': sum(bool(clean_doi(x.get('DOI'))) for x in items),
        'doi_validated_count': crossref_ok,
        'doi_title_identity_mismatch_count': 0,
        'local_title_quality_issue_count': len(title_artifacts),
        'missing_doi_count': len(missing_doi),
    },
    'findings': {
        'wrong_or_misattributed_abstracts': wrong_abstracts,
        'non_abstract_or_standfirst_text': non_abstract,
        'empty_abstracts': empty,
        'html_entities_in_abstracts': html_artifacts,
        'duplicates': {
            'exact_doi_duplicates': exact_doi_duplicates,
            'exact_normalized_title_duplicates': exact_title_duplicates,
            'duplicate_abstracts': duplicate_abstracts,
            'near_duplicate_review': [{
                'assessment': 'not_duplicate',
                'reason': 'Titles are nearly identical but cover different observation intervals and have different verified DOIs.',
                'items': [brief(by_key['U9ERWZJH']), brief(by_key['FPG6IR74'])],
            }],
        },
        'doi_title_consistency': {
            'crossref_validation_file': str(VALIDATIONS),
            'raw_crossref_directory': str(ROOT / 'tmp/zotero_expansion/raw_crossref'),
            'doi_records_checked': crossref_ok,
            'identity_mismatches': [],
            'assessment': 'All 141 supplied DOIs resolve to the expected work title. Four local titles contain transcription or formatting differences that should be cleaned.',
            'local_title_artifacts': title_artifacts,
        },
        'missing_doi': missing_doi,
        'crossref_abstract_comparison_notes': [{
            'zotero_keys': ['IRMCKSVY', 'Y92YQGKU'],
            'assessment': 'Zotero contains paper-specific formal abstracts. Crossref returns the same Science editor summary for both papers; the Crossref text is a lower-quality replacement and should not overwrite the Zotero abstracts.',
        }],
    },
    'recommended_order': [
        'Replace the two misattributed abstracts after publisher verification.',
        'Remove or relabel the Nature News & Views standfirst.',
        'Fill the five empty abstractNote fields for which Crossref already exposes an abstract; investigate the other six at publisher/repository sources.',
        'Repair the four local title artifacts and decode the two HTML entities.',
        'Retain the existing Science paper abstracts rather than Crossref editorial summaries.',
    ],
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(OUTPUT)
print(json.dumps(report['summary'], indent=2))
