#!/usr/bin/env python3
"""Build an exhaustive metadata inventory of Axial plots, maps, and summary pages."""
import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from axial_agent_tools import DEFAULT_BASE_URL, FIGURES, TOOL_SCHEMAS, parse_focal_csv

BASE=DEFAULT_BASE_URL
ANNUAL_COUNTS={2015:15612,2016:172,2017:354,2018:1665,2019:2073,2020:2247,2021:1098,2022:5,2023:75,2024:1590,2025:1297}

def write_jsonl(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text("".join(json.dumps(x,ensure_ascii=False,allow_nan=False)+"\n" for x in rows),encoding="utf-8")

def links(path,pattern):
 return sorted(set(re.findall(pattern,path.read_text(encoding="utf-8",errors="replace"))))

def main():
 p=argparse.ArgumentParser(); p.add_argument("--source-dir",type=Path,required=True); p.add_argument("--corpus-dir",type=Path,required=True); p.add_argument("--source-archive-dir",type=Path); a=p.parse_args(); source,out=a.source_dir,a.corpus_dir
 built=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
 caldera=links(source/"map1-index.html",r'href="(mapCaldera/dailyCalderaMap_(\d{8})\.jpg)"')
 regional=links(source/"map2-index.html",r'href="(mapRegional/dailyRegionalMap_(\d{8})\.jpg)"')
 assets=[]
 for name,path in FIGURES.items():
  category="rsam" if name.startswith("rsam_") else "focal_mechanism" if name.startswith("focal_") or name.startswith("eruption_focal") else "histogram" if name.startswith("histogram") else "earthquake_map"
  mutable=any(token in name for token in ("1_day","7_day","30_day","1_year","history")) and not name.startswith("focal_mechanisms_20")
  window=next((x for x in ("1_day","7_day","15_day","30_day","60_day","1_year","history") if x in name),None)
  region="caldera" if "caldera" in name else "regional" if "regional" in name or "outer" in name else None
  assets.append({"asset_id":f"axial_{name}","asset_type":category,"name":name,"canonical_url":f"{BASE}/{path}","mime_type":"image/jpeg","is_mutable":mutable,"retrieval_mode":"live_and_snapshot" if mutable else "snapshot","scope":"Axial Seamount","window":window,"region_or_station_group":region})
 for region,rows in (("caldera",caldera),("regional",regional)):
  for href,stamp in rows:
   day=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
   assets.append({"asset_id":f"axial_daily_{region}_{stamp}","asset_type":"daily_earthquake_map","name":f"daily_{region}_map","canonical_url":f"{BASE}/{href}","mime_type":"image/jpeg","date_utc":day,"region":region,"is_mutable":False,"retrieval_mode":"live_on_demand","index_source_url":f"{BASE}/{'map1.html' if region=='caldera' else 'map2.html'}"})
 month_pages=[]
 focal_month_source=(a.source_archive_dir/"focal_months") if a.source_archive_dir else None
 if focal_month_source: focal_month_source.mkdir(parents=True,exist_ok=True)
 for path in sorted(source.glob("FM_20????.html")):
  match=re.search(r"FM_(\d{6})",path.name)
  if not match: continue
  stamp=match.group(1); text=path.read_text(encoding="utf-8",errors="replace"); count=re.search(r"<p>\s*([\d,]+)\s+events\s*</p>",text,re.I)
  month=f"{stamp[:4]}-{stamp[4:]}"; event_count=int(count.group(1).replace(",","")) if count else None
  if focal_month_source: shutil.copy2(path,focal_month_source/path.name)
  month_pages.append({"summary_id":f"axial_focal_month_{stamp}","period_type":"month","period_utc":month,"focal_mechanism_count":event_count,"source_url":f"{BASE}/FocalMechanisms/months/FM_{stamp}.html","local_source":str((focal_month_source/path.name) if focal_month_source else path)})
  assets.append({"asset_id":f"axial_focal_month_page_{stamp}","asset_type":"monthly_focal_summary_page","name":f"focal_month_{month}","canonical_url":f"{BASE}/FocalMechanisms/months/FM_{stamp}.html","mime_type":"text/html","period_utc":month,"event_count":event_count,"is_mutable":month==datetime.now(timezone.utc).strftime('%Y-%m'),"retrieval_mode":"snapshot_and_live"})
 live_focal=parse_focal_csv((source/"axial_focal_mechanisms.csv").read_text(encoding="utf-8",errors="replace"),f"{BASE}/FocalMechanisms/catalog/axial_focal_mechanisms.csv")
 event_bundles=[]
 for row in live_focal:
  event_id=row["event_id"]
  event_bundles.append({"asset_id":f"axial_focal_event_{event_id}","asset_type":"focal_event_bundle","event_id":event_id,"origin_time_utc":row["origin_time_utc"],"latitude":row["latitude"],"longitude":row["longitude"],"depth_km":row["depth_km"],"magnitude_mw":row["magnitude_mw"],"fault_type":row["fault_type"],"quality":row["quality"],"detail_url":f"{BASE}/FocalMechanisms/events/FM_{event_id}.html","beachball_url":f"{BASE}/FocalMechanisms/images/beachball_{event_id}.png","map_url":f"{BASE}/FocalMechanisms/images/map_{event_id}.png","waveform_url":f"{BASE}/FocalMechanisms/images/waveform_{event_id}.png","retrieval_mode":"live_on_demand","is_mutable":False})
 summaries=[
  {"summary_id":"axial_visual_inventory","period_type":"archive","title":"Axial visual archive inventory","text":f"The Axial website snapshot indexes {len(caldera):,} dated caldera maps and {len(regional):,} dated regional maps from {caldera[0][1][:4]}-{caldera[0][1][4:6]}-{caldera[0][1][6:]} through {caldera[-1][1][:4]}-{caldera[-1][1][4:6]}-{caldera[-1][1][6:]}. It also publishes rolling earthquake maps and histograms, annual and eruption focal-mechanism maps, RSAM plots, monthly focal tables, and per-event beachball, map, and waveform images.","source_urls":[f"{BASE}/",f"{BASE}/map1.html",f"{BASE}/map2.html",f"{BASE}/Focal%20Mechanisms.html",f"{BASE}/rsam.html"]},
  {"summary_id":"axial_map_semantics","period_type":"method","title":"Axial earthquake map encodings","text":"Axial earthquake maps show latitude and longitude. Event color represents depth and symbol size represents moment magnitude. Rolling maps cover caldera and regional views over 1, 7, and 30 days; dated maps are retrievable for each UTC archive date.","source_urls":[f"{BASE}/"]},
  {"summary_id":"axial_histogram_semantics","period_type":"method","title":"Axial earthquake histogram products","text":"Recent histograms cover 7 days, 30 days, and 1 year. Eruption histograms cover the 2015 eruption at full, 60-day, and 15-day scales. Full-catalog histograms summarize detected and located earthquake activity over the archive.","source_urls":[f"{BASE}/"]},
  {"summary_id":"axial_rsam_interpretation","period_type":"method","title":"Axial RSAM plot interpretation","text":"RSAM plots show one-minute median absolute vertical-channel amplitudes in raw counts for 1–2 Hz and 2–4 Hz bands, refreshed hourly. AXCC1 and six outer stations are plotted over 7-day, 30-day, 1-year, and full-history windows. Multi-station and multi-band increases provide stronger evidence than an isolated increase.","source_urls":[f"{BASE}/rsam.html"]},
  {"summary_id":"axial_catalog_caveats","period_type":"provenance","title":"Axial catalog caveats and backfill","text":"The Axial catalog is updated hourly and may backfill locations after high-sample-rate data diverted by the Navy are later released. The catalog author warns that some seismic moments are inconsistent. Answers should state retrieval and data-through times and avoid treating moment fields as fully quality controlled.","source_urls":[f"{BASE}/"]},
  {"summary_id":"axial_focal_method_details","period_type":"method","title":"Axial focal-mechanism method and eligibility","text":"The near-real-time focal workflow predicts P polarities, selects six similar historical earthquakes using hypocenter, polarity, and S/P information across seven stations, and runs HASH. A successful hypocenter plus at least five P picks and five S picks is required. Per-event pages publish a beachball, location map, waveform plot, solution values, quality, analog count, dPo, and dLoc.","source_urls":[f"{BASE}/Focal%20Mechanisms.html"]},
  {"summary_id":"axial_catalog_citations","period_type":"citation","title":"Axial earthquake catalog citations","text":"The website asks users to cite Wilcock et al. (2016), Seismic constraints on caldera dynamics from the 2015 Axial Seamount eruption, Science 354, 1395–1399, and Wilcock, Waldhauser, and Tolstoy (2017), the IEDA Axial earthquake catalogs, DOI 10.1594/IEDA/323843.","source_urls":[f"{BASE}/"]},
 ]
 for phase in ("before","during","after"): summaries.append({"summary_id":f"axial_eruption_focal_{phase}","period_type":"eruption_phase","period_utc":"2015 eruption","title":f"Axial focal mechanisms {phase} the 2015 eruption","text":f"The Axial focal-mechanism archive publishes a static composite map for earthquakes {phase} the 2015 eruption. The source page does not state the phase boundary dates, so the figure is preserved with its original phase label.","source_urls":[f"{BASE}/EruptionFM_{phase.title()}.jpg",f"{BASE}/Focal%20Mechanisms.html"]})
 for year,count in ANNUAL_COUNTS.items(): summaries.append({"summary_id":f"axial_focal_year_{year}","period_type":"year","period_utc":str(year),"focal_mechanism_count":count,"title":f"Axial composite focal mechanisms in {year}","text":f"The published {year} Axial focal-mechanism figure summarizes {count:,} composite focal mechanisms.","source_urls":[f"{BASE}/FocalMechanisms_{year}.jpg",f"{BASE}/Focal%20Mechanisms.html"]})
 summaries.extend(month_pages)
 write_jsonl(out/"figures"/"archive_manifest.jsonl",assets)
 write_jsonl(out/"figures"/"focal_event_products.jsonl",event_bundles)
 write_jsonl(out/"visual_summaries.jsonl",summaries)
 write_jsonl(out/"figures"/"manifest.jsonl",[x for x in assets if x["asset_type"] not in {"daily_earthquake_map","monthly_focal_summary_page"}]+[{"asset_id":"axial_daily_caldera_map","asset_type":"daily_earthquake_map","name":"daily_caldera_map","url_pattern":f"{BASE}/mapCaldera/dailyCalderaMap_YYYYMMDD.jpg","date_semantics":"UTC","retrieval_mode":"live_on_demand"},{"asset_id":"axial_daily_regional_map","asset_type":"daily_earthquake_map","name":"daily_regional_map","url_pattern":f"{BASE}/mapRegional/dailyRegionalMap_YYYYMMDD.jpg","date_semantics":"UTC","retrieval_mode":"live_on_demand"}])
 (out/"tool_manifest.json").write_text(json.dumps({"tools":TOOL_SCHEMAS},indent=2)+"\n")
 visual_chunks=[]
 for x in summaries:
  period=x.get("period_utc","")
  text=x.get("text") or f"The Axial focal-mechanism archive page for {period} contains {x.get('focal_mechanism_count')} events and links each event to a detail page, beachball, location map, and waveform plot."
  visual_chunks.append({"chunk_id":"axial_visual_"+x["summary_id"],"title":x.get("title") or f"Axial focal mechanisms {period}","text":text,"entity_ids":["axial_seamount"],"source_ids":[],"metadata":x})
 chunks_path=out/"chunks.jsonl"; existing=[]
 if chunks_path.exists(): existing=[json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip() and not json.loads(line).get("chunk_id","").startswith("axial_visual_")]
 write_jsonl(chunks_path,existing+visual_chunks); write_jsonl(out/"visual_chunks.jsonl",visual_chunks)
 manifest_path=out/"manifest.json"; manifest=json.loads(manifest_path.read_text())
 manifest.update({"visual_archive_built_at_utc":built,"visual_asset_records":len(assets),"daily_caldera_maps_indexed":len(caldera),"daily_regional_maps_indexed":len(regional),"focal_month_pages":len(month_pages),"focal_event_product_bundles":len(event_bundles),"static_and_rolling_figure_products":len(FIGURES),"graph_chunks":len(existing)+len(visual_chunks),"live_tool_count":13})
 manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
 validation={"ok":len(caldera)==len(regional) and len(caldera)>4000,"daily_caldera_maps":len(caldera),"daily_regional_maps":len(regional),"date_ranges_match":caldera[0][1]==regional[0][1] and caldera[-1][1]==regional[-1][1],"static_and_rolling_figures":len(FIGURES),"monthly_pages":len(month_pages),"focal_event_bundles":len(event_bundles),"visual_summary_records":len(summaries)}
 (out/"visual_validation_report.json").write_text(json.dumps(validation,indent=2)+"\n")

if __name__=="__main__": main()
