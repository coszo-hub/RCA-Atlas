"""Snapshot EarthScope's channel metadata for every OO station Arcada describes.

Arcada gives every EarthScope station the same template: broadband (or high-frequency) with BHZ, BHN and BHE.
The build corrects those rows from this snapshot, which is committed so rebuilds stay offline and reproducible.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FDSN_STATION = "https://service.earthscope.org/fdsnws/station/1/query"
SNAPSHOT = Path(__file__).with_name("earthscope_stations.json")


def stations_in(chunks: list[dict]) -> list[tuple[str, str]]:
    found = {re.fullmatch(r"EARTHSCOPE-([A-Z0-9]{1,2})-([A-Z0-9]{1,5})", r["id"]) for r in chunks}
    return sorted(m.groups() for m in found if m)


def parse_channels(text: str) -> list[dict]:
    channels = []
    for line in text.splitlines()[1:]:
        p = line.split("|")
        if len(p) < 17:
            continue
        channels.append({"location": p[2], "channel": p[3], "sensor": p[10].strip(), "sample_rate_hz": float(p[14]),
                         "start": p[15][:10], "end": p[16][:10] or None})
    return channels


def refresh(chunks_path: Path, output: Path = SNAPSHOT, urlopen=urllib.request.urlopen) -> int:
    stations = {}
    for net, sta in stations_in(json.loads(chunks_path.read_text())):
        url = f"{FDSN_STATION}?net={net}&sta={sta}&level=channel&format=text"
        with urlopen(url, timeout=60) as resp:
            stations[f"{net}.{sta}"] = {"source_url": url, "channels": parse_channels(resp.read().decode("utf-8"))}
    output.write_text(json.dumps({"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                  "stations": stations}, indent=1) + "\n")
    return len(stations)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path, help="Arcada checkout (reads public/chunks.json)")
    args = parser.parse_args()
    print(f"EarthScope stations: {refresh(args.repo / 'public' / 'chunks.json')}")
