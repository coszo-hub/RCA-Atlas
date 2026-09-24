"""OOI ERDDAP: public, no login. Info for variables/coverage; tabledap CSV for readings."""
from __future__ import annotations

import csv
import io
import math
import urllib.parse
from datetime import datetime, timezone

import httpx

from .errors import UpstreamError

BASE = "https://erddap.dataexplorer.oceanobservatories.org/erddap"
SKIP = {"time", "latitude", "longitude", "z", "depth", "station", "deployment", "id"}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ErddapClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    def _get(self, url: str) -> httpx.Response:
        try:
            return self.http.get(url)
        except httpx.TimeoutException:
            raise UpstreamError("ERDDAP", "ERDDAP did not respond in time", 504) from None
        except httpx.HTTPError as exc:
            raise UpstreamError("ERDDAP", f"ERDDAP request failed: {exc}") from None

    def variables(self, dataset_id: str) -> dict:
        resp = self._get(f"{BASE}/info/{dataset_id}/index.json")
        if resp.status_code != 200:
            raise UpstreamError("ERDDAP", f"ERDDAP info returned HTTP {resp.status_code}")
        try:
            rows = resp.json()["table"]["rows"]
        except (ValueError, KeyError, TypeError):
            raise UpstreamError("ERDDAP", "unexpected ERDDAP info response") from None
        attrs: dict[tuple[str, str], str] = {(r[1], r[2]): r[4] for r in rows if r[0] == "attribute"}
        names = [r[1] for r in rows if r[0] == "variable"]
        variables = [{"name": n, "units": attrs.get((n, "units")), "longName": attrs.get((n, "long_name"))}
                     for n in names if n not in SKIP and "_qc_" not in n]
        return {"variables": variables, "coverage": {"start": attrs.get(("NC_GLOBAL", "time_coverage_start")),
                                                     "end": attrs.get(("NC_GLOBAL", "time_coverage_end"))}}

    def csv_url(self, dataset_id: str, var: str, start: datetime, end: datetime) -> str:
        q = f"time,{var}&time>={_iso(start)}&time<={_iso(end)}"
        return f"{BASE}/tabledap/{dataset_id}.csv?" + urllib.parse.quote(q, safe=",&=:")

    def series(self, dataset_id: str, var: str, start: datetime, end: datetime) -> dict:
        resp = self._get(self.csv_url(dataset_id, var, start, end))
        if resp.status_code == 404 and "no matching results" in resp.text:
            return {"units": None, "times": [], "values": []}
        if resp.status_code != 200:
            raise UpstreamError("ERDDAP", f"ERDDAP returned HTTP {resp.status_code}")
        rows = list(csv.reader(io.StringIO(resp.text)))
        if len(rows) < 2 or rows[0][:2] != ["time", var]:
            raise UpstreamError("ERDDAP", "unexpected ERDDAP CSV response")
        times, values = [], []
        for row in rows[2:]:
            try:
                v = float(row[1])
            except (ValueError, IndexError):
                continue
            if math.isnan(v):
                continue
            t = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            times.append(int(t.timestamp() * 1000))
            values.append(v)
        return {"units": rows[1][1] or None, "times": times, "values": values}
