#!/usr/bin/env python3
"""Read-only QA/QC tools for an agentic Graph-RAG system.

The module uses the public QAQC dashboard proxy for current evidence and the
local instrument graph for stable context. Plot generation is available only
as an explicit, disabled-by-default optional backend.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://ec2.qaqc.ooi-rca.net"
DEFAULT_INDEX_PATH = "QAQC_plots/index.json"
MAX_INLINE_IMAGE_BYTES = 15 * 1024 * 1024
REFDES_RE = re.compile(r"\b(?:RS|CE)\d{2}[A-Z0-9]{4}-[A-Z0-9]+-\d{2}-[A-Z0-9]+\b", re.I)
SITE_RE = re.compile(r"\b(?:RS|CE)\d{2}[A-Z0-9]{4}\b", re.I)


def _jsonable_error(kind: str, message: str, **details: Any) -> dict:
    return {"ok": False, "error": {"type": kind, "message": message, **details}}


class QAQCToolkit:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache_path: str | Path | None = None,
        instrument_root: str | Path | None = None,
        hitl_snapshot: str | Path | None = None,
        timeout: int = 30,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.index_url = f"{self.base_url}/{DEFAULT_INDEX_PATH}"
        self.cache_path = Path(cache_path) if cache_path else Path(tempfile.gettempdir()) / "rcn-agent-qaqc-index.json"
        self.instrument_root = Path(instrument_root) if instrument_root else None
        self.hitl_snapshot = Path(hitl_snapshot) if hitl_snapshot else None
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._index_memory: list[str] | None = None

    def _request(self, url: str, method: str = "GET") -> bytes:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": "RCN-Agent-QAQC/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return response.read()

    def _request_json(self, url: str) -> Any:
        return json.loads(self._request(url).decode("utf-8"))

    def get_index(self, force_refresh: bool = False) -> list[str]:
        if self._index_memory is not None and not force_refresh:
            return self._index_memory
        if not force_refresh and self.cache_path.exists() and time.time() - self.cache_path.stat().st_mtime <= self.cache_ttl_seconds:
            self._index_memory = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return self._index_memory
        try:
            data = self._request_json(self.index_url)
            if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
                raise ValueError("Plot index is not a string list")
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(data), encoding="utf-8")
            self._index_memory = data
            return data
        except Exception:
            if self.cache_path.exists():
                self._index_memory = json.loads(self.cache_path.read_text(encoding="utf-8"))
                return self._index_memory
            raise

    @staticmethod
    def parse_plot_path(path: str) -> dict | None:
        filename = path.rsplit("/", 1)[-1]
        stem = re.sub(r"\.(?:png|svg)$", "", filename, flags=re.I)
        tokens = stem.split("_")
        if len(tokens) < 4:
            return None
        data_range, overlay, time_span = tokens[-1], tokens[-2], tokens[-3]
        middle = tokens[1:-3]
        depth = ""
        if middle and (middle[-1].endswith("meters") or middle[-1].endswith("profile")):
            depth = middle.pop()
        refdes = tokens[0]
        return {
            "path": path,
            "url": f"{DEFAULT_BASE_URL}/QAQC_plots/{urllib.parse.quote(path, safe='/')}",
            "site": path.split("/", 1)[0] if "/" in path else refdes[:8],
            "reference_designator": refdes,
            "variable": "_".join(middle),
            "depth_or_profile": depth,
            "time_span": time_span,
            "overlay": overlay,
            "data_range": data_range,
            "format": filename.rsplit(".", 1)[-1].lower(),
        }

    def search_plots(
        self,
        reference_designator: str | None = None,
        site: str | None = None,
        variable: str | None = None,
        time_span: str | None = None,
        overlay: str | None = None,
        data_range: str | None = None,
        limit: int = 20,
        include_non_rca: bool = False,
    ) -> dict:
        limit = max(1, min(int(limit), 200))
        filters = {
            "reference_designator": reference_designator,
            "site": site,
            "variable": variable,
            "time_span": time_span,
            "overlay": overlay,
            "data_range": data_range,
        }
        matches = []
        for path in self.get_index():
            if not include_non_rca and not path.startswith("RS"):
                continue
            record = self.parse_plot_path(path)
            if not record:
                continue
            record["url"] = f"{self.base_url}/QAQC_plots/{urllib.parse.quote(path, safe='/')}"
            good = True
            score = 0
            for key, wanted in filters.items():
                if not wanted:
                    continue
                actual = str(record[key])
                if wanted.casefold() not in actual.casefold():
                    good = False
                    break
                score += 3 if wanted.casefold() == actual.casefold() else 1
            if good:
                record["match_score"] = score
                matches.append(record)
        matches.sort(key=lambda x: (-x["match_score"], x["reference_designator"], x["variable"], x["path"]))
        return {"ok": True, "filters": filters, "total_matches": len(matches), "returned": min(len(matches), limit), "plots": matches[:limit], "catalog_source": self.index_url}

    def catalog_summary(self, include_non_rca: bool = False) -> dict:
        sites, refs, variables, spans, overlays, ranges = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
        parsed = 0
        for path in self.get_index():
            if not include_non_rca and not path.startswith("RS"):
                continue
            record = self.parse_plot_path(path)
            if not record:
                continue
            parsed += 1
            sites[record["site"]] += 1; refs[record["reference_designator"]] += 1
            variables[record["variable"]] += 1; spans[record["time_span"]] += 1
            overlays[record["overlay"]] += 1; ranges[record["data_range"]] += 1
        return {
            "ok": True,
            "scope": "all dashboard arrays" if include_non_rca else "Regional Cabled Array paths only",
            "plot_count": parsed,
            "site_counts": dict(sites.most_common()),
            "reference_designator_count": len(refs),
            "top_reference_designators": dict(refs.most_common(50)),
            "variable_count": len(variables),
            "top_variables": dict(variables.most_common(100)),
            "time_spans": dict(spans), "overlays": dict(overlays), "data_ranges": dict(ranges),
            "catalog_source": self.index_url,
        }

    def get_plot(
        self,
        path: str,
        output_path: str | Path | None = None,
        include_image: bool = False,
    ) -> dict:
        if path not in set(self.get_index()):
            return _jsonable_error("plot_not_found", "The path is not present in the current dashboard index", path=path)
        url = f"{self.base_url}/QAQC_plots/{urllib.parse.quote(path, safe='/')}"
        metadata = self.parse_plot_path(path)
        if metadata:
            metadata["url"] = url
        result = {"ok": True, "path": path, "url": url, "metadata": metadata}
        if output_path or include_image:
            payload = self._request(url)
            if len(payload) > MAX_INLINE_IMAGE_BYTES and include_image:
                return _jsonable_error(
                    "image_too_large",
                    f"Plot is larger than the {MAX_INLINE_IMAGE_BYTES} byte inline limit",
                    path=path,
                    byte_size=len(payload),
                    url=url,
                )
            result["byte_size"] = len(payload)
        if output_path:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            result["downloaded_to"] = str(target.resolve())
        if include_image:
            suffix = Path(path).suffix.lower()
            mime_type = "image/svg+xml" if suffix == ".svg" else "image/png"
            result["_mcp_image"] = {
                "data": base64.b64encode(payload).decode("ascii"),
                "mimeType": mime_type,
            }
        return result

    def list_hitl_notes(self, query: str | None = None, include_non_rca: bool = False, limit: int = 100) -> dict:
        index_url = f"{self.base_url}/HITL_notes/index.json"
        rows = []
        live_error = None
        try:
            filenames = self._request_json(index_url)
            for filename in filenames:
                text = self._request(f"{self.base_url}/HITL_notes/{urllib.parse.quote(filename)}").decode("utf-8", errors="replace")
                for row in csv.reader(io.StringIO(text)):
                    if row:
                        rows.append({"reference_designator": row[0].strip(), "note": ",".join(row[1:]).strip(), "source_file": filename, "source_url": f"{self.base_url}/HITL_notes/{urllib.parse.quote(filename)}"})
            evidence_mode = "live"
        except Exception as exc:
            live_error = str(exc)
            if not self.hitl_snapshot or not self.hitl_snapshot.exists():
                return _jsonable_error("hitl_unavailable", live_error, index_source=index_url)
            rows = [json.loads(line) for line in self.hitl_snapshot.read_text(encoding="utf-8").splitlines() if line.strip()]
            evidence_mode = "snapshot_fallback"
        filtered = []
        for row in rows:
            refdes, note, filename = row.get("reference_designator", ""), row.get("note", ""), row.get("source_file", "")
            if not include_non_rca and not refdes.startswith("RS"):
                continue
            if query and query.casefold() not in filename.casefold() and query.casefold() not in refdes.casefold() and query.casefold() not in note.casefold():
                continue
            filtered.append(row)
        consolidated = {}
        for row in filtered:
            key = (row.get("reference_designator", ""), row.get("note", ""))
            if key not in consolidated:
                consolidated[key] = {**row, "source_files": [], "source_urls": []}
            if row.get("source_file") not in consolidated[key]["source_files"]:
                consolidated[key]["source_files"].append(row.get("source_file"))
            if row.get("source_url") not in consolidated[key]["source_urls"]:
                consolidated[key]["source_urls"].append(row.get("source_url"))
        notes = list(consolidated.values())
        return {"ok": True, "query": query, "raw_matching_rows": len(filtered), "total_matches": len(notes), "returned": min(len(notes), limit), "notes": notes[:limit], "evidence_mode": evidence_mode, "live_error": live_error, "index_source": index_url}

    def instrument_context(self, query: str, limit: int = 20) -> dict:
        if not self.instrument_root:
            return _jsonable_error("instrument_graph_not_configured", "Set instrument_root to the Instruments Graph-RAG directory")
        path = self.instrument_root / "instruments.jsonl"
        if not path.exists():
            return _jsonable_error("instrument_graph_missing", f"Missing {path}")
        tokens = [x for x in re.findall(r"[A-Za-z0-9-]+", query.casefold()) if len(x) >= 3]
        matches = []
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            hay = json.dumps(row, ensure_ascii=False).casefold()
            score = sum(1 for token in tokens if token in hay)
            canonical = str(row.get("canonical_id", ""))
            if canonical and canonical.casefold() in query.casefold():
                score += 20
            if score:
                matches.append((score, row))
        matches.sort(key=lambda x: (-x[0], x[1].get("canonical_id", "")))
        fields = ("instrument_id", "canonical_id", "name", "instrument_type", "location", "projects", "record_status", "deployment_state", "source_urls")
        result = [{key: row.get(key) for key in fields} | {"match_score": score} for score, row in matches[:limit]]
        return {"ok": True, "query": query, "total_matches": len(matches), "returned": len(result), "instruments": result, "source": str(path)}

    def question_context(self, question: str, limit: int = 20) -> dict:
        ref_match = REFDES_RE.search(question)
        site_match = SITE_RE.search(question)
        refdes = ref_match.group(0).upper() if ref_match else None
        site = site_match.group(0).upper() if site_match else None
        q = question.casefold()
        span = next((value for word, value in [("daily", "day"), ("day", "day"), ("weekly", "week"), ("week", "week"), ("monthly", "month"), ("month", "month"), ("year", "year"), ("deployment", "deploy")] if word in q), None)
        overlay = next((value for word, value in [("qartod", "flag"), ("flag", "flag"), ("climatology", "clim"), ("annotation", "anno"), ("time", "time")] if word in q), None)
        data_range = next((x for x in ("local", "standard", "full") if x in q), None)
        variables = ["temperature", "pressure", "salinity", "conductivity", "oxygen", "velocity", "seafloor_pressure", "spectral", "ph", "nitrate"]
        variable = next((x for x in variables if x.replace("_", " ") in q or x in q), None)
        graph = self.instrument_context(refdes or site or question, limit=10) if self.instrument_root else None
        plots = self.search_plots(reference_designator=refdes, site=site, variable=variable, time_span=span, overlay=overlay, data_range=data_range, limit=limit)
        hitl_query = refdes or site
        hitl = self.list_hitl_notes(hitl_query, limit=20) if hitl_query else {"ok": True, "notes": [], "reason": "No reference designator or site detected"}
        return {
            "ok": True,
            "question": question,
            "resolved_filters": {"reference_designator": refdes, "site": site, "variable": variable, "time_span": span, "overlay": overlay, "data_range": data_range},
            "graph_context": graph,
            "live_plot_evidence": plots,
            "human_in_the_loop_notes": hitl,
            "interpretation_guidance": [
                "Treat dashboard plots and HITL notes as time-sensitive evidence and report their source URLs.",
                "Do not infer a pass/fail state from image availability alone.",
                "Use graph records for stable instrument identity and live tools for current QA/QC state.",
            ],
        }

    def health(self) -> dict:
        try:
            dashboard = self._request_json(f"{self.base_url}/api/health")
            index_count = len(self.get_index(force_refresh=True))
            return {"ok": True, "dashboard": dashboard, "plot_index_count": index_count, "base_url": self.base_url}
        except Exception as exc:
            return _jsonable_error("dashboard_unavailable", str(exc), base_url=self.base_url)

    @staticmethod
    def runtime_status() -> dict:
        vendor_root = Path(__file__).resolve().parent / "vendor"
        vendored_pipeline = vendor_root / "rca_data_tools" / "qaqc" / "pipeline.py"
        executable = shutil.which("qaqc_pipeline")
        dependency_names = ("numpy", "pandas", "xarray", "matplotlib", "prefect", "s3fs")
        missing = []
        for dependency in dependency_names:
            try:
                __import__(dependency)
            except ImportError:
                missing.append(dependency)
        return {
            "ok": True,
            "pipeline_execution_enabled": os.getenv("QAQC_AGENT_ALLOW_PIPELINE") == "1",
            "installed_entry_point": executable,
            "vendored_backend": str(vendored_pipeline) if vendored_pipeline.exists() else None,
            "representative_missing_dependencies": missing,
            "ready_for_local_generation": bool(executable or vendored_pipeline.exists()) and not missing,
            "cloud_or_s3_sync_requires": ["Prefect configuration", "AWS credentials"],
        }

    @staticmethod
    def pipeline_command(
        site: str,
        span: str = "7",
        date: str | None = None,
        cloud: bool = False,
        s3_sync: bool = False,
        homebrew_qartod: bool = False,
        express: bool = False,
        prefix: str | None = None,
    ) -> dict:
        if homebrew_qartod and s3_sync and not prefix:
            return _jsonable_error("unsafe_live_sync", "Staged QARTOD plots require an internal archive prefix")
        cmd = ["qaqc_pipeline", "--site", site, "--span", span, "--run"]
        if date: cmd += ["--time", date]
        if cloud: cmd.append("--cloud")
        if s3_sync: cmd.append("--s3-sync")
        if homebrew_qartod: cmd.append("--homebrew-qartod")
        if express: cmd.append("--express")
        if prefix: cmd += ["--prefix", prefix]
        return {"ok": True, "command": cmd, "requires": ["rca-data-tools", "OOI data access"], "additional_requirements_if_cloud_or_sync": ["Prefect credentials", "AWS credentials"], "executes": False}

    @staticmethod
    def run_pipeline(command: list[str]) -> dict:
        if os.getenv("QAQC_AGENT_ALLOW_PIPELINE") != "1":
            return _jsonable_error("pipeline_execution_disabled", "Set QAQC_AGENT_ALLOW_PIPELINE=1 to enable this optional backend")
        if not command or command[0] != "qaqc_pipeline":
            return _jsonable_error("invalid_command", "Only qaqc_pipeline commands are permitted")
        vendor_root = Path(__file__).resolve().parent / "vendor"
        vendored_pipeline = vendor_root / "rca_data_tools" / "qaqc" / "pipeline.py"
        env = os.environ.copy()
        actual_command = list(command)
        backend = "installed_entry_point"
        if not shutil.which("qaqc_pipeline"):
            if not vendored_pipeline.exists():
                return _jsonable_error("pipeline_backend_missing", "Neither qaqc_pipeline nor the pinned vendored backend is available")
            actual_command = [sys.executable, "-m", "rca_data_tools.qaqc.pipeline", *command[1:]]
            env["PYTHONPATH"] = str(vendor_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            backend = "vendored_rca_data_tools"
        run = subprocess.run(actual_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        return {"ok": run.returncode == 0, "returncode": run.returncode, "backend": backend, "command": actual_command, "output": run.stdout[-20000:]}

    def generate_plots(self, execute: bool = False, **arguments: Any) -> dict:
        plan = self.pipeline_command(**arguments)
        if not plan.get("ok") or not execute:
            return plan
        result = self.run_pipeline(plan["command"])
        result["planned_command"] = plan["command"]
        result["executes"] = True
        return result


TOOL_SCHEMAS = [
    {"name": "qaqc_health", "description": "Check the live QAQC dashboard and refresh its plot index.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "qaqc_runtime_status", "description": "Report whether the pinned plot-generation backend, its dependencies, and execution switch are available.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "qaqc_catalog_summary", "description": "Summarize currently available QAQC plots for the RCA.", "inputSchema": {"type": "object", "properties": {"include_non_rca": {"type": "boolean", "default": False}}}},
    {"name": "qaqc_search_plots", "description": "Search current dashboard plots by instrument, site, variable, time span, overlay, and range.", "inputSchema": {"type": "object", "properties": {"reference_designator": {"type": "string"}, "site": {"type": "string"}, "variable": {"type": "string"}, "time_span": {"type": "string"}, "overlay": {"type": "string"}, "data_range": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "include_non_rca": {"type": "boolean", "default": False}}}},
    {"name": "qaqc_get_plot", "description": "Resolve, download, or return the actual image for a current indexed dashboard plot.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "output_path": {"type": "string", "description": "Optional local destination for the plot file."}, "include_image": {"type": "boolean", "default": False, "description": "Return the plot as MCP image content."}}}},
    {"name": "qaqc_hitl_notes", "description": "Read current human-in-the-loop QA/QC status notes by site, reference designator, instrument class, or status.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "include_non_rca": {"type": "boolean", "default": False}, "limit": {"type": "integer", "default": 100}}}},
    {"name": "qaqc_instrument_context", "description": "Retrieve stable instrument identity and deployment context from the local Graph-RAG inventory.", "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}}},
    {"name": "qaqc_question_context", "description": "Resolve a QA/QC question into graph context, live plot evidence, and current HITL notes.", "inputSchema": {"type": "object", "required": ["question"], "properties": {"question": {"type": "string"}, "limit": {"type": "integer", "default": 20}}}},
    {"name": "qaqc_pipeline_plan", "description": "Build a dry-run rca-data-tools pipeline command. It never executes the command.", "inputSchema": {"type": "object", "required": ["site"], "properties": {"site": {"type": "string"}, "span": {"type": "string", "default": "7"}, "date": {"type": "string"}, "cloud": {"type": "boolean", "default": False}, "s3_sync": {"type": "boolean", "default": False}, "homebrew_qartod": {"type": "boolean", "default": False}, "express": {"type": "boolean", "default": False}, "prefix": {"type": "string"}}}},
    {"name": "qaqc_generate_plots", "description": "Plan or run the pinned rca-data-tools QAQC plot pipeline. Execution requires QAQC_AGENT_ALLOW_PIPELINE=1 and runtime dependencies.", "inputSchema": {"type": "object", "required": ["site"], "properties": {"site": {"type": "string"}, "span": {"type": "string", "default": "7"}, "date": {"type": "string"}, "cloud": {"type": "boolean", "default": False}, "s3_sync": {"type": "boolean", "default": False}, "homebrew_qartod": {"type": "boolean", "default": False}, "express": {"type": "boolean", "default": False}, "prefix": {"type": "string"}, "execute": {"type": "boolean", "default": False}}}},
]


def dispatch(toolkit: QAQCToolkit, name: str, arguments: dict) -> dict:
    mapping = {
        "qaqc_health": lambda: toolkit.health(),
        "qaqc_runtime_status": lambda: toolkit.runtime_status(),
        "qaqc_catalog_summary": lambda: toolkit.catalog_summary(**arguments),
        "qaqc_search_plots": lambda: toolkit.search_plots(**arguments),
        "qaqc_get_plot": lambda: toolkit.get_plot(**arguments),
        "qaqc_hitl_notes": lambda: toolkit.list_hitl_notes(**arguments),
        "qaqc_instrument_context": lambda: toolkit.instrument_context(**arguments),
        "qaqc_question_context": lambda: toolkit.question_context(**arguments),
        "qaqc_pipeline_plan": lambda: toolkit.pipeline_command(**arguments),
        "qaqc_generate_plots": lambda: toolkit.generate_plots(**arguments),
    }
    if name not in mapping:
        return _jsonable_error("unknown_tool", name)
    try:
        return mapping[name]()
    except urllib.error.HTTPError as exc:
        return _jsonable_error("http_error", str(exc), status=exc.code, url=exc.url)
    except Exception as exc:
        return _jsonable_error(type(exc).__name__, str(exc))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cache")
    parser.add_argument("--instrument-root")
    parser.add_argument("--hitl-snapshot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    summary = sub.add_parser("summary"); summary.add_argument("--include-non-rca", action="store_true")
    search = sub.add_parser("search")
    for name in ("reference-designator", "site", "variable", "time-span", "overlay", "data-range"): search.add_argument(f"--{name}")
    search.add_argument("--limit", type=int, default=20); search.add_argument("--include-non-rca", action="store_true")
    hitl = sub.add_parser("hitl"); hitl.add_argument("query", nargs="?"); hitl.add_argument("--limit", type=int, default=100); hitl.add_argument("--include-non-rca", action="store_true")
    context = sub.add_parser("context"); context.add_argument("question"); context.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    toolkit = QAQCToolkit(args.base_url, args.cache, args.instrument_root, args.hitl_snapshot)
    if args.command == "health": result = toolkit.health()
    elif args.command == "summary": result = toolkit.catalog_summary(args.include_non_rca)
    elif args.command == "search": result = toolkit.search_plots(reference_designator=args.reference_designator, site=args.site, variable=args.variable, time_span=args.time_span, overlay=args.overlay, data_range=args.data_range, limit=args.limit, include_non_rca=args.include_non_rca)
    elif args.command == "hitl": result = toolkit.list_hitl_notes(args.query, args.include_non_rca, args.limit)
    else: result = toolkit.question_context(args.question, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
