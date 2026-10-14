"""Axial Seamount earthquakes from the UW daily hypo71 catalog: counts and histograms.

Each catalog file `hypo71_YYYYMMDD.dat` holds one UTC day. A row is
`yyyymmdd HHMM SS.SS latD latM lonD lonM depth MW NWR GAP DMIN RMS ERH ERZ ID PMom SMom`
with longitude in degrees west. As in the Worker's live count, only rows for
the file's own day with all 18 columns are events.
"""

from __future__ import annotations

import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

CATALOG = "http://axial.ocean.washington.edu/hypo71/hypo71_{stamp}.dat"


def parse_hypo71(text: str, day: str) -> list[dict]:
    """Events in one daily file; `day` is YYYY-MM-DD or YYYYMMDD."""
    stamp = day.replace("-", "")
    out = []
    for line in str(text or "").splitlines():
        p = line.split()
        if len(p) < 18 or p[0] != stamp:
            continue
        try:
            hhmm = p[1].zfill(4)
            base = datetime(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]), int(hhmm[:2]), int(hhmm[2:]), tzinfo=timezone.utc)
            when = base + timedelta(seconds=float(p[2]))       # 60.00 s rolls into the next minute
            lat = float(p[3]) + float(p[4]) / 60
            lon = -(float(p[5]) + float(p[6]) / 60)
            depth, mag = float(p[7]), float(p[8])
        except ValueError:
            continue
        out.append({"time": when.isoformat().replace("+00:00", "Z"), "day": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}",
                    "lat": round(lat, 6), "lon": round(lon, 6), "depth_km": depth, "mag": mag, "id": p[15]})
    return out


def days_between(start: str, end: str) -> list[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a:
        raise ValueError("end is before start")
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def http_loader(cache_dir: Path | None = None, timeout: float = 20.0) -> Callable[[str], str | None]:
    """Fetch a day's file from the live catalog, caching completed days on disk."""
    def load(day: str) -> str | None:
        stamp = day.replace("-", "")
        cached = cache_dir / f"hypo71_{stamp}.dat" if cache_dir else None
        if cached and cached.exists():
            return cached.read_text()
        try:
            with urllib.request.urlopen(CATALOG.format(stamp=stamp), timeout=timeout) as response:
                text = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if cached and date.fromisoformat(day) < datetime.now(timezone.utc).date():
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text)
        return text
    return load


def directory_loader(root: Path) -> Callable[[str], str | None]:
    def load(day: str) -> str | None:
        path = Path(root) / f"hypo71_{day.replace('-', '')}.dat"
        return path.read_text() if path.exists() else None
    return load


def load_events(start: str, end: str, loader: Callable[[str], str | None], *, workers: int = 6,
                deadline_s: float = 90.0, max_network_failures: int = 3) -> tuple[list[dict], list[str]]:
    """Events over the range and the days with no catalog file (absent or unreachable).

    Days are fetched in parallel under one overall deadline; after
    `max_network_failures` unreachable days the rest are not attempted, so a
    dead catalog host costs seconds, not one timeout per day.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, wait

    days = days_between(start, end)
    texts: dict[str, str | None] = {}
    failures = 0
    stop = threading.Event()
    lock = threading.Lock()

    def fetch(day: str) -> None:
        nonlocal failures
        if stop.is_set():
            return
        try:
            texts[day] = loader(day)
        except OSError:          # an unreachable catalog day is reported as missing, not fatal
            with lock:
                failures += 1
                if failures >= max_network_failures:
                    stop.set()

    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    futures = [pool.submit(fetch, day) for day in days]
    wait(futures, timeout=deadline_s)
    stop.set()
    pool.shutdown(wait=False, cancel_futures=True)
    events, missing = [], []
    for day in days:
        text = texts.get(day)
        if text is None:
            missing.append(day)
        else:
            events.extend(parse_hypo71(text, day))
    return events, missing


def select(events: Iterable[dict], *, min_mag: float | None = None, max_mag: float | None = None,
           min_depth_km: float | None = None, max_depth_km: float | None = None) -> list[dict]:
    keep = []
    for e in events:
        if min_mag is not None and e["mag"] < min_mag:
            continue
        if max_mag is not None and e["mag"] > max_mag:
            continue
        if min_depth_km is not None and e["depth_km"] < min_depth_km:
            continue
        if max_depth_km is not None and e["depth_km"] > max_depth_km:
            continue
        keep.append(e)
    return keep


def histogram(events: list[dict], *, by: str = "day", start: str | None = None, end: str | None = None,
              mag_bin: float = 0.25) -> dict:
    """Counts per day, per hour (UTC), or per magnitude bin.

    Day bins span start..end inclusive, so quiet days appear as zeros.
    """
    if by == "day":
        counts = Counter(e["day"] for e in events)
        days = days_between(start, end) if start and end else sorted(counts)
        return {"by": "day", "bins": days, "counts": [counts.get(d, 0) for d in days], "total": len(events)}
    if by == "hour":
        counts = Counter(e["time"][:13] for e in events)
        hours = sorted(counts)
        if start and end:
            hours = [f"{d}T{h:02d}" for d in days_between(start, end) for h in range(24)]
        return {"by": "hour", "bins": hours, "counts": [counts.get(h, 0) for h in hours], "total": len(events)}
    if by == "magnitude":
        if not events:
            return {"by": "magnitude", "bin_edges": [], "counts": [], "total": 0}
        mags = np.array([e["mag"] for e in events])
        lo = np.floor(mags.min() / mag_bin) * mag_bin
        hi = np.ceil((mags.max() + 1e-9) / mag_bin) * mag_bin
        edges = np.round(np.arange(lo, hi + mag_bin / 2, mag_bin), 6)
        if len(edges) < 2:
            edges = np.array([lo, lo + mag_bin])
        counts, _ = np.histogram(mags, bins=edges)
        return {"by": "magnitude", "bin_edges": edges.tolist(), "counts": counts.tolist(), "total": len(events)}
    raise ValueError("by must be 'day', 'hour', or 'magnitude'")


def summarize(events: list[dict], start: str, end: str, missing_days: list[str]) -> dict:
    mags = [e["mag"] for e in events]
    depths = [e["depth_km"] for e in events]
    per_day = histogram(events, by="day", start=start, end=end)
    busiest = max(zip(per_day["counts"], per_day["bins"]), default=(0, None))
    return {"start": start, "end": end, "count": len(events), "missing_days": missing_days,
            "complete": not missing_days,
            "magnitude": {"min": min(mags), "max": max(mags), "mean": round(float(np.mean(mags)), 3)} if mags else None,
            "depth_km": {"min": min(depths), "max": max(depths)} if depths else None,
            "busiest_day": {"day": busiest[1], "count": busiest[0]} if events else None,
            "daily": per_day}


def plot_histogram(hist: dict, path, title: str = "Axial Seamount earthquakes"):
    """Bar chart of a histogram; `path` is a file path or an open binary stream (PNG)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    if hist["by"] == "magnitude":
        edges = hist["bin_edges"]
        ax.bar(edges[:-1], hist["counts"], width=np.diff(edges), align="edge", color="#3b6ea8", edgecolor="white", linewidth=0.5)
        ax.set_xlabel("Magnitude (Mw)")
    else:
        ax.bar(range(len(hist["counts"])), hist["counts"], color="#3b6ea8", width=0.85)
        step = max(1, len(hist["bins"]) // 8)
        ax.set_xticks(range(0, len(hist["bins"]), step), [b[5:] for b in hist["bins"][::step]], fontsize=8)
        ax.set_xlabel("UTC " + hist["by"])
    ax.set_ylabel("Events")
    ax.set_title(f"{title} (n = {hist['total']})", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    if isinstance(path, (str, Path)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png")
    plt.close(fig)
    return path


# ------------------------------ question parsing -------------------------------

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


def _dates_in(q: str, today: date) -> list[tuple[int, date]]:
    """Every explicit date in the question with its position: ISO, US numeric, or month-name forms."""
    import re
    found = []

    def add(pos: int, year: int, month: int, day: int, year_given: bool = True) -> None:
        try:
            d = date(year, month, day)
        except ValueError:      # 2026-02-30 and the like: not a date, skip it
            return
        if not year_given and d > today:
            d = d.replace(year=year - 1)   # "Dec 20" asked in January means last December
        found.append((pos, d))

    for m in re.finditer(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", q):
        add(m.start(), int(m[1]), int(m[2]), int(m[3]))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", q):
        add(m.start(), int(m[3]), int(m[1]), int(m[2]))
    for m in re.finditer(rf"\b{_MONTH_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d{{2}}))?", q):
        add(m.start(), int(m[3]) if m[3] else today.year, MONTHS[m[1]], int(m[2]), year_given=bool(m[3]))
    return sorted(found)


def parse_quake_request(question: str, *, today: date) -> dict | None:
    """The UTC date range and magnitude floor an earthquake count/histogram question asks for.

    Ranges are inclusive. "last N days" and "last week" end today (N days in all);
    "since X" runs to today; a month name alone means that whole month. Returns
    None when no date expression is present.
    """
    import calendar
    import re
    q = " ".join(str(question or "").lower().split())
    out: dict = {"start": None, "end": None, "min_mag": None}
    # A magnitude is a small number, never the start of a date ("by magnitude 2026-01-01").
    m = re.search(r"(?:\bm(?:agnitude|w)?\s*(?:>=|≥|>|of at least|at least|above|over|greater than|larger than)?\s*|"
                  r"(?:above|over|greater than|larger than|at least|>=|≥|>)\s*(?:magnitude|mw?)\s*)(-?\d{1,2}(?:\.\d+)?)(?![\d-])", q)
    if m and re.search(r"magnitude|\bm(?:w)?\s*(?:>=|≥|>)|\bm(?:w)?\d|above m|over m|than m|least m", q):
        out["min_mag"] = float(m[1])
    dates = _dates_in(q, today)
    if re.search(r"day before yesterday", q):
        out["start"] = out["end"] = today - timedelta(days=2)
    elif len(dates) >= 2:
        out["start"], out["end"] = sorted([dates[0][1], dates[1][1]])
    elif dates and re.search(r"\bsince\b|\bfrom\b(?!.*\bto\b)", q):
        out["start"], out["end"] = dates[0][1], today
    elif dates:
        out["start"] = out["end"] = dates[0][1]
    elif (n := re.search(r"\b(?:last|past|previous)\s+(\d+)\s+days?\b", q)):
        out["start"], out["end"] = today - timedelta(days=int(n[1]) - 1), today
    elif re.search(r"\b(?:last|past|this)\s+week\b", q):
        out["start"], out["end"] = today - timedelta(days=6), today
    elif re.search(r"\byesterday\b", q):
        out["start"] = out["end"] = today - timedelta(days=1)
    elif re.search(r"\btoday\b|\bso far\b", q):
        out["start"] = out["end"] = today
    elif re.search(r"\blast month\b", q):
        first = today.replace(day=1) - timedelta(days=1)
        out["start"], out["end"] = first.replace(day=1), first
    elif re.search(r"\bthis month\b", q):
        out["start"], out["end"] = today.replace(day=1), today
    elif (mm := re.search(rf"\b(?:in|during|for)\s+{_MONTH_RE}(?:\s+(20\d{{2}}))?\b", q)):
        month = MONTHS[mm[1]]
        year = int(mm[2]) if mm[2] else (today.year if month <= today.month else today.year - 1)
        out["start"] = date(year, month, 1)
        out["end"] = min(date(year, month, calendar.monthrange(year, month)[1]), today)
    else:
        return None
    if out["end"] > today:
        out["end"] = today
    if out["start"] > out["end"]:
        return None
    return {"start": out["start"].isoformat(), "end": out["end"].isoformat(), "min_mag": out["min_mag"]}
