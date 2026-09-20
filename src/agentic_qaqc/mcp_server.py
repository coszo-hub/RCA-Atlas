#!/usr/bin/env python3
"""Minimal stdio MCP server exposing the QA/QC agent tools."""

from __future__ import annotations

import json
import os
import sys

from qaqc_agent_tools import QAQCToolkit, TOOL_SCHEMAS, dispatch


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tool_result(value: dict) -> dict:
    """Convert a toolkit value into MCP text plus optional image content."""
    value = dict(value)
    image = value.pop("_mcp_image", None)
    content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]
    if image:
        content.append({"type": "image", **image})
    return {"content": content, "isError": not value.get("ok", False)}


def main() -> None:
    toolkit = QAQCToolkit(
        base_url=os.getenv("QAQC_DASHBOARD_URL", "https://ec2.qaqc.ooi-rca.net"),
        cache_path=os.getenv("QAQC_INDEX_CACHE"),
        instrument_root=os.getenv("QAQC_INSTRUMENT_ROOT"),
        hitl_snapshot=os.getenv("QAQC_HITL_SNAPSHOT"),
    )
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            req_id = request.get("id")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rcn-agent-qaqc", "version": "1.0.0"}}
            elif method == "tools/list":
                result = {"tools": TOOL_SCHEMAS}
            elif method == "tools/call":
                params = request.get("params", {})
                value = dispatch(toolkit, params.get("name", ""), params.get("arguments", {}))
                result = tool_result(value)
            elif method and method.startswith("notifications/"):
                continue
            else:
                send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Exception as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
