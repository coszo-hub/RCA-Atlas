#!/usr/bin/env python3
"""Download the public Axial catalog sources used by build_axial_corpus.py."""
import argparse
import urllib.request
from pathlib import Path

BASE="http://axial.ocean.washington.edu"
FILES={
 "index.html":"/", "hypo71.dat":"/hypo71.dat", "hypo71-index.html":"/hypo71.html", "ph2dt-index.html":"/ph2dt.html",
 "axial_focal_mechanisms.csv":"/FocalMechanisms/catalog/axial_focal_mechanisms.csv",
 "FM_ML_2022_2025.txt":"/FocalMechanisms/catalog/FM_ML_2022_2025.txt", "FM_XC_2015_2021.txt":"/FocalMechanisms/catalog/FM_XC_2015_2021.txt",
 "focal-mechanisms.html":"/Focal%20Mechanisms.html", "rsam.html":"/rsam.html", "map1-index.html":"/map1.html", "map2-index.html":"/map2.html",
}

def main():
 p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--base-url",default=BASE); a=p.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
 for name,path in FILES.items():
  req=urllib.request.Request(a.base_url.rstrip("/")+path,headers={"User-Agent":"RCN-Agent-Axial/1.0"})
  with urllib.request.urlopen(req,timeout=120) as response, (a.output_dir/name).open("wb") as out: out.write(response.read())
  print(name)

if __name__=="__main__": main()

