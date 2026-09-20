#!/usr/bin/env python3
"""Credential-free Nereus tools for RCA Graph-RAG and live operations."""

from __future__ import annotations

import base64
import hashlib
import html
import ipaddress
import json
import math
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://nereus.ooirsn.uw.edu"
INTERVALS = {"MINUTE", "HOUR", "DAY", "WEEK", "MONTH"}
REFDES_RE = re.compile(r"\bRS\d{2}[A-Z0-9]{4}-[A-Z0-9]+-\d{2}-[A-Z0-9]+\b", re.I)
NODE_RE = re.compile(r"\b(?:DP|LJ|LV|MJ|PN)\d{2}[A-Z]\b", re.I)
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
NETWORK_DETAIL_KEYS = {
    "ip", "ipaddress", "ipv4", "ipv6", "mac", "macaddress", "gateway",
    "subnet", "netmask", "dns", "dnsserver", "hostname", "servername",
    "serveraddress", "sshhost", "snmpcommunity",
}


def error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


def _without_network_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _without_network_details(v)
            for k, v in value.items()
            if re.sub(r"[^a-z0-9]", "", str(k).casefold()) not in NETWORK_DETAIL_KEYS
        }
    if isinstance(value, list):
        return [_without_network_details(v) for v in value]
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            raw = match.group(0)
            try:
                address = ipaddress.ip_address(raw)
            except ValueError:
                return raw
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return "[REDACTED PRIVATE NETWORK ADDRESS]"
            return raw
        return IPV4_RE.sub(replace, value)
    return value


class NereusToolkit:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        query_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        snapshot_dir: str | Path | None = None,
        timeout: int = 45,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.graphql_url = f"{self.base_url}/hasura/v1/graphql"
        self.query_dir = Path(query_dir) if query_dir else Path(__file__).resolve().parent / "queries"
        self.cache_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "rcn-agent-nereus-cache"
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds

    def _query(self, operation: str) -> str:
        path = self.query_dir / f"{operation}.graphql"
        if not path.exists():
            raise FileNotFoundError(f"Missing allowlisted query document: {path}")
        return path.read_text(encoding="utf-8")

    def _snapshot_name(self, operation: str) -> str | None:
        return {
            "HelmQuery": "helm.json",
            "ReportsPageQuery": "reports.json",
            "EngineeringQuery": "engineering.json",
        }.get(operation)

    def execute(self, operation: str, variables: dict | None = None, force_refresh: bool = False) -> dict:
        variables = variables or {}
        query = self._query(operation)
        payload = {"operationName": operation, "variables": variables, "query": query}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        cache = self.cache_dir / f"{operation}-{key[:16]}.json"
        if not force_refresh and cache.exists() and time.time() - cache.stat().st_mtime <= self.cache_ttl_seconds:
            stored = json.loads(cache.read_text(encoding="utf-8"))
            return {"ok": True, "data": _without_network_details(stored["data"]), "evidence_mode": "live_cache", "source_url": self.graphql_url}
        request = urllib.request.Request(
            self.graphql_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "RCN-Agent-Nereus/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("errors"):
                return error("graphql_error", "Nereus rejected the operation", errors=result["errors"], operation=operation)
            safe_data = _without_network_details(result["data"])
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"data": safe_data}), encoding="utf-8")
            return {"ok": True, "data": safe_data, "evidence_mode": "live", "source_url": self.graphql_url}
        except Exception as exc:
            snapshot_name = self._snapshot_name(operation)
            snapshot = self.snapshot_dir / snapshot_name if self.snapshot_dir and snapshot_name else None
            if snapshot and snapshot.exists():
                stored = json.loads(snapshot.read_text(encoding="utf-8"))
                data = _without_network_details(stored.get("data", stored))
                return {"ok": True, "data": data, "evidence_mode": "snapshot_fallback", "live_error": str(exc), "source_url": self.graphql_url, "snapshot": str(snapshot)}
            return error("nereus_unavailable", str(exc), operation=operation, source_url=self.graphql_url)

    def health(self) -> dict:
        result = self.execute("AppLayoutQuery", force_refresh=True)
        if not result.get("ok"):
            return result
        return {"ok": True, "service": result["data"].get("info"), "evidence_mode": result["evidence_mode"], "source_url": self.base_url}

    def inventory(self, include_non_rca: bool = False, include_network_details: bool = False, force_refresh: bool = False) -> dict:
        result = self.execute("HelmQuery", force_refresh=force_refresh)
        if not result.get("ok"):
            return result
        instruments = result["data"].get("instruments", [])
        nodes = result["data"].get("nodes", [])
        if not include_non_rca:
            instruments = [x for x in instruments if str(x.get("designator", "")).startswith("RS")]
            nodes = [x for x in nodes if str(x.get("site", "")).startswith("RS")]
        # Kept as a Python-call compatibility argument; network details are
        # always excluded and the MCP schema does not expose this switch.
        instruments, nodes = _without_network_details(instruments), _without_network_details(nodes)
        return {
            "ok": True,
            "scope": "all arrays" if include_non_rca else "Regional Cabled Array only",
            "instrument_count": len(instruments),
            "node_count": len(nodes),
            "instruments": instruments,
            "nodes": nodes,
            "evidence_mode": result["evidence_mode"],
            "source_url": result["source_url"],
            "network_details_excluded": True,
        }

    def instrument_status(self, designator: str, include_network_details: bool = False) -> dict:
        inv = self.inventory(include_network_details=include_network_details)
        if not inv.get("ok"):
            return inv
        wanted = designator.casefold()
        matches = [x for x in inv["instruments"] if wanted in str(x.get("designator", "")).casefold()]
        return {"ok": True, "query": designator, "total_matches": len(matches), "instruments": matches, "evidence_mode": inv["evidence_mode"], "source_url": inv["source_url"]}

    def node_status(self, designator_or_site: str, include_network_details: bool = False) -> dict:
        inv = self.inventory(include_network_details=include_network_details)
        if not inv.get("ok"):
            return inv
        wanted = designator_or_site.casefold()
        matches = [x for x in inv["nodes"] if wanted in str(x.get("designator", "")).casefold() or wanted in str(x.get("site", "")).casefold()]
        return {"ok": True, "query": designator_or_site, "total_matches": len(matches), "nodes": matches, "evidence_mode": inv["evidence_mode"], "source_url": inv["source_url"]}

    def operational_notes(self, query: str | None = None, cutoff: str | None = None, limit: int = 100) -> dict:
        cutoff = cutoff or (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        result = self.execute("ReportsPageQuery", {"cutoff": cutoff})
        if not result.get("ok"):
            return result
        rca_designators = {x["designator"] for x in result["data"].get("instruments", []) if x.get("designator", "").startswith("RS")}
        notes = []
        for note in result["data"].get("notes", []):
            linked = [c.get("instrument", {}).get("designator") for c in note.get("instrumentConnections", [])]
            linked = [x for x in linked if x in rca_designators]
            if not linked:
                continue
            row = _without_network_details({**note, "referenceDesignators": linked})
            hay = json.dumps(row, ensure_ascii=False).casefold()
            if query and query.casefold() not in hay:
                continue
            notes.append(row)
        limit = max(1, min(int(limit), 500))
        return {"ok": True, "query": query, "cutoff": cutoff, "total_matches": len(notes), "returned": min(len(notes), limit), "notes": notes[:limit], "evidence_mode": result["evidence_mode"], "source_url": result["source_url"]}

    def engineering_telemetry(self, node: str | None = None) -> dict:
        result = self.execute("EngineeringQuery")
        if not result.get("ok"):
            return result
        inv = self.inventory()
        if not inv.get("ok"):
            return inv
        rca_nodes = {x["designator"] for x in inv["nodes"]}
        rows = [x for x in result["data"].get("engineering", {}).get("nodeStatuses", []) if x.get("designator") in rca_nodes]
        if node:
            rows = [x for x in rows if node.casefold() in str(x.get("designator", "")).casefold()]
        return {"ok": True, "query": node, "total_matches": len(rows), "node_statuses": _without_network_details(rows), "evidence_mode": result["evidence_mode"], "source_url": result["source_url"], "network_details_excluded": True}

    def _resolve_entity(self, entity_type: str, designator: str) -> dict | None:
        if entity_type == "instrument":
            result = self.instrument_status(designator)
            rows = result.get("instruments", [])
            return next((x for x in rows if x.get("designator", "").casefold() == designator.casefold()), rows[0] if rows else None)
        result = self.node_status(designator)
        rows = result.get("nodes", [])
        return next((x for x in rows if x.get("designator", "").casefold() == designator.casefold()), rows[0] if rows else None)

    def history(self, entity_type: str, designator: str, kind: str = "status", days: int = 30, interval: str = "DAY", started_at: str | None = None) -> dict:
        if entity_type not in {"instrument", "node"}:
            return error("invalid_entity_type", "entity_type must be instrument or node")
        interval = interval.upper()
        if interval not in INTERVALS:
            return error("invalid_interval", f"interval must be one of {sorted(INTERVALS)}")
        days = max(1, min(int(days), 3650))
        entity = self._resolve_entity(entity_type, designator)
        if not entity:
            return error("entity_not_found", designator, entity_type=entity_type)
        prefix = "PowerCurrentChart" if kind == "power" else "StatusHistoryChart"
        operation = f"{prefix}{entity_type.title()}Query"
        variables = {"id": entity["id"], "days": days, "interval": interval, "startedAt": started_at}
        result = self.execute(operation, variables)
        if not result.get("ok"):
            return result
        return {"ok": True, "entity_type": entity_type, "designator": entity.get("designator"), "entity_id": entity["id"], "kind": kind, "days": days, "interval": interval, "started_at": started_at, "statistics": _without_network_details(result["data"].get("statistics", {})), "evidence_mode": result["evidence_mode"], "source_url": result["source_url"], "network_details_excluded": True}

    def plot_power_history(self, entity_type: str, designator: str, days: int = 30, interval: str = "DAY", started_at: str | None = None, output_path: str | None = None) -> dict:
        result = self.history(entity_type, designator, "power", days, interval, started_at)
        if not result.get("ok"):
            return result
        rows = result["statistics"].get("history", [])
        if not rows:
            return error("no_history", "Nereus returned no power-current history", designator=designator)
        values = [float(x["current"]) for x in rows if x.get("current") is not None]
        if not values:
            return error("no_numeric_history", "Power-current history has no numeric values", designator=designator)
        width, height, pad = 1000, 420, 60
        lo, hi = min(values), max(values)
        if math.isclose(lo, hi): hi = lo + 1
        points = []
        for i, row in enumerate(rows):
            if row.get("current") is None: continue
            x = pad + i * (width - 2 * pad) / max(1, len(rows) - 1)
            y = height - pad - (float(row["current"]) - lo) * (height - 2 * pad) / (hi - lo)
            points.append(f"{x:.1f},{y:.1f}")
        title = html.escape(f"Nereus power current: {result['designator']} ({days} days, {interval})")
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="{pad}" y="30" font-family="sans-serif" font-size="20">{title}</text>
<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#333"/><line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#333"/>
<text x="8" y="{pad+5}" font-family="sans-serif" font-size="13">{hi:.3g} A</text><text x="8" y="{height-pad+5}" font-family="sans-serif" font-size="13">{lo:.3g} A</text>
<polyline points="{' '.join(points)}" fill="none" stroke="#1769aa" stroke-width="2"/>
<text x="{pad}" y="{height-15}" font-family="sans-serif" font-size="12">{html.escape(str(rows[0].get('date','')))}</text><text x="{width-pad}" y="{height-15}" text-anchor="end" font-family="sans-serif" font-size="12">{html.escape(str(rows[-1].get('date','')))}</text>
</svg>'''
        payload = svg.encode("utf-8")
        out = {k: v for k, v in result.items() if k != "statistics"}
        out.update({"ok": True, "points": len(points), "byte_size": len(payload), "_mcp_image": {"mimeType": "image/svg+xml", "data": base64.b64encode(payload).decode("ascii")}})
        if output_path:
            target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(payload); out["downloaded_to"] = str(target.resolve())
        return out

    def question_context(self, question: str, limit: int = 20) -> dict:
        ref = REFDES_RE.search(question)
        node = NODE_RE.search(question)
        identifier = ref.group(0).upper() if ref else (node.group(0).upper() if node else question)
        instruments = self.instrument_status(identifier)
        nodes = self.node_status(identifier)
        notes = self.operational_notes(identifier, limit=limit)
        engineering = self.engineering_telemetry(node.group(0).upper() if node else None) if node else {"ok": True, "node_statuses": [], "reason": "No node designator detected"}
        return {"ok": True, "question": question, "resolved_identifier": identifier, "instruments": instruments, "nodes": nodes, "operational_notes": notes, "engineering_telemetry": engineering, "guidance": ["Treat status and telemetry as time-sensitive observations.", "Report checkedAt, retrievedAt, startedAt, or endedAt timestamps with conclusions.", "Use Nereus for operational evidence and the local graph for stable scientific context."]}


TOOL_SCHEMAS = [
    {"name":"nereus_health","description":"Check the public Nereus service without credentials.","inputSchema":{"type":"object","properties":{}}},
    {"name":"nereus_inventory","description":"Retrieve the current RCA instrument and node inventory and statuses. Private network details are always excluded.","inputSchema":{"type":"object","properties":{"include_non_rca":{"type":"boolean","default":False},"force_refresh":{"type":"boolean","default":False}}}},
    {"name":"nereus_instrument_status","description":"Retrieve current operational, data, file, ping, GFD, power, asset, and deployment information for an RCA instrument. Private network details are always excluded.","inputSchema":{"type":"object","required":["designator"],"properties":{"designator":{"type":"string"}}}},
    {"name":"nereus_node_status","description":"Retrieve current status, power, asset, and deployment information for an RCA infrastructure node. Private network details are always excluded.","inputSchema":{"type":"object","required":["designator_or_site"],"properties":{"designator_or_site":{"type":"string"}}}},
    {"name":"nereus_operational_notes","description":"Retrieve RCA operational notes from Nereus for a designator, site, category, or text query.","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"cutoff":{"type":"string"},"limit":{"type":"integer","default":100}}}},
    {"name":"nereus_engineering_telemetry","description":"Retrieve live RCA node engineering telemetry such as voltage, current, temperature, pressure, humidity, state, and GFD values.","inputSchema":{"type":"object","properties":{"node":{"type":"string"}}}},
    {"name":"nereus_status_history","description":"Retrieve instrument or node operational and activity-status history.","inputSchema":{"type":"object","required":["entity_type","designator"],"properties":{"entity_type":{"type":"string","enum":["instrument","node"]},"designator":{"type":"string"},"days":{"type":"integer","default":30},"interval":{"type":"string","default":"DAY"},"started_at":{"type":"string"}}}},
    {"name":"nereus_power_history","description":"Retrieve instrument or node power-current history.","inputSchema":{"type":"object","required":["entity_type","designator"],"properties":{"entity_type":{"type":"string","enum":["instrument","node"]},"designator":{"type":"string"},"days":{"type":"integer","default":30},"interval":{"type":"string","default":"DAY"},"started_at":{"type":"string"}}}},
    {"name":"nereus_plot_power_history","description":"Generate an SVG plot from live Nereus power-current history and return it as MCP image content.","inputSchema":{"type":"object","required":["entity_type","designator"],"properties":{"entity_type":{"type":"string","enum":["instrument","node"]},"designator":{"type":"string"},"days":{"type":"integer","default":30},"interval":{"type":"string","default":"DAY"},"started_at":{"type":"string"},"output_path":{"type":"string"}}}},
    {"name":"nereus_question_context","description":"Resolve an operational question into live Nereus instrument, node, note, and engineering evidence.","inputSchema":{"type":"object","required":["question"],"properties":{"question":{"type":"string"},"limit":{"type":"integer","default":20}}}},
]


def dispatch(toolkit: NereusToolkit, name: str, arguments: dict) -> dict:
    calls = {
        "nereus_health": lambda: toolkit.health(),
        "nereus_inventory": lambda: toolkit.inventory(**arguments),
        "nereus_instrument_status": lambda: toolkit.instrument_status(**arguments),
        "nereus_node_status": lambda: toolkit.node_status(**arguments),
        "nereus_operational_notes": lambda: toolkit.operational_notes(**arguments),
        "nereus_engineering_telemetry": lambda: toolkit.engineering_telemetry(**arguments),
        "nereus_status_history": lambda: toolkit.history(kind="status", **arguments),
        "nereus_power_history": lambda: toolkit.history(kind="power", **arguments),
        "nereus_plot_power_history": lambda: toolkit.plot_power_history(**arguments),
        "nereus_question_context": lambda: toolkit.question_context(**arguments),
    }
    if name not in calls: return error("unknown_tool", name)
    try: return calls[name]()
    except urllib.error.HTTPError as exc: return error("http_error", str(exc), status=exc.code, url=exc.url)
    except Exception as exc: return error(type(exc).__name__, str(exc))
