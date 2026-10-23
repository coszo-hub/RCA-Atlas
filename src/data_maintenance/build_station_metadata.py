#!/usr/bin/env python3
"""Rebuild data/StationMetadata from StationXML: the RCA stations' from EarthScope, the COSZO stations' as supplied.

The first station metadata came from 2017 StationXML that listed only some stations' pressure and tilt channels, so
no seismometer had a channel, azimuth or sensor in the corpus. EarthScope's FDSN station service holds every OO
channel epoch; its channel-level StationXML is saved under source_material/stationxml/earthscope (--refresh fetches
it again). The COSZO stations (CZ*) keep the COSZO and Nanometrics files in source_material/stationxml.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_data_folder import station_graph  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "source_material" / "stationxml"
EARTHSCOPE = ARCHIVE / "earthscope"
FDSN = "https://service.earthscope.org/fdsnws/station/1/query"
COSZO_PREFIX = "OO_CZ"


def fetch(network: str = "OO") -> list[str]:
    """Saves each non-COSZO station's channel-level StationXML; returns the station codes."""
    with urllib.request.urlopen(f"{FDSN}?net={network}&level=station&format=text", timeout=120) as res:
        codes = sorted({line.split("|")[1] for line in res.read().decode().splitlines()[1:] if line.strip()})
    codes = [c for c in codes if not f"{network}_{c}".startswith(COSZO_PREFIX)]
    EARTHSCOPE.mkdir(parents=True, exist_ok=True)
    for code in codes:
        with urllib.request.urlopen(f"{FDSN}?net={network}&sta={code}&level=channel&format=xml", timeout=120) as res:
            (EARTHSCOPE / f"{network}_{code}.xml").write_bytes(res.read())
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="fetch the EarthScope StationXML again")
    args = parser.parse_args()
    if args.refresh or not any(EARTHSCOPE.glob("*.xml")):
        print("fetched", ", ".join(fetch()))
    files = sorted(EARTHSCOPE.glob("*.xml")) + sorted(ARCHIVE.glob(f"{COSZO_PREFIX}*.xml"))
    print(json.dumps(station_graph(files, ROOT / "data" / "StationMetadata", ROOT), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
