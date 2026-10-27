#!/usr/bin/env python3
"""Move source-only material out of data and normalize remaining assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NON_INGESTIBLE_EXTENSIONS = {".pdf", ".xlsx", ".xml", ".html", ".txt", ".csv", ".mpo", ".gz", ".sqlite"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text(element: ET.Element | None, name: str, ns: dict[str, str]) -> str | None:
    if element is None:
        return None
    found = element.find(name, ns)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def number(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


# The SEED instrument code (a channel code's second letter) says what made the channel.
INSTRUMENT = {"H": "seismometer (high gain)", "L": "seismometer (low gain)", "N": "accelerometer", "D": "pressure sensor or hydrophone",
              "A": "tiltmeter", "K": "temperature sensor"}
SEISMOMETER = {"H", "L"}
HORIZONTAL = {"N": "north", "1": "north (1)", "E": "east", "2": "east (2)"}


def horizontal(channel: dict, instruments=SEISMOMETER | {"N"}) -> bool:
    """A seismometer's or accelerometer's horizontal component (a BK1 temperature channel is not one)."""
    code = channel["channel"]
    return code[1:2] in instruments and code[2:3] in HORIZONTAL


def by_azimuth(channels: list[dict]) -> str:
    """'EHN at 0°; LHN, MHN, SHN at 35°': which channels point where, so disagreeing channels stay visible."""
    groups: dict[str, list[str]] = defaultdict(list)
    for x in sorted(channels, key=lambda x: x["channel"]):
        groups[degrees(x.get("azimuth_deg"))].append(x["channel"])
    return "; ".join(f"{', '.join(codes)} at {az}" for az, codes in groups.items())


def day(value: str | None) -> str:
    return (value or "")[:10]


def is_open(channel: dict) -> bool:
    return not channel.get("end_time") or channel["end_time"] > datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def degrees(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g}°"


def epoch_groups(channels: list[dict]) -> list[tuple[tuple, list[dict]]]:
    """Channel epochs that ran together: the same location code, sensor and dates."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for x in channels:
        groups[(x["location"], x.get("sensor_description") or "", day(x["start_time"]), day(x["end_time"]))].append(x)
    return sorted(groups.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1]))


def describe_group(key: tuple, channels: list[dict]) -> str:
    location, sensor, start, end = key
    rates: dict[float | None, list[str]] = defaultdict(list)
    for x in sorted(channels, key=lambda x: x["channel"]):
        rates[x.get("sample_rate_hz")].append(x["channel"])
    listed = "; ".join(f"{', '.join(codes)} at {rate:g} Hz" if rate is not None else ", ".join(codes) for rate, codes in rates.items())
    kinds = sorted({INSTRUMENT.get(x["channel"][1:2], "other") for x in channels})
    text = f"{start} to {end or 'present'}, location code {location or '(blank)'}: {sensor or 'sensor not described'} ({', '.join(kinds)}). Channels {listed}."
    components = [x for x in channels if horizontal(x)]
    if components:
        text += f" Horizontal azimuths: {by_azimuth(components)}."
    return text


def station_chunk(station: dict, channels: list[dict]) -> dict:
    name = f"{station['network']}.{station['station']}"
    lines = [f"{name} is {station.get('name') or 'a COSZO station'} at latitude {station.get('latitude')}, longitude "
             f"{station.get('longitude')}, elevation {station.get('elevation_m')} m, from {day(station.get('start_time'))} to "
             f"{day(station.get('end_time')) or 'present'}. Its metadata lists {len(channels)} channel epochs. Azimuth is the "
             "direction of a horizontal component, clockwise from geographic north; dip -90° is a vertical component pointing up."]
    lines += [describe_group(key, group) for key, group in epoch_groups(channels)]
    return {
        "chunk_id": f"station_metadata_{station['network']}_{station['station']}",
        "title": f"Station metadata for {name}: channels, sensors, sample rates and orientation (azimuth, dip)",
        "text": "\n".join(lines),
        "entity_ids": [station["station_id"]] + [x["channel_id"] for x in channels],
        "source_ids": station["source_ids"],
    }


def orientation_problems(north: list[dict], east: list[dict]) -> list[str]:
    """What cannot be right for one sensor: its channels at different azimuths, or a north and east component of the
    same band that are not 90° apart."""
    problems = []
    if len({x.get("azimuth_deg") for x in north}) > 1:
        problems.append(f"its north channels disagree: {by_azimuth(north)}")
    east_by_band = {x["channel"][:2]: x for x in east}
    for n in sorted(north, key=lambda x: x["channel"]):
        e = east_by_band.get(n["channel"][:2])
        if e and None not in (n.get("azimuth_deg"), e.get("azimuth_deg")) and (e["azimuth_deg"] - n["azimuth_deg"]) % 360 != 90:
            problems.append(f"{n['channel']} at {degrees(n['azimuth_deg'])} and {e['channel']} at {degrees(e['azimuth_deg'])} are not 90° apart")
    return problems


def orientation_chunk(stations: list[dict], by_station: dict[str, list[dict]]) -> dict:
    """Every station's seismometer orientation in one place, for questions across the network ("which seismometers
    are not at 0° azimuth?", "which have orientation issues?"), which no single station's record answers."""
    rows, rotated_now, north_now, rotated_before, issues_now, issues_before = [], [], [], [], [], []
    for station in stations:
        name = f"{station['network']}.{station['station']}"
        seismic = [x for x in by_station[station["station_id"]] if horizontal(x, SEISMOMETER)]
        if not seismic:
            continue
        for (location, sensor, start, end), group in epoch_groups(seismic):
            north = [x for x in group if x["channel"][2:3] in "N1"]
            east = [x for x in group if x["channel"][2:3] in "E2"]
            angles = {x.get("azimuth_deg") for x in north}
            current = any(is_open(x) for x in group)
            rotated = any(v not in (0.0, None) for v in angles)
            problems = orientation_problems(north, east)
            code = station["station"]
            if problems:
                (issues_now if current else issues_before).append(f"{code} ({'; '.join(problems)})")
            label = f"{code} ({by_azimuth(north)})" if len(angles) > 1 else f"{code} ({degrees(next(iter(angles), None))})"
            (rotated_now if rotated and current else north_now if current else rotated_before if rotated else []).append(label)
            note = ("; orientation issue: " + "; ".join(problems) + ". These channels record one sensor, which has one "
                    "orientation, so the StationXML is inconsistent; OOI would have to confirm the right azimuth" if problems
                    else " (not aligned with north)" if rotated else "")
            rows.append(f"- {name} ({station.get('name') or 'COSZO station'}), {sensor or 'seismometer'}, location code "
                        f"{location or '(blank)'}, {start} to {end or 'present'}: north component {by_azimuth(north) or 'none'}, "
                        f"east component {by_azimuth(east) or 'none'}{note}.")
    listed = lambda items: ", ".join(dict.fromkeys(items)) or "none"
    text = ["Seismometer orientation of every OO network station, from the stations' StationXML. Azimuth is the direction "
            "of a horizontal component, clockwise from geographic north; a seismometer is aligned with north when its "
            "north (N or 1) component is at 0° and its east (E or 2) component at 90°. StationXML gives an azimuth per "
            "channel, but a station's channels at different sample rates (EH, LH, MH, SH) record one sensor with one "
            "orientation, and its east component is 90° clockwise of its north component. A seismometer rotated from "
            "north is not an error: its horizontal components are rotated to north and east with the recorded azimuth. "
            "An orientation issue (an orientation problem or error) is metadata that cannot be right for one sensor.",
            f"Seismometers with orientation issues now: {listed(issues_now)}.",
            f"Earlier seismometer epochs with orientation issues: {listed(issues_before)}.",
            f"Seismometers not at 0° azimuth now (rotated from north): {listed(rotated_now)}.",
            f"Seismometers at 0° azimuth now: {listed(north_now)}.",
            f"Earlier seismometer epochs not at 0°: {listed(rotated_before)}.",
            "Each station's seismometer epochs:"] + rows
    return {
        "chunk_id": "station_metadata_seismometer_orientation",
        "title": "Seismometer orientation (azimuth) of every OO station: orientation issues in the metadata, and which "
                 "seismometers are not aligned with north",
        "text": "\n".join(text),
        "entity_ids": sorted({x["channel_id"] for chans in by_station.values() for x in chans if horizontal(x, SEISMOMETER)}),
        # Cited as itself: as one of its 27 station files' sources it was cited as OO_HYSB1.xml, a single station.
        "source_ids": [ORIENTATION_SOURCE["source_id"]],
        "source_urls": [ORIENTATION_SOURCE["source_url"]],
    }


ORIENTATION_SOURCE = {
    "source_id": "STATIONXML-OO-ORIENTATION",
    "title": "Seismometer orientation of every OO station (from the OO network StationXML)",
    "media_type": "text/plain",
    "source_url": "https://service.earthscope.org/fdsnws/station/1/query?network=OO&level=channel&format=text",
}


def station_graph(xml_files: list[Path], output: Path, project: Path) -> dict:
    stations: dict[str, dict] = {}
    channel_by_key: dict[tuple, dict] = {}
    sources = []
    for path in sorted(xml_files):
        root = ET.parse(path).getroot()
        uri = root.tag.partition("}")[0].removeprefix("{")
        ns = {"s": uri}
        source_id = "STATIONXML-" + sha256(path)[:16]
        sources.append({
            "source_id": source_id,
            "filename": path.name,
            "media_type": "application/xml",
            "sha256": sha256(path),
            "byte_size": path.stat().st_size,
            "archive_path": f"../../source_material/stationxml/{path.parent.name + '/' if path.parent.name != 'stationxml' else ''}{path.name}",
            "source": text(root, "s:Source", ns),
            "sender": text(root, "s:Sender", ns),
            "created": text(root, "s:Created", ns),
        })
        for network in root.findall("s:Network", ns):
            network_code = network.attrib.get("code", "")
            network_description = text(network, "s:Description", ns)
            for station in network.findall("s:Station", ns):
                station_code = station.attrib.get("code", "")
                station_id = f"station_{network_code}_{station_code}"
                site = station.find("s:Site", ns)
                current = stations.setdefault(station_id, {
                    "station_id": station_id,
                    "network": network_code,
                    "station": station_code,
                    "name": text(site, "s:Name", ns),
                    "network_description": network_description,
                    "latitude": number(text(station, "s:Latitude", ns)),
                    "longitude": number(text(station, "s:Longitude", ns)),
                    "elevation_m": number(text(station, "s:Elevation", ns)),
                    "start_time": station.attrib.get("startDate"),
                    "end_time": station.attrib.get("endDate"),
                    "source_ids": [],
                    "source_files": [],
                })
                if source_id not in current["source_ids"]: current["source_ids"].append(source_id)
                if path.name not in current["source_files"]: current["source_files"].append(path.name)
                for channel in station.findall("s:Channel", ns):
                    code, location = channel.attrib.get("code", ""), channel.attrib.get("locationCode", "")
                    start, end = channel.attrib.get("startDate"), channel.attrib.get("endDate")
                    key = (network_code, station_code, location, code, start, end)
                    sensor = channel.find("s:Sensor", ns)
                    sensitivity = channel.find("s:Response/s:InstrumentSensitivity", ns)
                    row = {
                        "channel_id": "channel_" + hashlib.sha256("|".join(str(x or "") for x in key).encode()).hexdigest()[:20],
                        "network": network_code, "station": station_code, "location": location, "channel": code,
                        "start_time": start, "end_time": end, "description": text(channel, "s:Description", ns),
                        "latitude": number(text(channel, "s:Latitude", ns)), "longitude": number(text(channel, "s:Longitude", ns)),
                        "elevation_m": number(text(channel, "s:Elevation", ns)), "depth_m": number(text(channel, "s:Depth", ns)),
                        "azimuth_deg": number(text(channel, "s:Azimuth", ns)), "dip_deg": number(text(channel, "s:Dip", ns)),
                        "sample_rate_hz": number(text(channel, "s:SampleRate", ns)),
                        "sensor_description": text(sensor, "s:Description", ns),
                        "sensitivity": number(text(sensitivity, "s:Value", ns)),
                        "sensitivity_frequency_hz": number(text(sensitivity, "s:Frequency", ns)),
                        "input_units": text(sensitivity, "s:InputUnits/s:Name", ns),
                        "output_units": text(sensitivity, "s:OutputUnits/s:Name", ns),
                        "station_id": station_id, "source_ids": [source_id], "source_files": [path.name],
                    }
                    if key in channel_by_key:
                        old = channel_by_key[key]
                        if source_id not in old["source_ids"]: old["source_ids"].append(source_id)
                        if path.name not in old["source_files"]: old["source_files"].append(path.name)
                    else:
                        channel_by_key[key] = row
    station_rows = sorted(stations.values(), key=lambda x: (x["network"], x["station"]))
    channel_rows = sorted(channel_by_key.values(), key=lambda x: (x["network"], x["station"], x["location"], x["channel"], x["start_time"] or ""))
    entities = [{"entity_id": x["station_id"], "entity_type": "station", "name": f"{x['network']}.{x['station']}", "attributes": x} for x in station_rows]
    entities += [{"entity_id": x["channel_id"], "entity_type": "channel", "name": f"{x['network']}.{x['station']}.{x['location']}.{x['channel']}", "attributes": x} for x in channel_rows]
    relationships = [{"relationship_id": f"{x['channel_id']}_at_{x['station_id']}", "source_id": x["channel_id"], "target_id": x["station_id"], "relationship_type": "CHANNEL_OF"} for x in channel_rows]
    by_station: dict[str, list[dict]] = defaultdict(list)
    for channel in channel_rows: by_station[channel["station_id"]].append(channel)
    chunks = [station_chunk(station, by_station[station["station_id"]]) for station in station_rows]
    chunks.append(orientation_chunk(station_rows, by_station))
    sources.append(ORIENTATION_SOURCE)
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "stations.jsonl", station_rows)
    write_jsonl(output / "channels.jsonl", channel_rows)
    write_jsonl(output / "entities.jsonl", entities)
    write_jsonl(output / "relationships.jsonl", relationships)
    write_jsonl(output / "chunks.jsonl", chunks)
    write_jsonl(output / "source_documents.jsonl", sources)
    manifest = {"corpus": "OOI StationXML normalized metadata", "built_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "station_count": len(station_rows), "channel_epoch_count": len(channel_rows), "entity_count": len(entities), "relationship_count": len(relationships), "chunk_count": len(chunks), "source_file_count": len(sources), "raw_source_archive": "../../source_material/stationxml"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# Station metadata\n\nGraph-RAG-ready normalization of OOI StationXML. Raw XML is preserved in `source_material/stationxml` outside the ingestible `data` directory. `stations.jsonl` stores station records, `channels.jsonl` stores channel epochs, and the entity/relationship/chunk files provide graph inputs.\n", encoding="utf-8")
    return manifest


def planned_moves(project: Path) -> list[tuple[Path, Path, str]]:
    data, archive = project / "data", project / "source_material"
    moves: list[tuple[Path, Path, str]] = []
    for path in sorted(data.rglob("*.pdf")) + sorted(data.rglob("*.xlsx")):
        rel = path.relative_to(data)
        moves.append((path, archive / "original_documents" / rel, "original_document"))
    station_dir = data / "station metadata"
    for path in sorted(station_dir.glob("*.xml")):
        moves.append((path, archive / "stationxml" / path.name, "stationxml_source"))
    axial_source = data / "AxialEarthquakes" / "graphrag" / "source"
    if axial_source.exists():
        for path in sorted(x for x in axial_source.rglob("*") if x.is_file()):
            moves.append((path, archive / "AxialEarthquakes" / "source_snapshot" / path.relative_to(axial_source), "source_snapshot"))
    website_figures = data / "Websites" / "figures"
    for path in sorted(website_figures.glob("*.mpo")):
        moves.append((path, archive / "Websites" / "mislabeled_jpeg_sources" / path.name, "mislabeled_jpeg_source"))
    for pattern in ("*.sqlite", "*.gz"):
        for path in sorted(data.rglob(pattern)):
            moves.append((path, project / "runtime_data" / path.relative_to(data), "runtime_query_store"))
    return moves


def update_jsonl(path: Path, transform) -> None:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip(): rows.append(transform(json.loads(line)))
    write_jsonl(path, rows)


def apply_cleanup(project: Path) -> dict:
    data, archive = project / "data", project / "source_material"
    moves = planned_moves(project)
    station_xml = [src for src, _, kind in moves if kind == "stationxml_source"]
    station_manifest = station_graph(station_xml, data / "StationMetadata", project) if station_xml else None

    # Make ingestible JPEG copies before archiving files whose extension was wrong.
    mpo_map: dict[str, str] = {}
    for src, _, kind in moves:
        if kind == "mislabeled_jpeg_source":
            jpg = src.with_suffix(".jpg")
            shutil.copy2(src, jpg)
            mpo_map[src.name] = jpg.name
    website_manifest = data / "Websites" / "figures.jsonl"
    if website_manifest.exists() and mpo_map:
        def fix_figure(row: dict) -> dict:
            old = Path(row.get("path", "")).name
            if old in mpo_map:
                row["path"] = str(Path(row["path"]).with_name(mpo_map[old]))
                row["media_type"] = "image/jpeg"
                row["normalized_extension"] = True
            return row
        update_jsonl(website_manifest, fix_figure)

    move_rows = []
    for src, dest, kind in moves:
        digest = sha256(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if sha256(dest) != digest: raise RuntimeError(f"Destination collision: {dest}")
            src.unlink()
        else:
            shutil.move(str(src), str(dest))
        move_rows.append({"kind": kind, "original_path": str(src.relative_to(project)), "archive_path": str(dest.relative_to(project)), "sha256": digest, "byte_size": dest.stat().st_size})

    # Update source-document pointers while retaining original filenames for citations.
    datasheets = data / "Datasheets" / "graphrag" / "source_documents.jsonl"
    if datasheets.exists():
        update_jsonl(datasheets, lambda r: {**r, "relative_path": f"../../../source_material/original_documents/Datasheets/{r['filename']}"})
    coszo = data / "coszo" / "graphrag" / "source_documents.jsonl"
    if coszo.exists():
        update_jsonl(coszo, lambda r: {**r, "relative_path": f"../../../source_material/original_documents/coszo/{r['filename']}"})
    literature = data / "Literature" / "source_documents.jsonl"
    if literature.exists():
        def fix_literature(row: dict) -> dict:
            if row.get("source_kind") == "glossary_pdf": row["source_path"] = "../../source_material/original_documents/Literature/Glossary.pdf"
            if row.get("source_kind") == "pdf_bibliography": row["source_path"] = "../../source_material/original_documents/coszo/COSZO Project DataMSRI.pdf"
            return row
        update_jsonl(literature, fix_literature)
    axial_summary = data / "AxialEarthquakes" / "graphrag" / "visual_summaries.jsonl"
    if axial_summary.exists():
        def fix_axial(row: dict) -> dict:
            local = row.get("local_source")
            if local and local.startswith("source/"):
                row["local_source"] = "../../../source_material/AxialEarthquakes/source_snapshot/" + local.removeprefix("source/")
            return row
        update_jsonl(axial_summary, fix_axial)
    axial_manifest = data / "AxialEarthquakes" / "graphrag" / "manifest.json"
    if axial_manifest.exists():
        row = json.loads(axial_manifest.read_text(encoding="utf-8")); row["source_snapshot_archive"] = "../../../source_material/AxialEarthquakes/source_snapshot"
        row["runtime_store"] = "../../../runtime_data/AxialEarthquakes/graphrag"
        axial_manifest.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")

    # Finder metadata is never provenance and can be discarded.
    ds_store = list(data.rglob(".DS_Store"))
    for path in ds_store: path.unlink()
    for directory in sorted((p for p in data.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try: directory.rmdir()
        except OSError: pass

    archive.mkdir(parents=True, exist_ok=True)
    old_move_manifest = archive / "move_manifest.jsonl"
    if old_move_manifest.exists():
        prior = [json.loads(line) for line in old_move_manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        known = {(x["original_path"], x["archive_path"]) for x in prior}
        move_rows = prior + [x for x in move_rows if (x["original_path"], x["archive_path"]) not in known]
    write_jsonl(old_move_manifest, move_rows)
    readme = "# Source material\n\nOriginal documents and raw source snapshots moved out of `data`. Their extracted Markdown, JSONL, graph records, images, and runtime databases remain under `data`. `move_manifest.jsonl` records original locations, archive locations, sizes, and SHA-256 checksums.\n"
    (archive / "README.md").write_text(readme, encoding="utf-8")
    allowed = {".md", ".json", ".jsonl", ".jpg", ".jpeg", ".png"}
    remaining = [p for p in data.rglob("*") if p.is_file() and p.suffix.lower() not in allowed]
    validation = {
        "ok": not remaining,
        "moved_file_count": len(move_rows),
        "moved_bytes": sum(x["byte_size"] for x in move_rows),
        "normalized_mpo_images": len(mpo_map),
        "removed_ds_store": len(ds_store),
        "station_metadata": station_manifest,
        "remaining_unapproved_files": [str(p.relative_to(data)) for p in remaining],
        "allowed_data_extensions": sorted(allowed),
        "validated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    (data / "cleanup_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    moves = planned_moves(args.project_root)
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "move_count": len(moves), "move_bytes": sum(src.stat().st_size for src,_,_ in moves), "by_kind": {kind: sum(1 for _,_,k in moves if k==kind) for kind in sorted({k for _,_,k in moves})}, "moves": [{"kind":kind,"from":str(src.relative_to(args.project_root)),"to":str(dest.relative_to(args.project_root))} for src,dest,kind in moves]}, indent=2))
        return
    print(json.dumps(apply_cleanup(args.project_root), indent=2))


if __name__ == "__main__": main()
