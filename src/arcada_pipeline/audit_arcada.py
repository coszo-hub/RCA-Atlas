#!/usr/bin/env python3
"""Check RCA Information (Arcada) against independent sources and write the corrections the builder applies.

Arcada was a preliminary database, not double checked. Each correction names its authority:

- paper titles: the publisher's title in the literature catalog, by DOI (PDF imports cut titles at ~100 characters);
- paper abstracts: the paper's own abstract (from its full text, or the catalog) where Arcada gives another paper's,
  or only the PDF's front matter;
- paper-to-instrument links: Arcada's "Relevant instruments" lists were assigned by keyword (a sonar keyword links
  every ASHES instrument); a link is kept only where the paper's own text names the instrument by an unambiguous
  code (station code, reference designator, instrument code) or names its type and its site in one passage, and
  an instrument the text names by code is added;
- instrument positions and depths: OOI's site pages (positions over 1.5 km from the site, depths over 20 m off;
  the shallow-profiler platform is at 200 m, and profilers move through the water column); a placeholder position
  (45.0, -128.0) is cleared.

Usage: python3 audit_arcada.py --repo <arcada checkout>   (writes corrections.json beside this file)
"""
from __future__ import annotations

import argparse
import collections
import html
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src/literature_fulltext"))
from build_fulltext_corpus import AXIAL, SITES  # noqa: E402
sys.path.insert(0, str(HERE))
from build_arcada_graph import normalized_doi  # noqa: E402

SITE_PAGES = ROOT / "source_material/original_documents/OOISiteInventory"
OUTPUT = HERE / "corrections.json"

# Abstracts reassembled by hand from the paper's own first page (two-column text) or taken from it verbatim, where
# Arcada gives another paper's abstract. Keywords are the paper's own (its KEYWORDS line), or none.
MANUAL_ABSTRACTS = {
    "10.1002/rob.21961": {
        "abstract": "Although modern machine learning has the potential to greatly speed up the interpretation of imagery, the varied nature of the seabed and limited availability of expert annotations form barriers to its widespread use in seafloor mapping applications. This motivates research into unsupervised methods that function without large databases of human annotations. This paper develops an unsupervised feature learning method for georeferenced seafloor visual imagery that considers patterns both within the footprint of a single image frame and broader scale spatial characteristics. Features within images are learnt using an autoencoder developed based on the AlexNet deep convolutional neural network. Features larger than each image frame are learnt using a novel loss function that regularises autoencoder training using the Kullback–Leibler divergence function to loosely assume that images captured within a close distance of each other look more similar than those that are far away. The method is used to semantically interpret images taken by an autonomous underwater vehicle at the Southern Hydrates Ridge, an active gas hydrate field and site of a seafloor cabled observatory at a depth of 780 m. The method's performance when applied to clustering and content‐based image retrieval is assessed against a ground truth consisting of more than 18,000 human annotations. The study shows that the location based loss function increases the rate of information retrieval by a factor of two for seafloor mapping applications. The effects of physics‐based colour correction and image rescaling are also investigated, showing that the improved consistency of spatial information achieved by rescaling is beneficial for recognising artificial objects such as cables and infrastructures, but is less effective for natural objects that have greater dimensional variability.",
        "keywords": ["autoencoder", "computer vision", "mapping", "underwater robotics", "unsupervised learning"],
        "reason": "Arcada gives this paper the abstract and keywords of a COVIS paper (acoustic backscatter at ASHES); these are the paper's own, from its first page.",
    },
    "10.1029/2020gl087372": {
        "abstract": "Detailed examination of a 32‐year record of high‐resolution bottom pressure measurements at Axial Seamount (and vicinity) in the northeast Pacific identified a total of 41 tsunamis between 1986 and 2018. All of the events were associated with tsunamigenic earthquakes with magnitudes of 7.0 and greater. Statistical analysis of the data reveals that the time series of maximum tsunami amplitude and root‐mean‐square (RMS) tsunami amplitude follow strict power‐law distributions, with considerably less deviation than for coastal tide gauge records. The high statistical reliability of the seamount record is attributable to the long duration of the observations and to the low signal‐to‐noise ratio of digital open‐ocean bottom pressure records. The power law for the RMS tsunami amplitude is especially stable and follows a pure Pareto distribution (with exponent, β = 1.24) even when the minimum threshold is increased to the point that only a few events remain in the time series.",
        "keywords": None,
        "reason": "Arcada gives this paper the abstract of an AMOC observing review (Frajka-Williams et al., 2019); this is the paper's own, from its first page.",
    },
}

TYPE_WORDS = [
    (r"seismomet|broadband|ocean_bottom_seismic|seismic", r"seismomet|seismic station|seismic network|\bOBS\b|broadband|short-period|stations?\b"),
    (r"ctd", r"\bCTD|conductivity"), (r"pressure|bpr|tilt|botpt", r"pressure|\bBPR|\bBOTPT|\bAPG|tilt"),
    (r"hydrophone", r"hydrophone"), (r"adcp|velocimeter|current", r"\bADCP|current meter|velocimeter|currents?\b"),
    (r"camera", r"camera|imag"), (r"fluorometer", r"fluorometer|chlorophyll|CDOM"), (r"oxygen", r"oxygen|optode"),
    (r"sonar", r"sonar|COVIS"), (r"thermistor", r"thermistor|temperature"),
    (r"ph$|pco2|nitrate|spectrophotometer", r"\bpH\b|pCO2|nitrate|spectrophotometer"), (r"mass_spectrometer", r"mass spectrometer"),
    (r"das|fiber|strain", r"\bDAS\b|distributed acoustic|fib(?:er|re)|strain"), (r"hpies", r"HPIES|inverted echo"),
    (r"par|irradiance", r"\bPAR\b|irradiance|radiance"), (r"sampler", r"sampler"),
]


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def site_pages() -> dict[str, tuple[float, float, int]]:
    """OOI site code -> (latitude, longitude, water depth m), from the archived site pages."""
    out = {}
    for path in sorted(SITE_PAGES.glob("*.html")):
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8", errors="replace"))).split())
        pos = re.search(r"Location\s+(\d+\.\d+)°?N,\s*(\d+\.\d+)°?W", text)
        depth = re.search(r"Depth\s+(\d+)\s+meters", text)
        if pos and depth:
            out[path.stem] = (float(pos[1]), -float(pos[2]), int(depth[1]))
    return out


def km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    return 6371 * math.acos(min(1.0, math.sin(lat1 * p) * math.sin(lat2 * p)
                                + math.cos(lat1 * p) * math.cos(lat2 * p) * math.cos((lon1 - lon2) * p)))


def instrument_corrections(catalog: list[dict]) -> list[dict]:
    sites, out = site_pages(), []
    for row in catalog:
        refdes, site = row["id"], row.get("site")
        # A placeholder position (45.0, -128.0, from the PI pages) about 300 km offshore, given to the DAS experiments,
        # which run along the cable: no single position.
        if (row.get("latitude"), row.get("longitude")) in (("45.0", "-128.0"), (45.0, -128.0)):
            out.append({"id": refdes, "latitude": None, "longitude": None, "position_text": "along the RCA cable (no single position)",
                        "reason": "45.0, -128.0 is a placeholder from the PI pages, about 300 km offshore and away from any RCA node",
                        "authority": "https://oceanobservatories.org/regional-cabled-array/"})
            continue
        if site not in sites or row.get("latitude") in (None, ""):
            continue
        lat, lon, water = sites[site]
        fix, reasons = {}, []
        if km(float(row["latitude"]), float(row["longitude"]), lat, lon) > 1.5:
            fix.update(latitude=lat, longitude=lon)
            reasons.append(f"position {km(float(row['latitude']), float(row['longitude']), lat, lon):.1f} km from the {site} site")
        node = row.get("node") or ""
        # depth_m stays the site's water depth, as the atlas reads it (the map gives profilers their own ranges);
        # the Depth line says where a profiling instrument is.
        if node.startswith("PC"):                      # the shallow-profiler platform
            fix.update(depth_m=water, depth_text=f"200 m (shallow-profiler platform; water depth {water} m)")
            reasons.append("the water depth was given as the instrument's depth")
        elif node.startswith(("SF", "DP")):            # the profilers move through the water column
            what = "profiles between the 200 m platform and near the surface" if node.startswith("SF") else "profiles the water column below the shallow profiler"
            fix.update(depth_m=water, depth_text=f"{what} (water depth {water} m)")
            reasons.append("the water depth was given as the depth of a profiling instrument")
        elif row.get("depth_m") not in (None, "") and abs(float(row["depth_m"]) - water) > 20:
            fix.update(depth_m=water, depth_text=f"{water} m")
            reasons.append(f"depth {row['depth_m']} m, where the {site} site is at {water} m")
        if fix:
            out.append({"id": refdes, **fix, "reason": "; ".join(reasons),
                        "authority": f"https://oceanobservatories.org/site/{site.lower()}/"})
    return out


def type_rx(kind: str):
    return next((re.compile(rx, re.I) for key, rx in TYPE_WORDS if re.search(key, kind or "")), None)


def site_rx(location: str):
    best = None
    for _, name, aliases, axial in SITES:
        if any(a.lower() in (location or "").lower() for a in (*aliases, name)) and (best is None or len(name) > len(best[0])):
            best = (name, aliases, axial)
    return best and (re.compile("|".join(re.escape(a) for a in best[1]), re.I), best[2])


def link_corrections(rows: list[dict]) -> list[dict]:
    instruments = {d["canonical_id"]: d for d in read_jsonl(ROOT / "data/Instruments/instruments.jsonl")}

    def codes(cid: str) -> set[str]:
        out = set()
        if m := re.fullmatch(r"EARTHSCOPE-OO-([A-Z0-9]{5})", cid):
            out.add(m[1])
        if re.match(r"(RS|CE)\d\d", cid):
            out |= {cid, cid.split("-")[-1]}
        return out

    owners = collections.defaultdict(set)
    for cid in instruments:
        for code in codes(cid):
            owners[code].add(cid)
    unique = {code: next(iter(ids)) for code, ids in owners.items() if len(ids) == 1}
    code_rx = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(sorted(map(re.escape, unique), key=len, reverse=True)) + r")(?![A-Za-z0-9])")
    full = collections.defaultdict(list)
    for chunk in read_jsonl(ROOT / "data/LiteratureFullText/chunks.jsonl"):
        for key in chunk.get("paper_keys") or []:
            if key.startswith("10."):
                full[key.lower()].append(chunk["text"])
    papers = collections.defaultdict(lambda: {"texts": [], "arcada": set()})
    for row in rows:
        doi = normalized_doi(row)
        if row.get("type") != "paper" or not doi:
            continue
        p = papers[doi]
        p["texts"].append((row.get("text") or "").split("\nRelevant instruments")[0])
        p["arcada"] |= set(row.get("linked_instruments") or [])

    def support(passages: list[str], cid: str) -> str | None:
        d = instruments.get(cid)
        if not d:
            return None
        for code in codes(cid):
            if code in unique and any(re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", t) for t in passages):
                return "named by code"
        trx, srx = type_rx(d.get("instrument_type")), site_rx(d.get("location"))
        if trx and srx and any(trx.search(t) and srx[0].search(t) and (not srx[1] or AXIAL.search(t)) for t in passages):
            return "type and site named in one passage"
        return None

    out = []
    for doi, p in sorted(papers.items()):
        passages = p["texts"] + full.get(doi, [])
        kept = {cid: why for cid in p["arcada"] if (why := support(passages, cid))}
        added = {unique[m[1]]: "named by code" for t in passages for m in code_rx.finditer(t) if unique[m[1]] not in p["arcada"]}
        links = {**kept, **added}
        if set(links) != p["arcada"]:
            out.append({"doi": doi, "linked_instruments": sorted(links), "evidence": links,
                        "removed": sorted(p["arcada"] - set(links)), "full_text": doi in full,
                        "reason": "Arcada's list was assigned by keyword; links are kept or added only where the paper's text names the instrument"})
    return out


def paper_corrections(rows: list[dict]) -> list[dict]:
    catalog = {(r.get("resolved_doi") or "").lower(): r for r in read_jsonl(ROOT / "data/Literature/literature.jsonl") if r.get("resolved_doi")}
    out, seen = [], set()
    first = {}
    for row in rows:
        if row.get("type") == "paper" and normalized_doi(row):
            first.setdefault(normalized_doi(row), row)
    for doi, row in sorted(first.items()):
        fix, reasons = {}, []
        cat = catalog.get(doi) or {}
        title = cat.get("resolved_title")
        if title and norm(title) != norm(row.get("title")):
            fix["title"] = title
            reasons.append("title as the publisher gives it (Arcada's was cut, repeated or altered)")
        if doi in MANUAL_ABSTRACTS:
            m = MANUAL_ABSTRACTS[doi]
            fix["abstract"] = m["abstract"]
            if m["keywords"] is not None:
                fix["keywords"] = m["keywords"]
            reasons.append(m["reason"])
        elif re.match(r"\s*published:\s+\d", row.get("text") or "") and cat.get("abstract"):
            fix["prepend_abstract"] = " ".join(cat["abstract"].split())
            reasons.append("the first chunk is the PDF's front matter; the publisher's abstract leads it")
        if fix:
            out.append({"doi": doi, **fix, "reason": "; ".join(reasons),
                        "authority": f"https://doi.org/{doi}"})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="Arcada checkout at the recorded commit")
    args = parser.parse_args()
    rows = json.loads((args.repo / "public/chunks.json").read_text(encoding="utf-8"))
    for row in rows:
        if isinstance(row.get("linked_instruments"), str):
            row["linked_instruments"] = json.loads(row["linked_instruments"].replace("'", '"'))
    catalog = json.loads((args.repo / "catalog/instruments.json").read_text(encoding="utf-8"))["instruments"]
    corrections = {"papers": paper_corrections(rows), "links": link_corrections(rows), "instruments": instrument_corrections(catalog)}
    OUTPUT.write_text(json.dumps(corrections, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: len(v) for k, v in corrections.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
