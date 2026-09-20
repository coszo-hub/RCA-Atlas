#!/usr/bin/env python3
"""Download current Axial catalog figures while retaining live source URLs."""
import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from axial_agent_tools import DEFAULT_BASE_URL, FIGURES


def main():
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--base-url",default=DEFAULT_BASE_URL); a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True); rows=[]
    retrieved=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    for name,remote in FIGURES.items():
        url=a.base_url.rstrip("/")+"/"+remote; target=a.output_dir/remote
        req=urllib.request.Request(url,headers={"User-Agent":"RCN-Agent-Axial/1.0"})
        with urllib.request.urlopen(req,timeout=90) as response: payload=response.read()
        target.write_bytes(payload)
        rows.append({"name":name,"source_url":url,"local_file":target.name,"retrieved_at_utc":retrieved,"byte_size":len(payload),"mime_type":"image/jpeg"})
        print(f"{name}: {len(payload)} bytes")
    (a.output_dir/"snapshot_manifest.jsonl").write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")
    corpus_manifest=a.output_dir.parent.parent/"manifest.json"
    if corpus_manifest.exists():
        manifest=json.loads(corpus_manifest.read_text(encoding="utf-8")); manifest["figure_products"]=len(FIGURES)+2; manifest["figure_snapshots"]=len(rows)
        corpus_manifest.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")

if __name__=="__main__": main()
