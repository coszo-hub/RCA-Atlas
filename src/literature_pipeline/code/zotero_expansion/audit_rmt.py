#!/usr/bin/env python3
import concurrent.futures
import hashlib
import html
import json
import pathlib
import re
import time
import threading
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

ROOT = pathlib.Path('/Users/quakehunter/Documents/ChatGPT/RCA Agent')
INPUTS = [
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top1.json',
    ROOT / 'tmp/coszo_products/zotero_RMTSE2IH_top2.json',
]
OUTDIR = ROOT / 'tmp/zotero_expansion'
RAW = OUTDIR / 'raw_crossref'
RAW.mkdir(parents=True, exist_ok=True)
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0


def clean_doi(value):
    value = (value or '').strip()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    return value.rstrip(' .').lower()


def norm_title(value):
    value = html.unescape(value or '').lower()
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def title_scores(a, b):
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0, 0.0
    sa, sb = set(a.split()), set(b.split())
    jaccard = len(sa & sb) / len(sa | sb)
    return SequenceMatcher(None, a, b).ratio(), jaccard


def fetch_crossref(item):
    global LAST_REQUEST
    doi = clean_doi(item.get('DOI'))
    key = item.get('key')
    if not doi:
        return {'key': key, 'doi': None, 'status': 'missing_doi'}
    raw_path = RAW / f'{key}_{hashlib.sha1(doi.encode()).hexdigest()[:10]}.json'
    if raw_path.exists():
        try:
            obj = json.loads(raw_path.read_text())
            msg = obj.get('message', {})
            return {'key': key, 'doi': doi, 'status': 'ok', 'message': msg,
                    'source_url': f'https://api.crossref.org/works/{urllib.parse.quote(doi, safe="")}',
                    'raw_path': str(raw_path)}
        except Exception:
            pass
    url = f'https://api.crossref.org/works/{urllib.parse.quote(doi, safe="")}'
    req = urllib.request.Request(url, headers={'User-Agent': 'COSZO bibliography audit'})
    last_exc = None
    for attempt in range(5):
        try:
            with RATE_LOCK:
                delay = max(0.0, 0.18 - (time.monotonic() - LAST_REQUEST))
                if delay:
                    time.sleep(delay)
                LAST_REQUEST = time.monotonic()
            with urllib.request.urlopen(req, timeout=25) as resp:
                payload = resp.read()
            raw_path.write_bytes(payload)
            obj = json.loads(payload)
            return {'key': key, 'doi': doi, 'status': 'ok', 'message': obj.get('message', {}),
                    'source_url': url, 'raw_path': str(raw_path)}
        except Exception as exc:
            last_exc = exc
            if getattr(exc, 'code', None) == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    return {'key': key, 'doi': doi, 'status': 'error', 'error': f'{type(last_exc).__name__}: {last_exc}',
            'source_url': url}


def main():
    items = []
    for path in INPUTS:
        for wrapped in json.loads(path.read_text()):
            data = dict(wrapped.get('data', {}))
            data['_source_file'] = path.name
            items.append(data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        validations = list(pool.map(fetch_crossref, items))
    (OUTDIR / 'crossref_validations.json').write_text(json.dumps(validations, ensure_ascii=False, indent=2))
    print(json.dumps({
        'items': len(items),
        'ok': sum(x['status'] == 'ok' for x in validations),
        'missing_doi': sum(x['status'] == 'missing_doi' for x in validations),
        'errors': sum(x['status'] == 'error' for x in validations),
    }))


if __name__ == '__main__':
    main()
