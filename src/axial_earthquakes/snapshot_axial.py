#!/usr/bin/env python3
"""Download the public Axial catalog sources used by build_axial_corpus.py.

The site's real-time focal-mechanism CSV holds only about the last two months (on 12 November 2026, 8 September
onward), and the 2015-2021 and 2022-2025 catalogs it links answer 404 since October 2026. With --previous (an
earlier snapshot, such as source_material/AxialEarthquakes/source_snapshot), the CSV keeps the earlier snapshot's
rows too (the newer row wins for an event in both), and a file the site no longer serves is kept from it.
"""
import argparse
import csv
import gzip
import io
import urllib.error
import urllib.request
from pathlib import Path

BASE="http://axial.ocean.washington.edu"
FILES={
 "index.html":"/", "hypo71.dat":"/hypo71.dat", "hypo71-index.html":"/hypo71.html", "ph2dt-index.html":"/ph2dt.html",
 "axial_focal_mechanisms.csv":"/FocalMechanisms/catalog/axial_focal_mechanisms.csv",
 "FM_ML_2022_2025.txt":"/FocalMechanisms/catalog/FM_ML_2022_2025.txt", "FM_XC_2015_2021.txt":"/FocalMechanisms/catalog/FM_XC_2015_2021.txt",
 "whale-counts.json":"/WhaleTracking/counts.json", "whale-tracking.html":"/WhaleTracking.html",
 "focal-mechanisms.html":"/FocalMechanisms.html", "rsam.html":"/rsam.html", "map1-index.html":"/map1.html", "map2-index.html":"/map2.html",
}

def previous_copy(previous, name):
 """The earlier snapshot's copy of a file (hypo71.dat is stored gzipped there), or None."""
 if not previous: return None
 if (previous/name).exists(): return (previous/name).read_bytes()
 if (previous/(name+".gz")).exists(): return gzip.decompress((previous/(name+".gz")).read_bytes())
 return None

def merge_focal_csv(new, old):
 """The rows of both CSVs, one per EventID (the new one's where both have it), sorted by origin time, under the new
 header. A row is read by its field count: the site added the Quality column in 2026 without adding it to the
 header, so an older file has 20-field rows under a 20-name header and 21-field rows that carry Quality."""
 header = next(csv.reader(io.StringIO(new.decode("utf-8", errors="replace"))))
 rows = {}
 for text in (old, new):
  lines = csv.reader(io.StringIO(text.decode("utf-8", errors="replace")))
  short = [f for f in next(lines) if f != "Quality"]
  for r in lines:
   if len(r) == len(header): rows[r[0]] = dict(zip(header, r))
   elif len(r) == len(short): rows[r[0]] = {**dict(zip(short, r)), "Quality": ""}
 out = io.StringIO(); w = csv.DictWriter(out, fieldnames=header, lineterminator="\n"); w.writeheader()
 w.writerows(sorted(rows.values(), key=lambda r: r["OriginTime"]))
 return out.getvalue().encode()

def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--base-url",default=BASE)
 p.add_argument("--previous",type=Path,help="an earlier snapshot: its focal-mechanism rows are kept, and its copy of any file the site no longer serves")
 a=p.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
 for name,path in FILES.items():
  req=urllib.request.Request(a.base_url.rstrip("/")+path,headers={"User-Agent":"RCN-Agent-Axial/1.0"})
  old=previous_copy(a.previous,name)
  try:
   with urllib.request.urlopen(req,timeout=300) as response: data=response.read()
  except urllib.error.HTTPError as e:
   if e.code!=404 or old is None: raise
   (a.output_dir/name).write_bytes(old); print(f"{name}: 404, kept the previous snapshot's copy"); continue
  if name=="axial_focal_mechanisms.csv" and old is not None:
   data=merge_focal_csv(data,old)
  (a.output_dir/name).write_bytes(data)
  print(name)

if __name__=="__main__": main()
