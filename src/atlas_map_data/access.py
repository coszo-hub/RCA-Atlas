"""Per-sensor data-access routes. External coverage lists are cached by explicit refresh steps."""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ERDDAP = "https://erddap.dataexplorer.oceanobservatories.org/erddap"
QAQC = "https://ec2.qaqc.ooi-rca.net"
OOI_EXPLORER = "https://dataexplorer.oceanobservatories.org"
ALLOWED_HOSTS = {
    "erddap.dataexplorer.oceanobservatories.org", "dataexplorer.oceanobservatories.org",
    "oceanobservatories.org", "ooinet.oceanobservatories.org", "ec2.qaqc.ooi-rca.net",
    "piweb.ooirsn.uw.edu", "service.earthscope.org", "ds.iris.edu", "www.earthscope.org",
    "interactiveoceans.washington.edu", "coszo.org", "www.coszo.org", "github.com", "doi.org",
}


def erddap_dataset_id(refdes: str) -> str:
    return "ooi-" + refdes.lower()


def earthscope_station(record: dict) -> tuple[str, str] | None:
    m = re.fullmatch(r"EARTHSCOPE-([A-Z0-9]+)-([A-Z0-9]+)", record["id"])
    return (m.group(1), m.group(2)) if m else None


def _allowed(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ALLOWED_HOSTS


def load_external(runtime: Path) -> dict:
    out = {"erddap": set(), "qaqc": set(), "warnings": []}
    for key, name, field in (("erddap", "erddap_datasets.json", "datasetIds"), ("qaqc", "qaqc_refdes.json", "refdes")):
        path = runtime / name
        if path.exists():
            out[key] = set(json.loads(path.read_text())[field])
        else:
            out["warnings"].append(f"{name} missing; run build_atlas_bundle.py --refresh-external")
    return out


def refresh_erddap(runtime: Path, urlopen=urllib.request.urlopen) -> int:
    url = f"{ERDDAP}/tabledap/allDatasets.csv?datasetID&datasetID=~%22ooi-rs.*%22"
    with urlopen(url, timeout=60) as resp:
        rows = list(csv.reader(io.StringIO(resp.read().decode("utf-8"))))
    ids = sorted({r[0] for r in rows[2:] if r and r[0].startswith("ooi-rs")})
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "erddap_datasets.json").write_text(json.dumps(
        {"retrievedAt": datetime.now(timezone.utc).isoformat(), "source": url, "datasetIds": ids}, indent=1))
    return len(ids)


def refresh_qaqc(runtime: Path, index_paths: list[str]) -> int:
    refdes = sorted({p.rsplit("/", 1)[-1].split("_", 1)[0] for p in index_paths if p.startswith("RS")})
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "qaqc_refdes.json").write_text(json.dumps(
        {"retrievedAt": datetime.now(timezone.utc).isoformat(), "source": f"{QAQC}/QAQC_plots/index.json",
         "refdes": refdes}, indent=1))
    return len(refdes)


def build_access(record: dict, external: dict, pi_endpoints: dict[str, list[dict]],
                 vertical_channels: dict[str, str]) -> list[dict]:
    routes: list[dict] = []
    refdes = record.get("refdes")
    if refdes:
        ds = erddap_dataset_id(refdes)
        if ds in external["erddap"]:
            routes.append({"kind": "erddap", "label": "OOI ERDDAP (public, no login)", "datasetId": ds,
                           "url": f"{ERDDAP}/tabledap/{ds}.html",
                           "how": "Choose variables and a time range, then download CSV or NetCDF."})
        if refdes in external["qaqc"]:
            routes.append({"kind": "qaqc", "label": "RCA QA/QC plots", "refdes": refdes,
                           "url": f"{QAQC}/", "how": "Pre-rendered charts of recent data, updated by the RCA team."})
        routes.append({"kind": "ooi_explorer", "label": "OOI Data Explorer", "refdes": refdes,
                       "url": f"{OOI_EXPLORER}/#ooi/search/{urllib.parse.quote(refdes)}",
                       "how": "Browse and request OOI data products for this instrument."})
    station = earthscope_station(record)
    if station:
        net, sta = station
        routes.append({"kind": "earthscope", "label": "EarthScope FDSN", "network": net, "station": sta,
                       "channel": vertical_channels.get(f"{net}.{sta}"),
                       "url": f"https://service.earthscope.org/fdsnws/station/1/query?net={net}&sta={sta}&level=channel&format=text",
                       "how": "Public seismic waveforms (MiniSEED) and station metadata; no login."})
    for ep in pi_endpoints.get(record["instrumentId"], []):
        routes.append({"kind": "pi_portal", "label": f"PI data portal: {ep['label']}", "instrumentKey": ep["instrument_key"],
                       "url": ep["url"], "how": "Public directory listing; open folders by date to find files."})
    if not routes:
        for url in record.get("sources", []):
            if _allowed(url):
                routes.append({"kind": "documentation", "label": "Documentation", "url": url,
                               "how": "No public data feed is known yet; this page documents the sensor."})
    return [r for r in routes if _allowed(r["url"])]
