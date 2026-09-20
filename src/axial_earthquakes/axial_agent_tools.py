#!/usr/bin/env python3
"""Live and snapshot-backed tools for the Axial Seamount earthquake catalog."""

from __future__ import annotations

import base64
import calendar
import csv
import hashlib
import html
import io
import json
import math
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = "http://axial.ocean.washington.edu"
UTC = timezone.utc
MAX_LIVE_RANGE_DAYS = 31

FIGURES = {
    "caldera_1_day": "MapCaldera1day.jpg",
    "caldera_7_day": "MapCaldera7day.jpg",
    "caldera_30_day": "MapCaldera30day.jpg",
    "regional_1_day": "MapRegional1day.jpg",
    "regional_7_day": "MapRegional7day.jpg",
    "regional_30_day": "MapRegional30day.jpg",
    "histogram_7_day": "histogram7day.jpg",
    "histogram_30_day": "histogram30day.jpg",
    "histogram_1_year": "histogram1Year.jpg",
    "histogram_eruption_2015": "histogramEruption2015.jpg",
    "histogram_eruption_60_day": "histogramEruption60day.jpg",
    "histogram_eruption_15_day": "histogramEruption15day.jpg",
    "histogram_all_1": "histogramAll1.jpg",
    "histogram_all_2": "histogramAll2.jpg",
    "histogram_all_3": "histogramAll3.jpg",
    "histogram_all_4": "histogramAll4.jpg",
    "focal_mechanism_1_day": "FocalMechanism1day.jpg",
    "focal_mechanism_7_day": "FocalMechanism7day.jpg",
    "focal_mechanism_30_day": "FocalMechanism30day.jpg",
    "focal_mechanisms_2015": "FocalMechanisms_2015.jpg",
    "focal_mechanisms_2016": "FocalMechanisms_2016.jpg",
    "focal_mechanisms_2017": "FocalMechanisms_2017.jpg",
    "focal_mechanisms_2018": "FocalMechanisms_2018.jpg",
    "focal_mechanisms_2019": "FocalMechanisms_2019.jpg",
    "focal_mechanisms_2020": "FocalMechanisms_2020.jpg",
    "focal_mechanisms_2021": "FocalMechanisms_2021.jpg",
    "focal_mechanisms_2022": "FocalMechanisms_2022.jpg",
    "focal_mechanisms_2023": "FocalMechanisms_2023.jpg",
    "focal_mechanisms_2024": "FocalMechanisms_2024.jpg",
    "focal_mechanisms_2025": "FocalMechanisms_2025.jpg",
    "eruption_focal_before": "EruptionFM_Before.jpg",
    "eruption_focal_during": "EruptionFM_During.jpg",
    "eruption_focal_after": "EruptionFM_After.jpg",
    "rsam_7_day_caldera": "RSAM_past_7_days.jpg",
    "rsam_7_day_outer": "RSAM_past_7_days_outer.jpg",
    "rsam_30_day_caldera": "RSAM_past_30_days.jpg",
    "rsam_30_day_outer": "RSAM_past_30_days_outer.jpg",
    "rsam_1_year_caldera": "RSAM_past_1_year.jpg",
    "rsam_1_year_outer": "RSAM_past_1_year_outer.jpg",
    "rsam_history_caldera": "RSAM_full_history.jpg",
    "rsam_history_outer": "RSAM_full_history_outer.jpg",
}


def error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


def _finite_float(value: str | float | int | None) -> float | None:
    try:
        result = float(value)  # type: ignore[arg-type]
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def resolve_utc_day(value: str | date | None, now: datetime | None = None) -> date:
    now = now or datetime.now(UTC)
    if isinstance(value, date):
        return value
    token = (value or "yesterday").strip().lower()
    if token == "today":
        return now.date()
    if token == "yesterday":
        return (now - timedelta(days=1)).date()
    return date.fromisoformat(token)


def parse_hypo71(text: str, source_url: str | None = None) -> list[dict]:
    """Parse UW HYPO71 catalog rows into normalized event dictionaries."""
    events: list[dict] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        parts = raw.split()
        if len(parts) < 18 or not re.fullmatch(r"\d{8}", parts[0]):
            continue
        try:
            hhmm = parts[1].zfill(4)
            seconds = float(parts[2])
            whole_seconds = int(seconds)
            microseconds = int(round((seconds - whole_seconds) * 1_000_000))
            if microseconds == 1_000_000:
                whole_seconds += 1
                microseconds = 0
            origin = datetime.strptime(parts[0] + hhmm, "%Y%m%d%H%M").replace(tzinfo=UTC)
            origin += timedelta(seconds=whole_seconds, microseconds=microseconds)
            lat = float(parts[3]) + float(parts[4]) / 60.0
            lon = -(float(parts[5]) + float(parts[6]) / 60.0)
            event = {
                "record_key": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24],
                "event_id": str(parts[15]),
                "origin_time_utc": origin.isoformat().replace("+00:00", "Z"),
                # Preserve the UTC calendar day assigned by the upstream daily file.
                # A small number of rows encode 60.00 seconds and roll into the next
                # minute when normalized, but still belong to this catalog day.
                "event_date_utc": datetime.strptime(parts[0], "%Y%m%d").date().isoformat(),
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "depth_km": _finite_float(parts[7]),
                "magnitude_mw": _finite_float(parts[8]),
                "weighted_readings": int(parts[9]),
                "azimuthal_gap_deg": _finite_float(parts[10]),
                "nearest_station_km": _finite_float(parts[11]),
                "rms_seconds": _finite_float(parts[12]),
                "horizontal_error_km": _finite_float(parts[13]),
                "vertical_error_km": _finite_float(parts[14]),
                "p_moment": _finite_float(parts[16]),
                "s_moment": _finite_float(parts[17]),
                "site_id": "axial_seamount",
                "source_url": source_url,
                "source_line": line_number,
            }
            events.append(event)
        except (ValueError, OverflowError):
            continue
    return events


def parse_ph2dt(text: str, source_url: str | None = None) -> list[dict]:
    """Parse ph2dt event headers and station phase picks."""
    events: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        parts = raw.split()
        if not parts:
            continue
        if parts[0] == "#" and len(parts) >= 15:
            if current:
                events.append(current)
            try:
                sec = float(parts[6])
                origin = datetime(int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5]), tzinfo=UTC) + timedelta(seconds=sec)
                current = {
                    "event_id": str(parts[14]),
                    "origin_time_utc": origin.isoformat().replace("+00:00", "Z"),
                    "latitude": float(parts[7]),
                    "longitude": float(parts[8]),
                    "depth_km": float(parts[9]),
                    "magnitude": _finite_float(parts[10]),
                    "header_values": [_finite_float(x) for x in parts[11:14]],
                    "picks": [],
                    "source_url": source_url,
                }
            except (ValueError, IndexError):
                current = None
        elif current and len(parts) >= 4:
            current["picks"].append({
                "station": parts[0],
                "travel_time_seconds": _finite_float(parts[1]),
                "weight": _finite_float(parts[2]),
                "phase": parts[3],
            })
    if current:
        events.append(current)
    return events


def parse_focal_csv(text: str, source_url: str | None = None) -> list[dict]:
    """Parse the live CSV while repairing its known 20/21-column schema drift."""
    rows: list[dict] = []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return rows
    seen: set[tuple[str, ...]] = set()
    for values in reader:
        raw_key = tuple(values)
        if not values or raw_key in seen:
            continue
        seen.add(raw_key)
        if len(values) == len(header) + 1:
            repaired_header = header[:10] + ["Quality"] + header[10:]
        elif len(values) == len(header):
            repaired_header = header
        else:
            continue
        row = dict(zip(repaired_header, values))
        event_id = row.get("EventID")
        if not event_id: continue
        item: dict[str, Any] = {
            "event_id": str(event_id),
            "origin_time_utc": (row.get("OriginTime") or "") + ("Z" if row.get("OriginTime") and not row["OriginTime"].endswith("Z") else ""),
            "latitude": _finite_float(row.get("Lat")),
            "longitude": _finite_float(row.get("Lon")),
            "depth_km": _finite_float(row.get("DepthKm")),
            "magnitude_mw": _finite_float(row.get("Mw")),
            "strike_deg": _finite_float(row.get("Strike")),
            "dip_deg": _finite_float(row.get("Dip")),
            "rake_deg": _finite_float(row.get("Rake")),
            "fault_type": row.get("FaultType"),
            "quality": row.get("Quality"),
            "analog_count": int(row["nAnalogs"]) if (row.get("nAnalogs") or "").isdigit() else None,
            "polarity_distance": _finite_float(row.get("dPo")),
            "location_distance_km": _finite_float(row.get("dLocKm")),
            "source_url": source_url,
        }
        item["station_polarities"] = {k.removeprefix("Po_"): int(v) for k, v in row.items() if k.startswith("Po_") and v and re.fullmatch(r"-?\d+", v)}
        rows.append(item)
    return rows


class AxialToolkit:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        db_path: str | Path | None = None,
        cache_dir: str | Path | None = None,
        timeout: int = 45,
        cache_ttl_seconds: int = 300,
        now_fn=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        default_db = Path(__file__).resolve().parents[2] / "runtime_data" / "AxialEarthquakes" / "graphrag" / "events.sqlite"
        self.db_path = Path(db_path) if db_path else default_db
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "rcn-agent-axial-cache"
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self.now_fn = now_fn or (lambda: datetime.now(UTC))

    def _fetch(self, url: str, binary: bool = False, force_refresh: bool = False) -> bytes | str:
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".dat"
        key = re.sub(r"[^A-Za-z0-9_.-]+", "_", url)[-180:]
        cache = self.cache_dir / (key + suffix)
        if not force_refresh and cache.exists() and time.time() - cache.stat().st_mtime <= self.cache_ttl_seconds:
            payload = cache.read_bytes()
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "RCN-Agent-Axial/1.0"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(payload)
        return payload if binary else payload.decode("utf-8", errors="replace")

    def _daily_url(self, day: date) -> str:
        return f"{self.base_url}/hypo71/hypo71_{day:%Y%m%d}.dat"

    def _live_day(self, day: date, force_refresh: bool = False) -> tuple[list[dict], str]:
        url = self._daily_url(day)
        rows = parse_hypo71(str(self._fetch(url, force_refresh=force_refresh)), url)
        # Guard against an upstream redirect or incorrectly named daily file.
        rows = [row for row in rows if row["event_date_utc"] == day.isoformat()]
        return rows, url

    def _db(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Axial snapshot database not found: {self.db_path}")
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def catalog_status(self, force_refresh: bool = False) -> dict:
        url = f"{self.base_url}/"
        try:
            text = str(self._fetch(url, force_refresh=force_refresh))
        except Exception as exc:
            return error("axial_unavailable", str(exc), source_url=url)
        clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text)))
        update = re.search(r"Catalog last updated(?:\s+at)?\s*:?\s*([^<]*?UTC)", clean, re.I)
        locations = re.search(r"locations up to\s*([^<]*?UTC)", clean, re.I)
        streaming = re.search(r"(?:Status of\s+)?200\s*Hz waveform data(?:\s+status)?\s*[-:]\s*([A-Za-z]+)", clean, re.I)
        return {
            "ok": True,
            "catalog_last_updated": update.group(1).strip() if update else None,
            "locations_through": locations.group(1).strip() if locations else None,
            "waveform_status": streaming.group(1) if streaming else None,
            "retrieved_at_utc": self.now_fn().isoformat().replace("+00:00", "Z"),
            "source_url": url,
            "evidence_mode": "live",
        }

    def count_events(
        self,
        day: str = "yesterday",
        min_magnitude: float | None = None,
        max_magnitude: float | None = None,
        min_depth_km: float | None = None,
        max_depth_km: float | None = None,
        source: str = "auto",
        force_refresh: bool = False,
    ) -> dict:
        try:
            target = resolve_utc_day(day, self.now_fn())
        except ValueError:
            return error("invalid_date", "Use today, yesterday, or YYYY-MM-DD", supplied=day)
        events: list[dict]
        url = self._daily_url(target)
        mode = "live"
        live_error = None
        if source not in {"auto", "live", "snapshot"}:
            return error("invalid_source", "source must be auto, live, or snapshot")
        if source != "snapshot":
            try:
                events, url = self._live_day(target, force_refresh)
            except Exception as exc:
                if source == "live":
                    return error("axial_unavailable", str(exc), source_url=url, day_utc=target.isoformat())
                live_error = str(exc)
                events = []
                mode = "snapshot_fallback"
        else:
            events = []
            mode = "snapshot"
        if source == "snapshot" or (mode == "snapshot_fallback" and not events):
            try:
                with self._db() as db:
                    rows = db.execute("SELECT * FROM events WHERE event_date_utc=? ORDER BY origin_time_utc", (target.isoformat(),)).fetchall()
                    events = [dict(x) for x in rows]
            except Exception as exc:
                return error("no_evidence", "Live catalog and local snapshot are unavailable", live_error=live_error, snapshot_error=str(exc), day_utc=target.isoformat())
        filtered = self._filter(events, min_magnitude, max_magnitude, min_depth_km, max_depth_km)
        result = {
            "ok": True,
            "day_utc": target.isoformat(),
            "timezone": "UTC",
            "earthquake_count": len(filtered),
            "unfiltered_count": len(events),
            "filters": {"min_magnitude": min_magnitude, "max_magnitude": max_magnitude, "min_depth_km": min_depth_km, "max_depth_km": max_depth_km},
            "is_partial_day": target == self.now_fn().date(),
            "evidence_mode": mode,
            "source_url": url,
            "retrieved_at_utc": self.now_fn().isoformat().replace("+00:00", "Z"),
        }
        if live_error:
            result["live_error"] = live_error
        return result

    @staticmethod
    def _filter(events: Iterable[dict], min_mag=None, max_mag=None, min_depth=None, max_depth=None) -> list[dict]:
        result = []
        for event in events:
            mag, dep = event.get("magnitude_mw"), event.get("depth_km")
            if min_mag is not None and (mag is None or mag < min_mag): continue
            if max_mag is not None and (mag is None or mag > max_mag): continue
            if min_depth is not None and (dep is None or dep < min_depth): continue
            if max_depth is not None and (dep is None or dep > max_depth): continue
            result.append(event)
        return result

    def search_events(
        self,
        start: str,
        end: str | None = None,
        min_magnitude: float | None = None,
        max_magnitude: float | None = None,
        min_depth_km: float | None = None,
        max_depth_km: float | None = None,
        source: str = "auto",
        limit: int = 500,
        order: str = "time_asc",
        force_refresh: bool = False,
    ) -> dict:
        try:
            start_day, end_day = resolve_utc_day(start, self.now_fn()), resolve_utc_day(end or start, self.now_fn())
        except ValueError:
            return error("invalid_date", "Use today, yesterday, or YYYY-MM-DD")
        if end_day < start_day:
            return error("invalid_range", "end must be on or after start")
        span = (end_day - start_day).days + 1
        if source not in {"auto", "live", "snapshot"}:
            return error("invalid_source", "source must be auto, live, or snapshot")
        use_live = source == "live" or (source == "auto" and span <= MAX_LIVE_RANGE_DAYS)
        events: list[dict] = []
        source_urls: list[str] = []
        mode = "live" if use_live else "snapshot"
        if use_live:
            if span > MAX_LIVE_RANGE_DAYS:
                return error("live_range_too_large", f"Live daily retrieval is limited to {MAX_LIVE_RANGE_DAYS} days; use snapshot for longer ranges", days=span)
            failures = []
            for offset in range(span):
                day = start_day + timedelta(days=offset)
                try:
                    rows, url = self._live_day(day, force_refresh)
                    events.extend(rows); source_urls.append(url)
                except Exception as exc:
                    failures.append({"day_utc": day.isoformat(), "error": str(exc)})
            if failures and source == "live":
                return error("incomplete_live_range", "One or more daily files could not be retrieved", failures=failures)
            if failures:
                mode = "mixed_live_snapshot"
                missing = [x["day_utc"] for x in failures]
                try:
                    placeholders = ",".join("?" for _ in missing)
                    with self._db() as db:
                        events.extend(dict(x) for x in db.execute(f"SELECT * FROM events WHERE event_date_utc IN ({placeholders})", missing))
                except Exception as exc:
                    return error("incomplete_evidence", "Some live days failed and snapshot fallback was unavailable", failures=failures, snapshot_error=str(exc))
        else:
            try:
                with self._db() as db:
                    events = [dict(x) for x in db.execute("SELECT * FROM events WHERE event_date_utc BETWEEN ? AND ?", (start_day.isoformat(), end_day.isoformat()))]
            except Exception as exc:
                return error("snapshot_unavailable", str(exc))
        events = self._filter(events, min_magnitude, max_magnitude, min_depth_km, max_depth_km)
        order_key = "magnitude_mw" if order.startswith("magnitude") else "origin_time_utc"
        reverse = order.endswith("desc")
        events.sort(key=lambda x: (x.get(order_key) is None, x.get(order_key)), reverse=reverse)
        total = len(events); limit = max(1, min(int(limit), 5000))
        return {
            "ok": True,
            "start_day_utc": start_day.isoformat(), "end_day_utc": end_day.isoformat(), "timezone": "UTC",
            "total_matches": total, "returned": min(total, limit), "events": events[:limit],
            "evidence_mode": mode, "source_urls": source_urls or [str(self.db_path)],
            "retrieved_at_utc": self.now_fn().isoformat().replace("+00:00", "Z"),
        }

    def get_event(self, event_id: str, live_day: str | None = None) -> dict:
        events = []; mode = "snapshot"; source_url = str(self.db_path); focals = []
        if live_day:
            result = self.search_events(live_day, source="live", limit=5000)
            if result.get("ok"):
                events = [x for x in result["events"] if str(x.get("event_id")) == str(event_id)]
                mode = "live"; source_url = result["source_urls"][0]
        if not events:
            try:
                with self._db() as db:
                    events = [dict(row) for row in db.execute("SELECT * FROM events WHERE event_id=? ORDER BY origin_time_utc", (str(event_id),))]
                    focals = [dict(row) for row in db.execute("SELECT * FROM focal_mechanisms WHERE event_id=? ORDER BY origin_time_utc", (str(event_id),))]
            except Exception as exc:
                return error("snapshot_unavailable", str(exc))
        if not events:
            return error("event_not_found", str(event_id))
        return {"ok": True, "event_id": str(event_id), "solution_count": len(events), "events": events, "event": events[0], "focal_mechanism_count": len(focals), "focal_mechanisms": focals, "evidence_mode": mode, "source_url": source_url}

    def activity_summary(self, start: str, end: str | None = None, source: str = "auto") -> dict:
        found = self.search_events(start, end, source=source, limit=5000, order="time_asc")
        if not found.get("ok"):
            return found
        if found["total_matches"] > found["returned"]:
            return error("summary_limit", "Query returned more than 5,000 events; shorten the range or use daily/monthly snapshot summaries", total=found["total_matches"])
        events = found["events"]
        mags = [x["magnitude_mw"] for x in events if x.get("magnitude_mw") is not None]
        depths = [x["depth_km"] for x in events if x.get("depth_km") is not None]
        per_day = Counter(x["event_date_utc"] for x in events)
        largest = sorted(events, key=lambda x: x.get("magnitude_mw") if x.get("magnitude_mw") is not None else -999, reverse=True)[:10]
        return {
            "ok": True, "start_day_utc": found["start_day_utc"], "end_day_utc": found["end_day_utc"], "timezone": "UTC",
            "earthquake_count": len(events), "daily_counts": dict(sorted(per_day.items())),
            "magnitude": {"minimum": min(mags) if mags else None, "maximum": max(mags) if mags else None, "mean": sum(mags)/len(mags) if mags else None},
            "depth_km": {"minimum": min(depths) if depths else None, "maximum": max(depths) if depths else None, "mean": sum(depths)/len(depths) if depths else None},
            "largest_events": largest, "evidence_mode": found["evidence_mode"], "source_urls": found["source_urls"],
        }

    def arrivals(self, day: str, event_id: str | None = None, force_refresh: bool = False) -> dict:
        try:
            target = resolve_utc_day(day, self.now_fn())
        except ValueError:
            return error("invalid_date", "Use today, yesterday, or YYYY-MM-DD")
        url = f"{self.base_url}/ph2dtInputCatalog/ph2dtInputCatalog_{target:%Y%m%d}.dat"
        try:
            rows = parse_ph2dt(str(self._fetch(url, force_refresh=force_refresh)), url)
        except Exception as exc:
            return error("axial_unavailable", str(exc), source_url=url)
        if event_id:
            rows = [x for x in rows if str(x["event_id"]) == str(event_id)]
        return {"ok": True, "day_utc": target.isoformat(), "event_id": event_id, "total_events": len(rows), "events": rows, "evidence_mode": "live", "source_url": url}

    def focal_mechanisms(self, start: str, end: str | None = None, fault_type: str | None = None, source: str = "auto", limit: int = 500) -> dict:
        try:
            start_day, end_day = resolve_utc_day(start, self.now_fn()), resolve_utc_day(end or start, self.now_fn())
        except ValueError:
            return error("invalid_date", "Use today, yesterday, or YYYY-MM-DD")
        rows: list[dict]; mode: str; source_url: str
        source_url = f"{self.base_url}/FocalMechanisms/catalog/axial_focal_mechanisms.csv"
        if source == "live" or (source == "auto" and start_day >= date(2026, 3, 22)):
            try:
                rows = parse_focal_csv(str(self._fetch(source_url)), source_url); mode = "live"
            except Exception as exc:
                if source == "live": return error("axial_unavailable", str(exc), source_url=source_url)
                rows = []; mode = "snapshot_fallback"
        else:
            rows = []; mode = "snapshot"
        if not rows:
            try:
                with self._db() as db:
                    rows = [dict(x) for x in db.execute("SELECT * FROM focal_mechanisms WHERE substr(origin_time_utc,1,10) BETWEEN ? AND ?", (start_day.isoformat(), end_day.isoformat()))]
            except Exception as exc:
                return error("snapshot_unavailable", str(exc))
        rows = [x for x in rows if start_day.isoformat() <= str(x.get("origin_time_utc", ""))[:10] <= end_day.isoformat()]
        if fault_type:
            rows = [x for x in rows if str(x.get("fault_type", "")).casefold() == fault_type.casefold()]
        limit = max(1, min(int(limit), 5000))
        return {"ok": True, "start_day_utc": start_day.isoformat(), "end_day_utc": end_day.isoformat(), "fault_type": fault_type, "total_matches": len(rows), "returned": min(len(rows), limit), "focal_mechanisms": rows[:limit], "evidence_mode": mode, "source_url": source_url if mode == "live" else str(self.db_path)}

    def list_figures(self) -> dict:
        rows = [{"name": name, "kind": "current", "source_url": f"{self.base_url}/{path}"} for name, path in FIGURES.items()]
        rows.extend([
            {"name": "daily_caldera_map", "kind": "dated", "date_parameter": "YYYY-MM-DD", "url_pattern": f"{self.base_url}/mapCaldera/dailyCalderaMap_YYYYMMDD.jpg"},
            {"name": "daily_regional_map", "kind": "dated", "date_parameter": "YYYY-MM-DD", "url_pattern": f"{self.base_url}/mapRegional/dailyRegionalMap_YYYYMMDD.jpg"},
        ])
        return {"ok": True, "total": len(rows), "figures": rows}

    def focal_event_product(self, event_id: str, product: str = "details", output_path: str | None = None, force_refresh: bool = False) -> dict:
        product = product.casefold()
        if product not in {"details", "beachball", "map", "waveform"}:
            return error("invalid_product", "product must be details, beachball, map, or waveform")
        root = f"{self.base_url}/FocalMechanisms"
        urls = {
            "details": f"{root}/events/FM_{event_id}.html",
            "beachball": f"{root}/images/beachball_{event_id}.png",
            "map": f"{root}/images/map_{event_id}.png",
            "waveform": f"{root}/images/waveform_{event_id}.png",
        }
        metadata = []
        try:
            with self._db() as db:
                metadata = [dict(row) for row in db.execute("SELECT * FROM focal_mechanisms WHERE event_id=? ORDER BY origin_time_utc", (str(event_id),))]
        except Exception:
            pass
        if product == "details":
            try:
                page = str(self._fetch(urls["details"], force_refresh=force_refresh))
                page = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", page, flags=re.I|re.S)
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(page))).strip()
            except Exception as exc:
                return error("axial_unavailable", str(exc), source_url=urls["details"], event_id=str(event_id))
            return {"ok": True, "event_id": str(event_id), "focal_mechanisms": metadata, "page_text": text, "products": urls, "quality_warnings":["dLoc is preserved from the source but can be implausibly large for an Axial-local comparison; do not use it as an event-to-station distance."], "evidence_mode": "live", "source_url": urls["details"]}
        try:
            payload = bytes(self._fetch(urls[product], binary=True, force_refresh=force_refresh))
        except Exception as exc:
            return error("axial_unavailable", str(exc), source_url=urls[product], event_id=str(event_id))
        result = {"ok": True, "event_id": str(event_id), "product": product, "focal_mechanisms": metadata, "products": urls, "quality_warnings":["dLoc is preserved from the source but can be implausibly large for an Axial-local comparison; do not use it as an event-to-station distance."], "mime_type": "image/png", "byte_size": len(payload), "evidence_mode": "live", "source_url": urls[product], "_mcp_image": {"mimeType":"image/png", "data":base64.b64encode(payload).decode("ascii")}}
        if output_path:
            path=Path(output_path); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload); result["downloaded_to"]=str(path.resolve())
        return result

    def monthly_focal_summary(self, month: str, include_events: bool = False, limit: int = 500, source: str = "auto", force_refresh: bool = False) -> dict:
        if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month):
            return error("invalid_month", "month must be YYYY-MM")
        year, month_number = map(int, month.split("-"))
        last = calendar.monthrange(year, month_number)[1]
        start, end = f"{month}-01", f"{month}-{last:02d}"
        if source not in {"auto","live","snapshot"}: return error("invalid_source","source must be auto, live, or snapshot")
        try:
            with self._db() as db:
                snapshot_rows = [dict(row) for row in db.execute("SELECT * FROM focal_mechanisms WHERE substr(origin_time_utc,1,10) BETWEEN ? AND ? ORDER BY origin_time_utc", (start,end))]
        except Exception as exc:
            return error("snapshot_unavailable", str(exc))
        live_catalog_url=f"{self.base_url}/FocalMechanisms/catalog/axial_focal_mechanisms.csv"
        use_live=source=="live" or (source=="auto" and month >= "2026-03")
        rows=snapshot_rows; mode="snapshot"; live_error=None
        if use_live:
            try:
                live_rows=parse_focal_csv(str(self._fetch(live_catalog_url,force_refresh=force_refresh)),live_catalog_url)
                rows=[x for x in live_rows if start <= str(x.get("origin_time_utc",""))[:10] <= end]
                mode="live"
            except Exception as exc:
                if source=="live": return error("axial_unavailable",str(exc),source_url=live_catalog_url)
                live_error=str(exc); mode="snapshot_fallback"
        fault_types = Counter(str(x.get("fault_type") or "unknown") for x in rows)
        qualities = Counter(str(x.get("quality") or "unknown") for x in rows)
        page_url = f"{self.base_url}/FocalMechanisms/months/FM_{year:04d}{month_number:02d}.html"
        page_available = False; page_event_count = None
        try:
            page = str(self._fetch(page_url))
            count_match = re.search(r"<p>\s*([0-9,]+)\s+events\s*</p>", page, re.I)
            page_event_count = int(count_match.group(1).replace(",", "")) if count_match else None
            page_available = True
        except Exception:
            pass
        limit=max(1,min(int(limit),5000))
        result={"ok":True,"month_utc":month,"earthquake_focal_mechanism_count":len(rows),"snapshot_count":len(snapshot_rows),"fault_type_counts":dict(sorted(fault_types.items())),"quality_counts":dict(sorted(qualities.items())),"archive_page_available":page_available,"archive_page_event_count":page_event_count,"archive_page_url":page_url,"evidence_mode":mode,"source_url":live_catalog_url if mode=="live" else str(self.db_path)}
        if live_error: result["live_error"]=live_error
        if include_events:
            result.update({"returned":min(len(rows),limit),"events":rows[:limit]})
        return result

    def get_figure(self, name: str, day: str | None = None, output_path: str | None = None, force_refresh: bool = False) -> dict:
        if name in {"daily_caldera_map", "daily_regional_map"}:
            if not day: return error("date_required", f"{name} requires day")
            try: target = resolve_utc_day(day, self.now_fn())
            except ValueError: return error("invalid_date", "Use today, yesterday, or YYYY-MM-DD")
            folder, prefix = ("mapCaldera", "dailyCalderaMap") if name == "daily_caldera_map" else ("mapRegional", "dailyRegionalMap")
            url = f"{self.base_url}/{folder}/{prefix}_{target:%Y%m%d}.jpg"
        elif name in FIGURES:
            target = None; url = f"{self.base_url}/{FIGURES[name]}"
        else:
            return error("unknown_figure", name, available=sorted(list(FIGURES) + ["daily_caldera_map", "daily_regional_map"]))
        try: payload = bytes(self._fetch(url, binary=True, force_refresh=force_refresh))
        except Exception as exc: return error("axial_unavailable", str(exc), source_url=url)
        result = {"ok": True, "name": name, "day_utc": target.isoformat() if target else None, "mime_type": "image/jpeg", "byte_size": len(payload), "evidence_mode": "live", "source_url": url, "_mcp_image": {"mimeType": "image/jpeg", "data": base64.b64encode(payload).decode("ascii")}}
        if output_path:
            path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload); result["downloaded_to"] = str(path.resolve())
        return result

    def plot_events(self, start: str, end: str | None = None, source: str = "auto", output_path: str | None = None) -> dict:
        result = self.search_events(start, end, source=source, limit=5000)
        if not result.get("ok"): return result
        events = result["events"]
        if not events: return error("no_events", "No earthquakes matched the query")
        width, height, pad = 1000, 620, 70
        lons = [float(x["longitude"]) for x in events]; lats = [float(x["latitude"]) for x in events]
        lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
        if math.isclose(lo_x, hi_x): lo_x -= .01; hi_x += .01
        if math.isclose(lo_y, hi_y): lo_y -= .01; hi_y += .01
        circles = []
        for row in events:
            x = pad + (float(row["longitude"]) - lo_x) * (width-2*pad)/(hi_x-lo_x)
            y = height-pad-(float(row["latitude"])-lo_y)*(height-2*pad)/(hi_y-lo_y)
            mag = row.get("magnitude_mw"); radius = max(2.0, 2.5 + (float(mag) if mag is not None else 0)*2)
            circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="#db4437" fill-opacity="0.45"><title>{html.escape(str(row["event_id"]))} {html.escape(str(row["origin_time_utc"]))} Mw {html.escape(str(mag))}</title></circle>')
        title = html.escape(f"Axial Seamount earthquakes, {result['start_day_utc']} to {result['end_day_utc']} UTC (n={len(events)})")
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><text x="{pad}" y="35" font-family="sans-serif" font-size="21">{title}</text><rect x="{pad}" y="{pad}" width="{width-2*pad}" height="{height-2*pad}" fill="#eaf5fa" stroke="#334"/>{''.join(circles)}<text x="{pad}" y="{height-25}" font-family="sans-serif" font-size="13">Longitude {lo_x:.4f} to {hi_x:.4f}</text><text x="20" y="{height/2}" transform="rotate(-90 20 {height/2})" font-family="sans-serif" font-size="13">Latitude {lo_y:.4f} to {hi_y:.4f}</text></svg>'''
        payload = svg.encode()
        out = {"ok": True, "earthquake_count": len(events), "start_day_utc": result["start_day_utc"], "end_day_utc": result["end_day_utc"], "evidence_mode": result["evidence_mode"], "source_urls": result["source_urls"], "_mcp_image": {"mimeType":"image/svg+xml", "data":base64.b64encode(payload).decode("ascii")}}
        if output_path:
            path=Path(output_path); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload); out["downloaded_to"]=str(path.resolve())
        return out

    def question_context(self, question: str) -> dict:
        q = question.casefold()
        day = "yesterday" if "yesterday" in q else ("today" if "today" in q else None)
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", question)
        day = match.group(1) if match else day
        if day and any(word in q for word in ("how many", "count", "number of", "earthquake")):
            return {"ok": True, "question": question, "intent": "daily_earthquake_count", "result": self.count_events(day), "guidance": ["Dates and day boundaries are UTC.", "Today is a partial day; yesterday is complete once the site has processed all locations."]}
        return {"ok": True, "question": question, "intent": "general_axial_earthquake_query", "catalog_status": self.catalog_status(), "guidance": ["Use axial_count_events for one day.", "Use axial_search_events or axial_activity_summary for a date range.", "Use axial_get_figure when a source map, histogram, focal-mechanism, or RSAM image would support the answer."]}


TOOL_SCHEMAS = [
    {"name":"axial_catalog_status","description":"Read the live Axial catalog update time, location coverage, and waveform streaming status.","inputSchema":{"type":"object","properties":{"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_count_events","description":"Return the exact number of Axial earthquakes on a UTC day, including today, yesterday, or YYYY-MM-DD. Uses the live daily catalog by default.","inputSchema":{"type":"object","properties":{"day":{"type":"string","default":"yesterday"},"min_magnitude":{"type":"number"},"max_magnitude":{"type":"number"},"min_depth_km":{"type":"number"},"max_depth_km":{"type":"number"},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_search_events","description":"Retrieve normalized Axial earthquake events for a UTC day or date range, with magnitude and depth filters.","inputSchema":{"type":"object","required":["start"],"properties":{"start":{"type":"string"},"end":{"type":"string"},"min_magnitude":{"type":"number"},"max_magnitude":{"type":"number"},"min_depth_km":{"type":"number"},"max_depth_km":{"type":"number"},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"},"limit":{"type":"integer","default":500},"order":{"type":"string","enum":["time_asc","time_desc","magnitude_asc","magnitude_desc"],"default":"time_asc"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_get_event","description":"Get one Axial earthquake and any matching focal mechanism by event ID.","inputSchema":{"type":"object","required":["event_id"],"properties":{"event_id":{"type":"string"},"live_day":{"type":"string"}}}},
    {"name":"axial_activity_summary","description":"Summarize counts, magnitudes, depths, daily activity, and largest earthquakes in a UTC range.","inputSchema":{"type":"object","required":["start"],"properties":{"start":{"type":"string"},"end":{"type":"string"},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"}}}},
    {"name":"axial_arrivals","description":"Retrieve live station P/S picks from a daily Axial ph2dt catalog, optionally for one event ID.","inputSchema":{"type":"object","required":["day"],"properties":{"day":{"type":"string"},"event_id":{"type":"string"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_focal_mechanisms","description":"Retrieve Axial focal mechanisms by UTC range and optional fault type (N, R, S, or U).","inputSchema":{"type":"object","required":["start"],"properties":{"start":{"type":"string"},"end":{"type":"string"},"fault_type":{"type":"string"},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"},"limit":{"type":"integer","default":500}}}},
    {"name":"axial_list_figures","description":"List live Axial earthquake maps, histograms, focal-mechanism maps, and RSAM figures.","inputSchema":{"type":"object","properties":{}}},
    {"name":"axial_get_figure","description":"Fetch a current or dated Axial figure and return it as an MCP image.","inputSchema":{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"day":{"type":"string"},"output_path":{"type":"string"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_get_focal_event_product","description":"Retrieve an Axial focal-event detail page or its beachball, location map, or waveform plot.","inputSchema":{"type":"object","required":["event_id"],"properties":{"event_id":{"type":"string"},"product":{"type":"string","enum":["details","beachball","map","waveform"],"default":"details"},"output_path":{"type":"string"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_monthly_focal_summary","description":"Summarize one UTC month of Axial focal mechanisms and link its published monthly archive page when available.","inputSchema":{"type":"object","required":["month"],"properties":{"month":{"type":"string","description":"YYYY-MM"},"include_events":{"type":"boolean","default":False},"limit":{"type":"integer","default":500},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"axial_plot_events","description":"Create an SVG map from exact live or snapshot Axial earthquake events.","inputSchema":{"type":"object","required":["start"],"properties":{"start":{"type":"string"},"end":{"type":"string"},"source":{"type":"string","enum":["auto","live","snapshot"],"default":"auto"},"output_path":{"type":"string"}}}},
    {"name":"axial_question_context","description":"Route a natural-language Axial earthquake question to current status or an exact daily count.","inputSchema":{"type":"object","required":["question"],"properties":{"question":{"type":"string"}}}},
]


def dispatch(toolkit: AxialToolkit, name: str, arguments: dict) -> dict:
    mapping = {
        "axial_catalog_status": toolkit.catalog_status,
        "axial_count_events": toolkit.count_events,
        "axial_search_events": toolkit.search_events,
        "axial_get_event": toolkit.get_event,
        "axial_activity_summary": toolkit.activity_summary,
        "axial_arrivals": toolkit.arrivals,
        "axial_focal_mechanisms": toolkit.focal_mechanisms,
        "axial_list_figures": toolkit.list_figures,
        "axial_get_figure": toolkit.get_figure,
        "axial_get_focal_event_product": toolkit.focal_event_product,
        "axial_monthly_focal_summary": toolkit.monthly_focal_summary,
        "axial_plot_events": toolkit.plot_events,
        "axial_question_context": toolkit.question_context,
    }
    if name not in mapping:
        return error("unknown_tool", name)
    try:
        return mapping[name](**arguments)
    except TypeError as exc:
        return error("invalid_arguments", str(exc), tool=name)
