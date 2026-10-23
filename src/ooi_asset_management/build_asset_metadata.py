#!/usr/bin/env python3
"""Build data/OOIAssetManagement from OOI's public asset-management repository, for the RCA's cabled instruments.

Each cabled reference designator gets its make and model (vocab), every deployment with its dates, sensor asset,
serial number, firmware, deploy and recovery cruises, position and depth (deployment/{site}_Deploy.csv,
bulk/*AssetRecord.csv, cruise/CruiseInformation.csv), and the calibration coefficients in force for each deployment
(calibration/{class}/{uid}__{date}.csv). Questions across instruments ("which CTDs are SBE 16plusV2?", "what was
deployed on Visions 25?", "which instruments are deeper than 2500 m?") get summary chunks by instrument type, site,
cruise and depth, because no single instrument's chunk answers them.

    python src/ooi_asset_management/build_asset_metadata.py [--repo source_material/repositories/asset-management]

The repository is a sparse clone (deployment/RS*, the cabled CE sites, bulk, cruise, vocab and the calibrations of the
sensors those deployments name); see README.md for the clone commands.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "source_material" / "repositories" / "asset-management"
OUTPUT = ROOT / "data" / "OOIAssetManagement"
CATALOG = ROOT / "data" / "Instruments" / "instruments.jsonl"
# The Worker bundles this: which chunk holds which instrument, site, type, cruise year and depth band (/v1/chunks).
WORKER_DIRECTORY = ROOT / "src" / "atlas_worker" / "src" / "asset_directory.json"
# Serial numbers and components that papers, web pages and documents give (curated; each quote is checked against
# the corpus chunk it comes from). Each entry becomes a chunk cited to its own source.
SOURCE_SERIALS = Path(__file__).resolve().parent / "source_serials.json"
DATA = ROOT / "data"
GITHUB = "https://github.com/oceanobservatories/asset-management/blob"
# The RCA's cabled sites: the Axial and Hydrate Ridge sites (RS*) and the Endurance Array's cabled Oregon Shelf and
# Offshore platforms, which the RCA operates.
SITES = re.compile(r"^(RS0|CE02SHBP|CE04OSBP|CE04OSPS|CE04OSPD)")
DEPTH_BANDS = ((2000, None, "deeper than 2000 m"), (1000, 2000, "1000 to 2000 m deep"),
               (200, 1000, "200 to 1000 m deep"), (None, 200, "shallower than 200 m"))
LONG_VALUE = 120   # a calibration value longer than this is an array, summarized rather than copied


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def day(value: str) -> str:
    return value[:10] if value else ""


def number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def metres(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g} m"


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


class Repository:
    def __init__(self, repo: Path):
        self.repo = repo
        self.commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                                     check=True).stdout.strip()
        self.commit_date = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%cs"], capture_output=True,
                                          text=True, check=True).stdout.strip()

    def url(self, path: str) -> str:
        return f"{GITHUB}/{self.commit}/{path}"

    def vocab(self) -> dict[str, dict]:
        return {r["Reference_Designator"]: r for r in read_csv(self.repo / "vocab" / "vocab.csv")}

    def assets(self) -> dict[str, dict]:
        out = {}
        for path in sorted((self.repo / "bulk").glob("*_bulk_load-AssetRecord.csv")):
            for r in read_csv(path):
                if r.get("ASSET_UID"):
                    out[r["ASSET_UID"]] = r | {"_file": f"bulk/{path.name}"}
        return out

    def cruises(self) -> dict[str, dict]:
        return {r["CUID"]: r for r in read_csv(self.repo / "cruise" / "CruiseInformation.csv")}

    def deployments(self) -> list[dict]:
        rows = []
        for path in sorted((self.repo / "deployment").glob("*_Deploy.csv")):
            if not SITES.match(path.name):
                continue
            for r in read_csv(path):
                if r.get("Reference Designator") and r.get("deploymentNumber"):
                    rows.append(r | {"_file": f"deployment/{path.name}"})
        return rows

    def calibrations(self) -> dict[str, list[tuple[str, Path]]]:
        """uid -> [(YYYY-MM-DD, path)], oldest first."""
        out: dict[str, list[tuple[str, Path]]] = defaultdict(list)
        for path in sorted((self.repo / "calibration").glob("*/*__*.csv")):
            uid, _, stamp = path.stem.rpartition("__")
            if re.fullmatch(r"\d{8}", stamp):
                out[uid].append((f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}", path))
        return {uid: sorted(files) for uid, files in out.items()}


def cruise_label(cuid: str, cruises: dict[str, dict]) -> str:
    """'AT50-41 (Atlantis, 2025-08-04 to 2025-08-31, Visions 25)': the ship, dates and OOI's name for the cruise."""
    c = cruises.get(cuid)
    if not cuid:
        return "no cruise recorded"
    if not c:
        return cuid
    name = re.sub(r"^Cabled \(rvdata\)\s*", "", c.get("notes", "")).strip()
    dates = f"{day(c.get('cruiseStartDateTime', ''))} to {day(c.get('cruiseStopDateTime', ''))}"
    return f"{cuid} ({c.get('ShipName')}, {dates}{', ' + name if name else ''})"


def distance_m(a: dict, b: dict) -> float | None:
    """Metres between two deployments' positions (flat-earth, ample at these distances)."""
    import math
    try:
        lat1, lon1, lat2, lon2 = (float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    k = 111_320.0
    return math.hypot((lat2 - lat1) * k, (lon2 - lon1) * k * math.cos(math.radians((lat1 + lat2) / 2)))


def changes(prev: dict, d: dict, assets: dict, cal_prev, cal) -> list[str]:
    """What changed from one deployment to the next: sensor, its make, model and firmware, node box, calibration,
    position and depth. An empty list is the same sensor put back in the same place."""
    out = []
    a, b = assets.get(prev.get("sensor.uid", ""), {}), assets.get(d.get("sensor.uid", ""), {})
    serial = lambda x, uid: x.get("Manufacturer's Serial No./Other Identifier") or uid or "not recorded"
    if prev.get("sensor.uid") != d.get("sensor.uid"):
        out.append(f"sensor {serial(a, prev.get('sensor.uid'))} replaced by {serial(b, d.get('sensor.uid'))} ({d.get('sensor.uid') or 'asset not recorded'})")
    for field, label in (("Manufacturer", "make"), ("Model", "model"), ("Firmware Version", "firmware")):
        if a.get(field) and b.get(field) and a[field] != b[field]:
            out.append(f"{label} {a[field]} to {b[field]}")
    if prev.get("node.uid") and d.get("node.uid") and prev["node.uid"] != d["node.uid"]:
        na, nb = assets.get(prev["node.uid"], {}), assets.get(d["node.uid"], {})
        out.append(f"node box {serial(na, prev['node.uid'])} to {serial(nb, d['node.uid'])}")
    if cal and (not cal_prev or cal[1] != cal_prev[1]):
        out.append(f"calibration {cal[0]}" + (f" (was {cal_prev[0]})" if cal_prev else ""))
    moved = distance_m(prev, d)
    if moved is not None and moved >= 50:
        out.append(f"position moved {moved:,.0f} m")
    da, db = number(prev.get("deployment_depth", "")), number(d.get("deployment_depth", ""))
    if da is not None and db is not None and abs(da - db) >= 5:
        out.append(f"deployment depth {metres(da)} to {metres(db)}")
    return out


def short_codes(refdes: str) -> list[str]:
    """The instrument class as people write it: RS03CCAL-MJ03F-09-SCPRAA301 is an SCPR (SCPRA), BOTPTA301 a BOTPT."""
    segment = refdes.split("-")[3]
    return list(dict.fromkeys([segment[:5], segment[:4]]))


def recovery_cruise(d: dict, cruises: dict[str, dict]) -> tuple[str, bool]:
    """The cruise that recovered a deployment: OOI's CUID_Recover, or else the cruise its stop date falls in (OOI
    seldom fills CUID_Recover; a cabled instrument ends its deployment when a cruise takes it up). `cruises` holds only
    the cabled-array cruises: CruiseInformation lists every OOI array's, and other arrays' overlap the RCA's.
    Returns (cuid, inferred)."""
    if d.get("CUID_Recover"):
        return d["CUID_Recover"], False
    stop = day(d.get("stopDateTime", ""))
    for cuid, c in cruises.items():
        if day(c.get("cruiseStartDateTime", "")) <= stop <= day(c.get("cruiseStopDateTime", "")):
            return cuid, True
    return "", False


def calibration_for(uid: str, start: str, calibrations: dict) -> tuple[str, Path] | None:
    """The calibration in force when a deployment started: the latest one dated on or before it, else the first."""
    files = calibrations.get(uid) or []
    before = [f for f in files if f[0] <= day(start)]
    return before[-1] if before else (files[0] if files else None)


def coefficients(path: Path) -> list[str]:
    out = []
    for r in read_csv(path):
        value = r.get("value", "")
        if len(value) > LONG_VALUE:
            items = [v for v in re.split(r"[\s,\[\]]+", value) if v]
            value = f"array of {len(items)} values ({', '.join(items[:3])}, ...)"
        out.append(f"{r.get('name')} = {value}")
    return out


def source_serials(path: Path = SOURCE_SERIALS, data: Path = DATA) -> list[dict]:
    """The curated entries, each quote checked word for word against its corpus chunk; any miss stops the build."""
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    texts: dict[str, dict[str, str]] = {}
    for entry in entries:
        for quote in entry["quotes"]:
            collection = quote["collection"]
            if collection not in texts:
                texts[collection] = {}
                for line in (data / collection / "chunks.jsonl").read_text(encoding="utf-8").splitlines():
                    row = json.loads(line)
                    texts[collection][row["chunk_id"]] = row.get("text") or ""
            if quote["text"] not in texts[collection].get(quote["chunk_id"], ""):
                raise ValueError(f"{entry['id']}: quote not found in {collection} {quote['chunk_id']}: {quote['text'][:60]}")
    return entries


def short_citation(citation: str) -> str:
    """'Sasagawa, G. S., Zumberge, M. A., & Cook, M. J. (2023). ...' -> 'Sasagawa et al. (2023)'."""
    match = re.match(r"^([^,(]+),.*?\((\d{4})\)", citation)
    if not match:
        return citation.split(".")[0]
    authors = citation[:citation.find("(")]
    return f"{match.group(1)}{' et al.' if authors.count('.,') > 1 or ' & ' in authors else ''} ({match.group(2)})"


def build(repo_path: Path, output: Path) -> dict:
    repo = Repository(repo_path)
    vocab, assets, cruises, calibrations = repo.vocab(), repo.assets(), repo.cruises(), repo.calibrations()
    cabled = {d["CUID_Deploy"] for d in repo.deployments() if d.get("CUID_Deploy")}
    names = {}
    if CATALOG.exists():
        for line in CATALOG.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            names[row.get("canonical_id")] = row.get("name")

    by_refdes: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in repo.deployments():
        refdes, number_ = r["Reference Designator"], r["deploymentNumber"]
        current = by_refdes[refdes].get(number_)
        if current is None or int(r.get("versionNumber") or 0) >= int(current.get("versionNumber") or 0):
            by_refdes[refdes][number_] = r   # the latest version of each deployment
    # Instruments only: a reference designator with an instrument code (site-node-port-class; profiler ports are 2A, 4B…), not a node or mooring.
    by_refdes = {k: v for k, v in by_refdes.items() if re.fullmatch(r"[A-Z0-9]{8}-[A-Z0-9]{5}-[A-Z0-9]{2}-[A-Z0-9]{9}", k)}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    entities, relationships, chunks, records = [], [], [], []
    sources = {}

    def source(path: str) -> str:
        """A repository file a chunk draws on; `named` makes the one source a chunk is cited by."""
        return path

    def named(title: str, url: str, files) -> list[str]:
        """The source a chunk is cited by, named for what it holds ("OOI asset-management: <refdes> deployments,
        assets and calibrations"), linked to its main file and listing every file it draws on. A citation shows one
        source a chunk; a file name such as vocab/vocab.csv says nothing to a reader."""
        sid = stable_id("OOI-ASSET-MANAGEMENT-SOURCE", title)
        sources.setdefault(sid, {"source_id": sid, "title": title, "source_url": url, "files": sorted(set(files)),
                                 "commit": repo.commit, "commit_date": repo.commit_date})
        return [sid]

    tree = lambda folder: f"https://github.com/oceanobservatories/asset-management/tree/{repo.commit}/{folder}"

    for refdes in sorted(by_refdes):
        deployments = sorted(by_refdes[refdes].values(), key=lambda r: (int(r["deploymentNumber"]), r["startDateTime"]))
        v = vocab.get(refdes, {})
        instrument = ("Profiler vehicle (engineering)" if refdes.split("-")[3].startswith("ENG")
                      else v.get("Instrument") or refdes.split("-")[3][:5])
        make_model = " ".join(x for x in (v.get("Manufacturer"), v.get("Model")) if x) or "make and model not recorded"
        place = ", ".join(x for x in (v.get("TOC_L1"), v.get("TOC_L2"), v.get("TOC_L3")) if x)
        name = names.get(refdes) or f"{v.get('TOC_L2') or refdes[:8]} {instrument}"
        refdes_id = stable_id("OOI-ASSETS-INSTRUMENT", refdes)
        source_ids = sorted({source(d["_file"]) for d in deployments} | {source("vocab/vocab.csv")})
        lines, cal_lines, used_cals, timeline = [], [], {}, []
        prev, cal_prev = None, None
        for d in deployments:
            asset = assets.get(d.get("sensor.uid", ""), {})
            serial = asset.get("Manufacturer's Serial No./Other Identifier") or "not recorded"
            firmware = asset.get("Firmware Version")
            depth, water = number(d.get("deployment_depth", "")), number(d.get("water_depth", ""))
            ended = bool(d.get("stopDateTime")) and d["stopDateTime"] <= now
            cal = calibration_for(d.get("sensor.uid", ""), d["startDateTime"], calibrations)
            # The timeline: each deployment against the one before, and the time out of the water between them.
            if prev is None:
                timeline.append(f"{day(d['startDateTime'])}: first deployment ({d['deploymentNumber']}), serial number {serial}.")
            else:
                gap = ""
                if prev.get("stopDateTime") and d.get("startDateTime"):
                    days_out = (datetime.fromisoformat(d["startDateTime"][:10]) - datetime.fromisoformat(prev["stopDateTime"][:10])).days
                    gap = f", {days_out} days after deployment {prev['deploymentNumber']} ended" if days_out > 1 else ""
                changed = changes(prev, d, assets, cal_prev, cal)
                timeline.append(f"{day(d['startDateTime'])}: deployment {d['deploymentNumber']}{gap}: "
                                + ("; ".join(changed) if changed else "same sensor, node and calibration redeployed") + ".")
            prev, cal_prev = d, cal
            recovered_on, inferred = recovery_cruise(d, {c: cruises[c] for c in cabled if c in cruises}) if ended else ("", False)
            recovery = (f"; recovered on cruise {cruise_label(recovered_on, cruises)}"
                        f"{' (inferred: the deployment ended during that cruise)' if inferred else ''}" if recovered_on
                        else "; recovery cruise not recorded" if ended else "")
            if asset:
                source_ids.append(source(asset["_file"]))
            lines.append(
                f"Deployment {d['deploymentNumber']}: {day(d['startDateTime'])} to "
                f"{day(d['stopDateTime']) if ended else 'present (deployed now)'}; sensor asset {d.get('sensor.uid') or 'not recorded'}"
                f"{' (' + ' '.join(x for x in (asset.get('Manufacturer'), asset.get('Model')) if x) + ')' if asset.get('Model') else ''}, "
                f"serial number {serial}, firmware {firmware or 'not recorded'}; deployed on cruise "
                f"{cruise_label(d.get('CUID_Deploy', ''), cruises)}"
                f"{recovery}; position "
                f"{d.get('lat')}, {d.get('lon')}; deployment depth {metres(depth)} (water depth {metres(water)})"
                f"{'; calibration ' + cal[0] if cal else '; no calibration file'}"
                f"{'; notes: ' + d['notes'] if d.get('notes') else ''}.")
            if cal:
                rel = str(cal[1].relative_to(repo.repo))
                source_ids.append(source(rel))
                used_cals.setdefault(rel, (cal[0], serial, []))[2].append(d["deploymentNumber"])
            dep_id = stable_id("OOI-ASSETS-DEPLOYMENT", refdes, d["deploymentNumber"])
            entities.append({"entity_id": dep_id, "entity_type": "deployment", "name": f"{refdes} deployment {d['deploymentNumber']}",
                             "attributes": {k: v for k, v in d.items() if not k.startswith("_")} | {"serial_number": serial}})
            relationships.append({"relationship_id": f"{dep_id}_of", "source_id": dep_id, "target_id": refdes_id,
                                  "relationship_type": "DEPLOYMENT_OF"})
            for cuid, kind in ((d.get("CUID_Deploy"), "DEPLOYED_ON"), (recovered_on, "RECOVERED_ON")):
                if cuid:
                    relationships.append({"relationship_id": f"{dep_id}_{kind}", "source_id": dep_id,
                                          "target_id": stable_id("OOI-ASSETS-CRUISE", cuid), "relationship_type": kind})
        latest = deployments[-1]
        deployed_now = not latest.get("stopDateTime") or latest["stopDateTime"] > now
        latest_asset = assets.get(latest.get("sensor.uid", ""), {})
        status = (f"It is deployed now: deployment {latest['deploymentNumber']} since {day(latest['startDateTime'])}, serial number "
                  f"{latest_asset.get(chr(39).join(['Manufacturer', 's Serial No./Other Identifier'])) or 'not recorded'}."
                  if deployed_now else
                  f"It is not deployed now: its last deployment ({latest['deploymentNumber']}) ended {day(latest['stopDateTime'])}.")
        numbers = sorted({int(d["deploymentNumber"]) for d in deployments})
        ended_ = [d for d in deployments if d.get("stopDateTime") and d["stopDateTime"] <= now]
        if ended_:
            last = max(ended_, key=lambda d: d["stopDateTime"])
            cuid, inferred = recovery_cruise(last, {c: cruises[c] for c in cabled if c in cruises})
            status += (f" It was last recovered {day(last['stopDateTime'])}, ending deployment {last['deploymentNumber']}"
                       f"{' on cruise ' + cruise_label(cuid, cruises) + (' (inferred from the end date)' if inferred else '') if cuid else ''}.")
        else:
            status += " It has never been recovered: no deployment has ended."
        codes = short_codes(refdes)
        head = (f"{refdes} is the {name} ({'/'.join(codes)}): {instrument}, {make_model}, at {place or refdes[:8]}. OOI asset-management lists "
                f"{len(numbers)} deployment{'s' if len(numbers) != 1 else ''} (number{'s' if len(numbers) != 1 else ''} {numbers[0]}{' to ' + str(numbers[-1]) if len(numbers) != 1 else ''}), from {day(deployments[0]['startDateTime'])}. {status}")
        chunks.append({
            "chunk_id": f"ooi_assets_{refdes}",
            "title": f"{name} ({refdes}, {'/'.join(codes)} {instrument}): make, model, serial numbers, firmware, deployments, "
                     "recoveries, cruises and depths",
            "text": "\n".join([head, "Changes over time (each deployment against the one before):"] + [f"- {t}" for t in timeline]
                               + ["Each deployment in full:"] + lines),
            "entity_ids": [refdes_id] + [stable_id("OOI-ASSETS-DEPLOYMENT", refdes, d["deploymentNumber"]) for d in deployments],
            "source_ids": named(f"OOI asset-management: {refdes} deployments, assets and calibrations",
                                repo.url(deployments[0]["_file"]), source_ids),
            "source_urls": [repo.url(deployments[0]["_file"])],
        })
        if used_cals:
            for rel, (date, serial, numbers_) in sorted(used_cals.items(), key=lambda kv: kv[1][0]):
                cal_lines.append(f"Calibration {date} of serial number {serial} (file {rel}), used for deployment"
                                 f"{'s' if len(numbers_) > 1 else ''} {', '.join(numbers_)}: " + "; ".join(coefficients(repo.repo / rel)) + ".")
            chunks.append({
                "chunk_id": f"ooi_assets_calibration_{refdes}",
                "title": f"{name} ({refdes}, {'/'.join(codes)} {instrument}): calibration coefficients and calibration dates, "
                         "by deployment and serial number",
                "text": f"Calibration coefficients of {refdes}, the {name} ({make_model}), from OOI asset-management. "
                        "Each deployment uses the calibration of its sensor dated on or before the deployment's start.\n"
                        + "\n".join(cal_lines),
                "entity_ids": [refdes_id],
                "source_ids": named(f"OOI asset-management: {refdes} calibration files", tree(f"calibration/{refdes.split('-')[3][:6]}"), used_cals),
                "source_urls": [repo.url(rel) for rel in sorted(used_cals)][:5],
            })
        entities.append({"entity_id": refdes_id, "entity_type": "instrument", "name": name, "reference_designator": refdes,
                         "attributes": {"reference_designator": refdes, "instrument": instrument, "manufacturer": v.get("Manufacturer"),
                                        "model": v.get("Model"), "deployments": len(numbers), "deployed_now": deployed_now}})
        depth = number(latest.get("deployment_depth", ""))
        records.append({"refdes": refdes, "name": name, "instrument": instrument, "make_model": make_model,
                        "site": v.get("TOC_L2") or refdes[:8], "array": v.get("TOC_L1") or "", "deployments": len(numbers),
                        "first": day(deployments[0]["startDateTime"]), "deployed_now": deployed_now,
                        "latest": latest, "serial": latest_asset.get("Manufacturer's Serial No./Other Identifier") or "not recorded",
                        "depth": depth, "all": deployments})

    def state(r: dict) -> str:
        latest = r["latest"]
        return (f"deployed now (deployment {latest['deploymentNumber']} since {day(latest['startDateTime'])}, serial {r['serial']})"
                if r["deployed_now"] else f"not deployed now (last deployment ended {day(latest['stopDateTime'])})")

    every = [source("vocab/vocab.csv")] + sorted({source(d["_file"]) for r in records for d in r["all"]})
    # Nodes (junction boxes, profiler pods and platforms, deep-profiler vehicles): which node asset was in place when,
    # from the node.uid of the instruments deployed on each node.
    on_node: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    node_place: dict[str, dict] = {}
    for r in records:
        node = "-".join(r["refdes"].split("-")[:2])
        node_place.setdefault(node, vocab.get(r["refdes"], {}) | {"_instruments": []})["_instruments"].append(r)
        for d in r["all"]:
            if d.get("node.uid"):
                on_node[node].append((d["startDateTime"], d["node.uid"], not d.get("stopDateTime") or d["stopDateTime"] > now,
                                      d.get("stopDateTime") or now))
    node_chunks: dict[str, str] = {}
    node_assets: set[str] = set()
    node_runs: dict[str, list[list]] = {}
    for node, uses in sorted(on_node.items()):
        uses.sort()
        runs: list[list] = []   # [first start, uid, still deployed, last stop]
        for start, uid, open_, stop in uses:
            if runs and runs[-1][1] == uid:
                runs[-1][2] = runs[-1][2] or open_
                runs[-1][3] = max(runs[-1][3], stop)
            else:
                runs.append([start, uid, open_, stop])
        node_runs[node] = runs
    # One node asset on two nodes at overlapping times: the deployment sheets disagree, and both nodes' chunks say so.
    # A node asset's period on a node runs until the next node asset there: an instrument left in place for years
    # (a BOTPT since 2014) keeps the node.uid of its own deployment, so its stop date says nothing about the node.
    # Periods end at the next instrument deployment, which can be weeks after a swap on a cruise: 30 days of
    # overlap are allowed.
    periods = [(uid, node, day(start), day(runs[i + 1][0]) if i + 1 < len(runs) else day(now))
               for node, runs in node_runs.items() for i, (start, uid, _, _) in enumerate(runs)]
    overlap_days = lambda a, b: (datetime.fromisoformat(min(a[3], b[3])) - datetime.fromisoformat(max(a[2], b[2]))).days
    clashes: dict[str, list[str]] = defaultdict(list)
    for a in periods:
        for b in periods:
            if a[0] == b[0] and a[1] < b[1] and overlap_days(a, b) > 30:
                note = (f"OOI asset-management has node asset {a[0]} on both {a[1]} ({a[2]} to {a[3]}) and {b[1]} ({b[2]} to "
                        f"{b[3]}): one box cannot be on two nodes at once, so one of the two deployment sheets is wrong there.")
                clashes[a[1]].append(note)
                clashes[b[1]].append(note)
    for node, runs in sorted(node_runs.items()):
        place = node_place[node]
        lines = []
        for i, (start, uid, open_, _) in enumerate(runs):
            asset = assets.get(uid, {})
            end = day(runs[i + 1][0]) if i + 1 < len(runs) else ("present" if open_ else "its instruments' last deployment")
            serial = asset.get("Manufacturer's Serial No./Other Identifier") or "not recorded"
            lines.append(f"- {day(start)} to {end}: node asset {uid} ({asset.get('DESCRIPTION OF EQUIPMENT') or 'not described'}"
                         f"{', ' + asset['Manufacturer'] if asset.get('Manufacturer') else ''}), serial number {serial}.")
        node_id = stable_id("OOI-ASSETS-NODE", node)
        entities.append({"entity_id": node_id, "entity_type": "node", "name": node, "attributes": {"node": node, "name": place.get("TOC_L3"), "site": place.get("TOC_L2")}})
        for start, uid, _, _ in runs:
            asset_id = stable_id("OOI-ASSETS-NODE-ASSET", uid)
            if asset_id not in node_assets:
                asset = assets.get(uid, {})
                node_assets.add(asset_id)
                entities.append({"entity_id": asset_id, "entity_type": "node_asset", "name": f"{asset.get('DESCRIPTION OF EQUIPMENT') or 'node asset'} {uid}",
                                 "attributes": {"uid": uid, "serial_number": asset.get("Manufacturer's Serial No./Other Identifier"),
                                                "manufacturer": asset.get("Manufacturer"), "model": asset.get("Model"),
                                                "description": asset.get("DESCRIPTION OF EQUIPMENT")}})
            relationships.append({"relationship_id": f"{node_id}_{uid}_{day(start)}", "source_id": node_id,
                                  "target_id": stable_id("OOI-ASSETS-NODE-ASSET", uid), "relationship_type": "NODE_ASSET"})
        chunk_id = f"ooi_assets_node_{node}"
        node_chunks[node] = chunk_id
        chunks.append({
            "chunk_id": chunk_id,
            "title": f"Node {node} ({place.get('TOC_L3') or 'node'}) at {place.get('TOC_L2') or node[:8]}: junction box or platform assets and serial numbers over time",
            "text": "\n".join([f"{node} is the {place.get('TOC_L3') or 'node'} at {place.get('TOC_L2') or node[:8]} ({place.get('TOC_L1') or ''}). "
                               "OOI asset-management names, for each instrument deployment on it, the node asset it was on; "
                               "in order, the node assets were:"] + lines
                              + clashes.get(node, [])
                              + [f"Instruments on {node}: " + "; ".join(f"{r['refdes']} ({r['name']})" for r in place["_instruments"]) + "."]),
            "entity_ids": [node_id], "source_ids": named(f"OOI asset-management: node {node} deployments",
                                                        repo.url(place["_instruments"][0]["all"][0]["_file"]),
                                                        [d["_file"] for r in place["_instruments"] for d in r["all"]]),
            "source_urls": [repo.url(place["_instruments"][0]["all"][0]["_file"])],
        })
    # Serial numbers from papers, web pages and documents: one chunk an entry, cited to its source.
    sourced: dict[str, list[str]] = defaultdict(list)
    for entry in source_serials():
        src = entry["source"]
        sid = stable_id("SOURCED-SERIALS-SOURCE", src["id"])
        sources.setdefault(sid, {"source_id": sid, "title": src["citation"], "path": src["id"], "source_url": src.get("url"),
                                 "kind": src["kind"]})
        target = entry.get("refdes") or entry.get("node")
        target_id = stable_id("OOI-ASSETS-INSTRUMENT", target) if entry.get("refdes") else stable_id("OOI-ASSETS-NODE", target)
        chunk_id = f"ooi_assets_sourced_{entry['id']}"
        sourced[target].append(chunk_id)
        for k, component in enumerate(entry["components"]):
            comp_id = stable_id("SOURCED-COMPONENT", entry["id"], str(k))
            entities.append({"entity_id": comp_id, "entity_type": "component", "name": f"{component['manufacturer']} {component['model']} {component['name']}",
                             "attributes": component | {"of": target, "relation": entry.get("relation") or "component", "source": src["citation"]}})
            relationships.append({"relationship_id": f"{comp_id}_of", "source_id": comp_id, "target_id": target_id,
                                  "relationship_type": "EARLIER_INSTRUMENT_COMPONENT" if entry.get("relation") else "COMPONENT_OF"})
        relation = f" ({entry['relation']} of {target})" if entry.get("relation") else f" ({target})"
        chunks.append({
            "chunk_id": chunk_id,
            "title": f"{entry['subject']}{relation}: serial numbers and components, from {short_citation(src['citation'])}",
            "text": f"{entry['subject']}{relation}. From {src['citation']}" + (f" ({src['url']})" if src.get("url") else "") + ":\n"
                    + "\n".join(f"- {fact}" for fact in entry["facts"])
                    + "\nThe source says: " + " ... ".join(f"\u201c{q['text']}\u201d" for q in entry["quotes"]),
            "entity_ids": [target_id] + [stable_id("SOURCED-COMPONENT", entry["id"], str(k)) for k in range(len(entry["components"]))],
            "source_ids": [sid], "source_urls": [src["url"]] if src.get("url") else [],
        })
    # One chunk per instrument type: make, model, serial and deployments of every instance.
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_type[r["instrument"]].append(r)
    for instrument, rows in sorted(by_type.items()):
        models = defaultdict(list)
        for r in rows:
            models[r["make_model"]].append(r["refdes"])
        chunks.append({
            "chunk_id": f"ooi_assets_type_{re.sub(r'[^A-Za-z0-9]+', '_', instrument).strip('_')}",
            "title": f"Every RCA {instrument} instrument: make and model, serial numbers, deployments and depth",
            "text": "\n".join(
                [f"The RCA has {len(rows)} cabled {instrument} instruments in OOI asset-management. By make and model: "
                 + "; ".join(f"{m}: {', '.join(codes)}" for m, codes in sorted(models.items())) + "."]
                + [f"- {r['refdes']} ({r['name']}), {r['make_model']}: {r['deployments']} deployments since {r['first']}, "
                   f"{state(r)}, deployment depth {metres(r['depth'])}." for r in sorted(rows, key=lambda r: r["refdes"])]),
            "entity_ids": [stable_id("OOI-ASSETS-INSTRUMENT", r["refdes"]) for r in rows],
            "source_ids": named(f"OOI asset-management: the RCA's cabled {instrument} instruments", tree("deployment"), every),
            "source_urls": [repo.url("vocab/vocab.csv")],
        })
    # One chunk per site: how often each instrument has been deployed, most first.
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_site[r["site"]].append(r)
    for site, rows in sorted(by_site.items()):
        rows = sorted(rows, key=lambda r: (-r["deployments"], r["refdes"]))
        chunks.append({
            "chunk_id": f"ooi_assets_site_{re.sub(r'[^A-Za-z0-9]+', '_', site).strip('_')}",
            "title": f"Instruments at {site} ({rows[0]['array']}): deployments and recoveries of each, most often redeployed first",
            "text": "\n".join([f"{site} ({rows[0]['array']}) has {len(rows)} cabled instruments in OOI asset-management. Each is "
                               "recovered and redeployed (often as a different serial number) on the RCA's cruises; "
                               "the number of deployments counts how often."]
                              + [f"- {r['refdes']} ({r['name']}, {r['make_model']}): {r['deployments']} deployments since "
                                 f"{r['first']}, {state(r)}." for r in rows]),
            "entity_ids": [stable_id("OOI-ASSETS-INSTRUMENT", r["refdes"]) for r in rows],
            "source_ids": named(f"OOI asset-management: {site} deployments", repo.url(rows[0]["latest"]["_file"]), every),
            "source_urls": [repo.url(rows[0]["latest"]["_file"])],
        })
    # One chunk per cruise: the instruments it deployed and recovered.
    deployed, recovered = defaultdict(list), defaultdict(list)
    for r in records:
        for d in r["all"]:
            if d.get("CUID_Deploy"):
                deployed[d["CUID_Deploy"]].append(f"{r['refdes']} ({r['name']}, deployment {d['deploymentNumber']})")
            if d.get("stopDateTime") and d["stopDateTime"] <= now:
                cuid, inferred = recovery_cruise(d, {c: cruises[c] for c in cabled if c in cruises})
                if cuid:
                    recovered[cuid].append(f"{r['refdes']} ({r['name']}, deployment {d['deploymentNumber']}"
                                           f"{', inferred from its end date' if inferred else ''})")
    # One chunk per year: the year's cruises (2017 and 2018 had four legs), so "Visions 25" and "the 2025 cruise" find it.
    by_year: dict[str, list[str]] = defaultdict(list)
    for cuid in sorted(set(deployed) | set(recovered), key=lambda c: cruises.get(c, {}).get("cruiseStartDateTime", c)):
        by_year[cruises.get(cuid, {}).get("cruiseStartDateTime", "")[:4] or "unknown"].append(cuid)
        entities.append({"entity_id": stable_id("OOI-ASSETS-CRUISE", cuid), "entity_type": "cruise", "name": cuid,
                         "attributes": cruises.get(cuid, {"CUID": cuid})})
    for year, cuids in sorted(by_year.items()):
        parts = [f"Cruise {cruise_label(c, cruises)} deployed {len(deployed[c])} instruments and recovered {len(recovered[c])}.\n"
                 f"Deployed on {c}: {'; '.join(deployed[c]) or 'none'}.\nRecovered on {c}: {'; '.join(recovered[c]) or 'none'}."
                 for c in cuids]
        chunks.append({
            "chunk_id": f"ooi_assets_cruises_{year}",
            "title": f"The RCA's {year} cruise{'s' if len(cuids) > 1 else ''} ({'; '.join(cruise_label(c, cruises) for c in cuids)}): "
                     "instruments deployed and recovered",
            "text": f"The RCA's {year} cabled-array operations cruise{'s' if len(cuids) > 1 else ''}, from OOI asset-management.\n"
                    + "\n".join(parts),
            "entity_ids": [stable_id("OOI-ASSETS-CRUISE", c) for c in cuids],
            "source_ids": named(f"OOI asset-management: the RCA's {year} cruises", repo.url("cruise/CruiseInformation.csv"),
                                ["cruise/CruiseInformation.csv"] + every),
            "source_urls": [repo.url("cruise/CruiseInformation.csv")],
        })
    # Depth bands of the latest deployment, deepest first.
    for low, high, label in DEPTH_BANDS:
        rows = sorted((r for r in records if r["depth"] is not None and (low is None or r["depth"] > low)
                       and (high is None or r["depth"] <= high)), key=lambda r: (-r["depth"], r["refdes"]))
        chunks.append({
            "chunk_id": f"ooi_assets_depth_{re.sub(r'[^a-z0-9]+', '_', label)}",
            "title": f"Which RCA instruments are {label}: every instrument's depth, deepest first (deep, deepest, depth below)",
            "text": "\n".join([f"Cabled RCA instruments {label} at their latest deployment, from OOI asset-management "
                               f"({len(rows)} instruments). Profiler instruments move through the water column; their "
                               "depth is the deployment depth OOI lists."]
                              + [f"- {metres(r['depth'])}: {r['refdes']} ({r['name']}, {r['make_model']})" for r in rows]),
            "entity_ids": [stable_id("OOI-ASSETS-INSTRUMENT", r["refdes"]) for r in rows],
            "source_ids": named("OOI asset-management: the RCA's cabled instruments by depth", tree("deployment"), every),
            "source_urls": [repo.url("vocab/vocab.csv")],
        })

    output.mkdir(parents=True, exist_ok=True)
    slug = lambda text: re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    directory = {
        "commit": repo.commit,
        "instruments": [{"refdes": r["refdes"], "name": r["name"], "instrument": r["instrument"], "site": r["site"],
                         "codes": short_codes(r["refdes"]), "calibration": f"ooi_assets_calibration_{r['refdes']}" in {c["chunk_id"] for c in chunks},
                         "sourced": sourced.get(r["refdes"], [])}
                        for r in records],
        "nodes": {node: {"id": chunk_id, "name": node_place[node].get("TOC_L3") or "", "site": node_place[node].get("TOC_L2") or "",
                         "sourced": sourced.get(node, [])} for node, chunk_id in sorted(node_chunks.items())},
        "sites": {site: f"ooi_assets_site_{slug(site)}" for site in sorted(by_site)},
        "types": {instrument: f"ooi_assets_type_{slug(instrument)}" for instrument in sorted(by_type)},
        "cruise_years": {year: f"ooi_assets_cruises_{year}" for year in sorted(by_year)},
        "depth_bands": [{"low": low, "high": high, "id": f"ooi_assets_depth_{re.sub(r'[^a-z0-9]+', '_', label)}"}
                        for low, high, label in DEPTH_BANDS],
    }
    ids = {c["chunk_id"] for c in chunks}
    missing = [i for i in [*directory["sites"].values(), *directory["types"].values(), *directory["cruise_years"].values(),
                           *(b["id"] for b in directory["depth_bands"])] if i not in ids]
    if missing:
        raise ValueError(f"directory names chunks that were not built: {missing[:5]}")
    WORKER_DIRECTORY.write_text(json.dumps(directory, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    def write(name: str, rows: list[dict]) -> None:
        (output / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    write("chunks.jsonl", chunks)
    write("entities.jsonl", entities)
    write("relationships.jsonl", relationships)
    write("source_documents.jsonl", sorted(sources.values(), key=lambda s: s["title"]))
    manifest = {"corpus": "OOI asset-management metadata for the RCA's cabled instruments",
                "built_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "repository": "https://github.com/oceanobservatories/asset-management", "commit": repo.commit,
                "commit_date": repo.commit_date, "instrument_count": len(records),
                "deployment_count": sum(len(r["all"]) for r in records), "chunk_count": len(chunks),
                "entity_count": len(entities), "relationship_count": len(relationships), "source_count": len(sources)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# OOI asset-management metadata\n\nThe RCA's cabled instruments from OOI's public asset-management repository: "
        "make and model, every deployment's dates, serial number, firmware, cruises, position and depth, and the "
        "calibration coefficients in force for each deployment. Built by "
        "`src/ooi_asset_management/build_asset_metadata.py`.\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
