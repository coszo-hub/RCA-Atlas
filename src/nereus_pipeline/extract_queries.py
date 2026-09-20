#!/usr/bin/env python3
"""Refresh the exact allowlisted public GraphQL documents from the Nereus bundle."""
import argparse, hashlib, json, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

OPERATIONS=["AppLayoutQuery","HelmQuery","ReportsPageQuery","EngineeringQuery","PowerCurrentChartInstrumentQuery","PowerCurrentChartNodeQuery","StatusHistoryChartInstrumentQuery","StatusHistoryChartNodeQuery"]

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"RCN-Agent-Nereus/1.0"})
    with urllib.request.urlopen(req,timeout=60) as response: return response.read()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--base-url",default="https://nereus.ooirsn.uw.edu"); args=p.parse_args()
    base=args.base_url.rstrip("/"); html=fetch(base+"/").decode("utf-8")
    match=re.search(r'src=["\']?(/assets/index-[A-Za-z0-9_-]+\.js)',html)
    if not match: raise SystemExit("Nereus index bundle was not found")
    bundle_url=base+match.group(1); raw=fetch(bundle_url); source=raw.decode("utf-8",errors="replace")
    blocks={m.group(1):m.group(2) for m in re.finditer(r'(?:const |,)([A-Za-z_$][A-Za-z0-9_$]*)=je`(.*?)`',source,re.S)}
    def expand(name,seen=()):
        text=blocks[name]
        for dep in re.findall(r'\$\{([A-Za-z_$][A-Za-z0-9_$]*)\}',text):
            text=text.replace('${'+dep+'}',expand(dep,seen+(name,)) if dep in blocks and dep not in seen else '')
        return text.strip()+"\n"
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for operation in OPERATIONS:
        name=next((n for n,text in blocks.items() if re.search(r'\bquery\s+'+operation+r'\b',text)),None)
        if not name: raise SystemExit(f"Operation not found in bundle: {operation}")
        (args.output_dir/f"{operation}.graphql").write_text(expand(name),encoding="utf-8")
    metadata={"source_url":base+"/","graphql_url":base+"/hasura/v1/graphql","frontend_bundle_url":bundle_url,"frontend_bundle_sha256":hashlib.sha256(raw).hexdigest(),"retrieved_at":datetime.now(timezone.utc).isoformat(),"operations":OPERATIONS}
    (args.output_dir/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(metadata,indent=2))

if __name__=="__main__": main()
