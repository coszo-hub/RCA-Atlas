#!/usr/bin/env python3
"""Extract small, provenance-preserving spatial metadata from DAS HDF5 files.

The extractor intentionally reads metadata datasets only.  It never copies the
strain/phase array into the corpus.  It is useful for OptoDAS-style HDF5 files
which commonly expose ``/cableSpec/sensorDistances`` and, when available,
per-channel geographic positions.

Raw PI files must remain outside ``data/``.  The JSONL output is graph-ready
metadata and records the exact source-file checksum and source URL supplied by
the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from statistics import median
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _h5dump(path: Path, dataset: str) -> str | None:
    """Return a scalar/vector HDF5 dataset using the system h5dump utility."""
    if not shutil.which("h5dump"):
        raise RuntimeError("h5dump is required; install HDF5 tools before extracting metadata")
    result = subprocess.run(
        ["h5dump", "-d", dataset, str(path)], text=True, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def _data_body(dump: str | None) -> str | None:
    if not dump:
        return None
    match = re.search(r"DATA\s*\{(.*?)\n\s*\}\s*\n\}", dump, flags=re.DOTALL)
    return match.group(1) if match else None


def _numbers(path: Path, dataset: str) -> list[float] | None:
    body = _data_body(_h5dump(path, dataset))
    if body is None:
        return None
    # Strip h5dump's row labels, e.g. ``(9):``.
    body = re.sub(r"\(\d+\):", "", body)
    values = re.findall(r"(?<![A-Za-z0-9_])[-+]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", body)
    return [float(value) for value in values]


def _text(path: Path, dataset: str) -> str | None:
    body = _data_body(_h5dump(path, dataset))
    if body is None:
        return None
    quoted = re.search(r'"(.*)"', body)
    return quoted.group(1) if quoted else None


def _stable_id(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return "DAS-SPATIAL-" + hashlib.sha256(payload).hexdigest()[:18]


def extract_file(path: Path, source_url: str | None = None) -> dict[str, Any]:
    distances = _numbers(path, "/cableSpec/sensorDistances")
    if not distances:
        raise ValueError(f"{path} has no /cableSpec/sensorDistances metadata")
    cable_lengths = _numbers(path, "/cableSpec/cableLengths") or []
    cable_ids = _numbers(path, "/cableSpec/cables") or []
    coordinate_system = _text(path, "/cableSpec/positions/coordinateSystemName")
    eastings = _numbers(path, "/cableSpec/positions/eastings") or []
    northings = _numbers(path, "/cableSpec/positions/northings") or []
    depths = _numbers(path, "/cableSpec/positions/depths") or []
    steps = [right - left for left, right in zip(distances, distances[1:]) if right > left]
    position_count_matches = len(eastings) == len(northings) == len(distances)
    wgs84_coordinates = (
        coordinate_system == "WGS84"
        and position_count_matches
        and all(-180 <= value <= 180 for value in eastings)
        and all(-90 <= value <= 90 for value in northings)
    )
    locations = []
    if wgs84_coordinates:
        locations = [
            {"channel_index": index, "distance_m": distance, "longitude": eastings[index], "latitude": northings[index],
             "depth_m": depths[index] if len(depths) == len(distances) else None}
            for index, distance in enumerate(distances)
        ]
    return {
        "das_spatial_metadata_id": _stable_id(str(path.resolve()), _sha256(path)),
        "record_type": "das_hdf5_spatial_metadata",
        "source_file": str(path),
        "source_url": source_url,
        "source_file_sha256": _sha256(path),
        "source_file_size_bytes": path.stat().st_size,
        "metadata_path": "/cableSpec",
        "cable_ids": [int(value) if value.is_integer() else value for value in cable_ids],
        "cable_lengths_m": cable_lengths,
        "sensor_count": len(distances),
        "sensor_distance_start_m": distances[0],
        "sensor_distance_end_m": distances[-1],
        "sensor_spacing_median_m": median(steps) if steps else None,
        "coordinate_system": coordinate_system,
        "georeferenced_channel_positions": bool(locations),
        "channel_locations": locations,
        "caveats": ([] if locations else [
            "No per-channel WGS84 coordinates were present; distance is along-fiber metadata, not a geographic location."
        ]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="One raw DAS HDF5 file outside the graph-ready corpus")
    parser.add_argument("--output", required=True, type=Path, help="JSONL metadata output")
    parser.add_argument("--source-url", help="Authoritative URL from which this exact file was obtained")
    args = parser.parse_args()
    record = extract_file(args.input, args.source_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in (
        "das_spatial_metadata_id", "sensor_count", "sensor_distance_end_m",
        "sensor_spacing_median_m", "georeferenced_channel_positions"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
