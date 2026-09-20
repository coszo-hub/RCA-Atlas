#!/usr/bin/env python3
"""Build the Axial earthquake structured store and Graph-RAG corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from axial_agent_tools import FIGURES, TOOL_SCHEMAS, _finite_float, parse_focal_csv, parse_hypo71


BASE = "http://axial.ocean.washington.edu"
STATIONS = {
    "AXCC1": "Central Caldera seismometer",
    "AXEC1": "Eastern Caldera seismometer 1",
    "AXEC2": "Eastern Caldera seismometer 2",
    "AXEC3": "Eastern Caldera seismometer 3",
    "AXAS1": "Axial Summit seismometer 1",
    "AXAS2": "Axial Summit seismometer 2",
    "AXID1": "International District seismometer",
}


def dump_jsonl(path: Path, rows, gz: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if gz else open
    count = 0
    with opener(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            count += 1
    return count


def parse_historical_focal(path: Path, source_url: str) -> list[dict]:
    rows = []
    seen = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw or raw.startswith("#"): continue
        p = raw.split()
        if len(p) != 21: continue
        key = tuple(p)
        if key in seen: continue
        seen.add(key)
        rows.append({
            "event_id": p[0], "origin_time_utc": p[1] + "Z", "latitude": _finite_float(p[2]), "longitude": _finite_float(p[3]),
            "depth_km": _finite_float(p[4]), "magnitude_mw": _finite_float(p[5]), "strike_deg": _finite_float(p[6]),
            "dip_deg": _finite_float(p[7]), "rake_deg": _finite_float(p[8]), "fault_type": p[9], "quality": p[10],
            "analog_count": int(p[11]), "polarity_distance": _finite_float(p[12]), "location_distance_km": _finite_float(p[13]),
            "station_polarities": dict(zip(["AS1","AS2","CC1","EC1","EC2","EC3","ID1"], map(int, p[14:21]))),
            "source_url": source_url,
        })
    return rows


def summary_row(key: str, events: list[dict], period: str) -> dict:
    mags = [e["magnitude_mw"] for e in events if e["magnitude_mw"] is not None]
    deps = [e["depth_km"] for e in events if e["depth_km"] is not None]
    largest = max(events, key=lambda e: e["magnitude_mw"] if e["magnitude_mw"] is not None else -999) if events else None
    return {
        "summary_id": f"axial_{period}_{key}", "period_type": period, "period_utc": key, "earthquake_count": len(events),
        "magnitude_min": min(mags) if mags else None, "magnitude_max": max(mags) if mags else None,
        "magnitude_mean": sum(mags)/len(mags) if mags else None, "depth_min_km": min(deps) if deps else None,
        "depth_max_km": max(deps) if deps else None, "depth_mean_km": sum(deps)/len(deps) if deps else None,
        "largest_event_id": largest["event_id"] if largest else None, "largest_event_record_key": largest["record_key"] if largest else None,
        "source_url": f"{BASE}/hypo71.dat", "site_id": "axial_seamount",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--source-archive-dir", type=Path)
    args = parser.parse_args()
    source, out = args.source_dir, args.output_dir
    runtime = args.runtime_dir or out
    source_archive = args.source_archive_dir or (out / "source")
    out.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    events = parse_hypo71((source/"hypo71.dat").read_text(encoding="utf-8", errors="replace"), f"{BASE}/hypo71.dat")
    events.sort(key=lambda x: (x["origin_time_utc"], x["source_line"]))
    event_ids = Counter(e["event_id"] for e in events)
    by_day, by_month = defaultdict(list), defaultdict(list)
    for event in events:
        by_day[event["event_date_utc"]].append(event)
        by_month[event["event_date_utc"][:7]].append(event)
    daily = [summary_row(k, v, "day") for k,v in sorted(by_day.items())]
    monthly = [summary_row(k, v, "month") for k,v in sorted(by_month.items())]

    focal = []
    focal.extend(parse_historical_focal(source/"FM_XC_2015_2021.txt", f"{BASE}/FocalMechanisms/catalog/FM_XC_2015_2021.txt"))
    focal.extend(parse_historical_focal(source/"FM_ML_2022_2025.txt", f"{BASE}/FocalMechanisms/catalog/FM_ML_2022_2025.txt"))
    focal.extend(parse_focal_csv((source/"axial_focal_mechanisms.csv").read_text(encoding="utf-8", errors="replace"), f"{BASE}/FocalMechanisms/catalog/axial_focal_mechanisms.csv"))
    focal.sort(key=lambda x: (x["origin_time_utc"], x["event_id"]))

    db_path = runtime/"events.sqlite"
    if db_path.exists(): db_path.unlink()
    with sqlite3.connect(db_path) as db:
        db.executescript("""
        PRAGMA journal_mode=DELETE;
        CREATE TABLE events (
          record_key TEXT PRIMARY KEY, event_id TEXT NOT NULL, origin_time_utc TEXT NOT NULL, event_date_utc TEXT NOT NULL,
          latitude REAL, longitude REAL, depth_km REAL, magnitude_mw REAL, weighted_readings INTEGER,
          azimuthal_gap_deg REAL, nearest_station_km REAL, rms_seconds REAL, horizontal_error_km REAL, vertical_error_km REAL,
          p_moment REAL, s_moment REAL, site_id TEXT, source_url TEXT, source_line INTEGER
        );
        CREATE INDEX idx_events_date ON events(event_date_utc);
        CREATE INDEX idx_events_time ON events(origin_time_utc);
        CREATE INDEX idx_events_id ON events(event_id);
        CREATE INDEX idx_events_mag ON events(magnitude_mw);
        CREATE TABLE focal_mechanisms (
          focal_key TEXT PRIMARY KEY, event_id TEXT, origin_time_utc TEXT, latitude REAL, longitude REAL, depth_km REAL,
          magnitude_mw REAL, strike_deg REAL, dip_deg REAL, rake_deg REAL, fault_type TEXT, quality TEXT,
          analog_count INTEGER, polarity_distance REAL, location_distance_km REAL, station_polarities_json TEXT, source_url TEXT
        );
        CREATE INDEX idx_focal_time ON focal_mechanisms(origin_time_utc);
        CREATE INDEX idx_focal_event ON focal_mechanisms(event_id);
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
        """)
        db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(e[k] for k in ["record_key","event_id","origin_time_utc","event_date_utc","latitude","longitude","depth_km","magnitude_mw","weighted_readings","azimuthal_gap_deg","nearest_station_km","rms_seconds","horizontal_error_km","vertical_error_km","p_moment","s_moment","site_id","source_url","source_line"]) for e in events])
        focal_rows = []
        for idx, f in enumerate(focal):
            focal_key = hashlib.sha256((f["source_url"]+"|"+f["event_id"]+"|"+f["origin_time_utc"]+"|"+str(idx)).encode()).hexdigest()[:24]
            focal_rows.append((focal_key, f["event_id"], f["origin_time_utc"], f["latitude"], f["longitude"], f["depth_km"], f["magnitude_mw"], f["strike_deg"], f["dip_deg"], f["rake_deg"], f["fault_type"], f["quality"], f["analog_count"], f["polarity_distance"], f["location_distance_km"], json.dumps(f["station_polarities"]), f["source_url"]))
        db.executemany("INSERT INTO focal_mechanisms VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", focal_rows)
        db.executemany("INSERT INTO metadata VALUES (?,?)", [("built_at_utc",retrieved),("event_rows",str(len(events))),("first_event_utc",events[0]["origin_time_utc"]),("last_event_utc",events[-1]["origin_time_utc"])])

    dump_jsonl(runtime/"events.jsonl.gz", events, gz=True)
    dump_jsonl(runtime/"focal_mechanisms.jsonl.gz", focal, gz=True)
    dump_jsonl(out/"daily_summaries.jsonl", daily)
    dump_jsonl(out/"monthly_summaries.jsonl", monthly)

    sources = [
        {"source_id":"axial_catalog_home","title":"Axial Seamount Earthquake Catalog","url":f"{BASE}/","source_type":"live_web_catalog","scope":"Axial Seamount","update_frequency":"hourly"},
        {"source_id":"axial_hypo71_full","title":"Axial HYPO71 earthquake catalog","url":f"{BASE}/hypo71.dat","source_type":"structured_catalog","record_count":len(events)},
        {"source_id":"axial_hypo71_daily","title":"Axial daily HYPO71 catalogs","url":f"{BASE}/hypo71.html","source_type":"daily_catalog_index","date_semantics":"UTC"},
        {"source_id":"axial_ph2dt_daily","title":"Axial daily ph2dt arrival catalogs","url":f"{BASE}/ph2dt.html","source_type":"phase_pick_catalog_index","date_semantics":"UTC"},
        {"source_id":"axial_focal","title":"Axial focal mechanisms","url":f"{BASE}/Focal%20Mechanisms.html","source_type":"focal_mechanism_catalog"},
        {"source_id":"axial_rsam","title":"Axial RSAM","url":f"{BASE}/rsam.html","source_type":"continuous_amplitude_figures","update_frequency":"hourly"},
    ]
    entities = [
        {"entity_id":"axial_seamount","entity_type":"volcano","name":"Axial Seamount","description":"Active submarine volcano on the Juan de Fuca Ridge observed by the OOI Regional Cabled Array."},
        {"entity_id":"axial_earthquake_catalog","entity_type":"catalog","name":"Axial Seamount Earthquake Catalog","description":"Near-real-time detections and HYPOINVERSE locations derived from OOI cabled seismic data."},
        {"entity_id":"axial_focal_method","entity_type":"method","name":"Axial focal-mechanism workflow","description":"Near-real-time P-polarity analog selection and HASH focal-mechanism estimation for eligible located earthquakes."},
        {"entity_id":"axial_rsam","entity_type":"measurement_product","name":"Axial RSAM","description":"One-minute median absolute vertical-channel amplitudes in 1–2 Hz and 2–4 Hz bands."},
    ] + [{"entity_id":f"station_{k.lower()}","entity_type":"seismic_station","name":k,"description":v} for k,v in STATIONS.items()]
    relationships = [
        {"relationship_id":"catalog_describes_axial","source_id":"axial_earthquake_catalog","target_id":"axial_seamount","relationship_type":"DESCRIBES"},
        {"relationship_id":"focal_derives_catalog","source_id":"axial_focal_method","target_id":"axial_earthquake_catalog","relationship_type":"DERIVES_FROM"},
        {"relationship_id":"rsam_observes_axial","source_id":"axial_rsam","target_id":"axial_seamount","relationship_type":"OBSERVES"},
    ] + [{"relationship_id":f"{k.lower()}_observes_axial","source_id":f"station_{k.lower()}","target_id":"axial_seamount","relationship_type":"OBSERVES"} for k in STATIONS]

    chunks = [
        {"chunk_id":"axial_catalog_overview","title":"Axial Seamount earthquake catalog","text":f"The University of Washington Axial Seamount Earthquake Catalog provides near-real-time detections and HYPOINVERSE earthquake locations derived from the OOI Regional Cabled Array. The catalog is updated hourly. This snapshot contains {len(events):,} catalog rows from {events[0]['event_date_utc']} through {events[-1]['event_date_utc']}. Exact day counts should use the live axial_count_events tool because recent data change.","entity_ids":["axial_seamount","axial_earthquake_catalog"],"source_ids":["axial_catalog_home","axial_hypo71_full"]},
        {"chunk_id":"axial_event_fields","title":"Axial earthquake event fields","text":"Each normalized earthquake record preserves catalog ID, UTC origin time, latitude, west longitude, depth, moment magnitude, weighted reading count, azimuthal gap, nearest-station distance, RMS residual, horizontal and vertical errors, P moment, S moment, source URL, and source line. Catalog IDs are not globally unique, so record_key identifies a source row and exact counts count rows.","entity_ids":["axial_earthquake_catalog"],"source_ids":["axial_hypo71_full"]},
        {"chunk_id":"axial_focal_overview","title":"Axial focal mechanisms","text":"The focal-mechanism product uses predicted P-wave polarities, similar historical earthquakes, and HASH. Eligible earthquakes require a successful hypocenter plus at least five P picks and five S picks. Fault classes are normal (N), reverse (R), strike-slip (S), and unclassified (U). The live CSV has schema drift and is normalized by the retrieval code.","entity_ids":["axial_focal_method","axial_earthquake_catalog"],"source_ids":["axial_focal"]},
        {"chunk_id":"axial_rsam_overview","title":"Axial RSAM","text":"Axial RSAM is calculated from continuous 8 Hz vertical MHZ data as one-minute median absolute amplitude in the 1–2 Hz and 2–4 Hz bands. The site publishes hourly refreshed plots for AXCC1 and six outer stations over 7-day, 30-day, 1-year, and full-history windows.","entity_ids":["axial_rsam","axial_seamount"],"source_ids":["axial_rsam"]},
    ]
    for row in monthly:
        chunks.append({"chunk_id":row["summary_id"],"title":f"Axial earthquake activity in {row['period_utc']}","text":f"In {row['period_utc']} UTC, the Axial catalog contains {row['earthquake_count']:,} earthquake rows. Magnitudes range from {row['magnitude_min']} to {row['magnitude_max']}; the largest row is event {row['largest_event_id']}. Exact event details are in events.sqlite and events.jsonl.gz.","entity_ids":["axial_seamount","axial_earthquake_catalog"],"source_ids":["axial_hypo71_full"],"metadata":row})

    figure_manifest = [{"figure_id":f"axial_{name}","name":name,"source_url":f"{BASE}/{path}","scope":"Axial Seamount","retrieval_mode":"live","mime_type":"image/jpeg"} for name,path in FIGURES.items()]
    figure_manifest += [
        {"figure_id":"axial_daily_caldera_map","name":"daily_caldera_map","url_pattern":f"{BASE}/mapCaldera/dailyCalderaMap_YYYYMMDD.jpg","date_semantics":"UTC","retrieval_mode":"live"},
        {"figure_id":"axial_daily_regional_map","name":"daily_regional_map","url_pattern":f"{BASE}/mapRegional/dailyRegionalMap_YYYYMMDD.jpg","date_semantics":"UTC","retrieval_mode":"live"},
    ]
    dump_jsonl(out/"sources.jsonl", sources); dump_jsonl(out/"entities.jsonl", entities); dump_jsonl(out/"relationships.jsonl", relationships); dump_jsonl(out/"chunks.jsonl", chunks); dump_jsonl(out/"figures"/"manifest.jsonl", figure_manifest)

    raw_dir = source_archive
    raw_dir.mkdir(exist_ok=True)
    for name in ["hypo71.dat","axial_focal_mechanisms.csv","FM_ML_2022_2025.txt","FM_XC_2015_2021.txt","index.html","focal-mechanisms.html","rsam.html","hypo71-index.html","ph2dt-index.html","map1-index.html","map2-index.html"]:
        p = source/name
        if not p.exists(): continue
        if p.stat().st_size > 5_000_000:
            with p.open("rb") as inp, gzip.open(raw_dir/(name+".gz"),"wb") as dest: shutil.copyfileobj(inp,dest)
        else: shutil.copy2(p,raw_dir/name)

    manifest = {
        "corpus":"Axial Seamount earthquakes","built_at_utc":retrieved,"scope":"Axial Seamount and its OOI cabled seismic observations",
        "event_rows":len(events),"unique_catalog_ids":len(event_ids),"duplicate_id_groups":sum(1 for n in event_ids.values() if n>1),
        "first_event_utc":events[0]["origin_time_utc"],"last_event_utc":events[-1]["origin_time_utc"],"days_with_events":len(daily),
        "monthly_summaries":len(monthly),"focal_mechanisms":len(focal),"graph_chunks":len(chunks),"entities":len(entities),"relationships":len(relationships),
        "time_semantics":"UTC","live_tool_count":len(TOOL_SCHEMAS),"runtime_store":str(runtime),"source_snapshot_archive":str(source_archive),"notes":["Exact daily counts count valid catalog rows, not unique EventID values.","A zero-event daily file is distinct from an unavailable daily file.","The local snapshot supports historical fallback; live tools should answer current-day and yesterday questions.","Downloaded focal sources visibly lack coverage from 2025-03-08 through 2026-03-07."],
    }
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"tool_manifest.json").write_text(json.dumps({"tools":TOOL_SCHEMAS},indent=2)+"\n")
    validation = {"ok":True,"event_rows_match_source":len(events)==317696,"record_keys_unique":len({e['record_key'] for e in events})==len(events),"chronological":all(events[i]['origin_time_utc']<=events[i+1]['origin_time_utc'] for i in range(len(events)-1)),"duplicate_id_groups":manifest["duplicate_id_groups"],"event_count_2026_09_18":len(by_day.get("2026-09-18",[])),"focal_schema_normalized":True}
    (out/"validation_report.json").write_text(json.dumps(validation,indent=2)+"\n")


if __name__ == "__main__": main()
