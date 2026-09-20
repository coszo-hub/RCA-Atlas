#!/usr/bin/env python3
"""Snapshot Axial focal-mechanism monthly archive pages."""
import argparse
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE="http://axial.ocean.washington.edu"

def main():
 p=argparse.ArgumentParser(); p.add_argument("--index",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--base-url",default=BASE); a=p.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
 text=a.index.read_text(encoding="utf-8",errors="replace")
 links=sorted(set(re.findall(r'href="(FocalMechanisms/months/FM_\d{6}\.html)"',text)))
 for link in links:
  url=urllib.parse.urljoin(a.base_url.rstrip("/")+"/",link); req=urllib.request.Request(url,headers={"User-Agent":"RCN-Agent-Axial/1.0"})
  with urllib.request.urlopen(req,timeout=90) as response: payload=response.read()
  target=a.output_dir/Path(link).name; target.write_bytes(payload); print(f"{target.name}: {len(payload)} bytes")

if __name__=="__main__": main()

