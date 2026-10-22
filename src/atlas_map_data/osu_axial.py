"""OSU's Axial monitoring plots → per-instrument figure lists for the BOTPT pressure and seafloor CTD sensors.

Oregon State University (axial.ceoas.oregonstate.edu) redraws plots of the Axial BOTPT and seafloor CTD data every
15 minutes (the longer spans once a day) under fixed file names. The build reads which figures exist, and their
captions, from the pages archived under source_material, so it needs no network; the map loads the images from OSU.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from . import paths

BASE = "https://axial.ceoas.oregonstate.edu/"
SOURCE = paths.REPO / "source_material" / "original_documents" / "AxialCEOAS"
HOW = ("Oregon State University's plots of this instrument's real-time data, redrawn every 15 minutes (spans longer "
       "than a week once a day). The data have not been through quality checks.")
# The node a figure's file name starts with → its instruments. The OSU pages name them BOTPT-A301-MJ03F, MJ03F-CTDPFB305...
NODES = {
    "MJ03F": {"botpt": "RS03CCAL-MJ03F-05-BOTPTA301", "ctd": "RS03CCAL-MJ03F-12-CTDPFB305", "page": "mj03f.html"},
    "MJ03E": {"botpt": "RS03ECAL-MJ03E-06-BOTPTA302", "ctd": "RS03ECAL-MJ03E-12-CTDPFB306", "page": "mj03e.html"},
    "MJ03D": {"botpt": "RS03INT2-MJ03D-06-BOTPTA303", "ctd": "RS03INT2-MJ03D-11-CTDPFB307", "page": "mj03d.html"},
    "MJ03B": {"botpt": "RS03ASHS-MJ03B-09-BOTPTA304", "ctd": "RS03ASHS-MJ03B-10-CTDPFB304", "page": "mj03b.html"},
}
CTD_PAGES = {"MJ03B": "CTD.html", "MJ03E": "CTD2.html", "MJ03F": "CTD3.html", "MJ03D": "CTD4.html"}
# Each instrument's own page first, then the pages comparing all four BOTPTs.
PAGES = [n["page"] for n in NODES.values()] + list(CTD_PAGES.values()) + ["rates.html", "tilt.html", "alarms.html", "diffs.html"]
# File name → what it plots and over what span; first match wins.
GROUPS = (
    (r"CTDTemp", "Temperature"), (r"CTDSal", "Salinity"), (r"CTDDens", "Density"),
    (r"DET", "Depth (de-tided pressure)"), (r"1Wk.*RTMD", "Weekly tilt change"),
    (r"RTMD", "Tilt magnitude and direction"), (r"LILY", "Tilt (LILY X and Y)"),
    (r"1DayMeans|LTrates", "Uplift rate"), (r"RTM1WkRate|RTM-12MO|RTM-Since2015", "Tilt rate"),
    (r"STrates|AlarmSummary", "Event alarms"), (r"NANOdifference", "Differential uplift, Eastern minus Central"),
)
SPANS = (
    (r"AlarmSummary", "Now"), (r"1DayMeans", "Latest rates"), (r"1WkRate", "Last 2 weeks"), (r"3day", "3 days"),
    (r"7Days|7days", "7 days"), (r"3months", "3 months"), (r"6Months|6mo|6months", "6 months"), (r"12MO", "12 months"),
    (r"25Apr2015on|Since2015|Since25May2015|LTrates", "Since 2015"), (r"All", "Full record"),
)
IMG = re.compile(r'<img[^>]*\bsrc="graphs/([^"]+\.png)"[^>]*>', re.I)


def _first(rules, name: str) -> str | None:
    return next((label for pattern, label in rules if re.search(pattern, name)), None)


def _text(fragment: str) -> str:
    fragment = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fragment, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _caption(before: str, after: str) -> str | None:
    """OSU's caption: the "Plot N: ..." that follows a figure, without its "ONLY UPDATED ONCE PER DAY", or else the
    heading just above it (the differential-uplift page puts "Depth-difference (MJ03E-MJ03F), last 7 days" there)."""
    m = re.match(r"Plot \d+:\s*(.+?\.)(?=\s|$)", _text(after))
    if not m:
        heading = re.split(r"(?:\.|MAIN PAGE)\s+", _text(before))[-1]
        return heading + "." if 0 < len(heading) <= 120 else None
    text = m.group(1).rstrip(".") + "."
    return text.replace(" - RELATIVE TO 1 WEEK EARLIER.", ", relative to 1 week earlier.")


def _owners(name: str) -> list[str]:
    if name.startswith("NANOdifference"):          # the depth difference between the Eastern and Central BPRs
        return [NODES["MJ03E"]["botpt"], NODES["MJ03F"]["botpt"]]
    if name.startswith("AlarmSummary"):            # one table of all four BOTPTs
        return [n["botpt"] for n in NODES.values()]
    m = re.match(r"(MJ03[BDEF])", name)
    return [NODES[m.group(1)]["ctd" if "CTD" in name else "botpt"]] if m else []


def load_figures(source: Path = SOURCE) -> dict[str, dict]:
    """refdes → its access route, with the figures in page order."""
    routes: dict[str, dict] = {}
    pages = {n["botpt"]: n["page"] for n in NODES.values()} | {NODES[k]["ctd"]: p for k, p in CTD_PAGES.items()}
    for page in PAGES:
        path = source / page
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        matches = list(IMG.finditer(raw))
        for i, m in enumerate(matches):
            name = m.group(1)
            group, span = _first(GROUPS, name), _first(SPANS, name)
            if not group or not span:
                raise ValueError(f"OSU figure {name} on {page} has no group or span rule")
            start = matches[i - 1].end() if i else 0
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            figure = {"group": group, "span": span, "url": f"{BASE}graphs/{name}",
                      "caption": _caption(raw[start:m.start()], raw[m.end():end])}
            for refdes in _owners(name):
                route = routes.setdefault(refdes, {
                    "kind": "osu_axial", "label": "OSU Axial monitoring plots", "url": BASE + pages[refdes],
                    "how": HOW, "figures": []})
                if figure["url"] not in {f["url"] for f in route["figures"]}:
                    route["figures"].append(figure)
    return routes
