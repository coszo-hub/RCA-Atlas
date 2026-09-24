#!/usr/bin/env python3
"""Newline-delimited stdio MCP server for live OSU Axial monitoring tools."""

import json
import sys

from axial_monitoring_tools import AxialMonitoringToolkit, TOOL_SCHEMAS, dispatch


def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(value):
    value = dict(value)
    image = value.pop("_mcp_image", None)
    content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]
    if image:
        content.append({"type": "image", **image})
    return {"content": content, "isError": not value.get("ok", False)}


def main():
    toolkit = AxialMonitoringToolkit()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method, request_id = request.get("method"), request.get("id")
            if method == "initialize":
                response = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rca-atlas-axial-monitoring", "version": "1.0.0"}}
            elif method == "tools/list":
                response = {"tools": TOOL_SCHEMAS}
            elif method == "tools/call":
                params = request.get("params", {})
                response = result(dispatch(toolkit, params.get("name", ""), params.get("arguments", {})))
            elif method and method.startswith("notifications/"):
                continue
            else:
                send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
                continue
            send({"jsonrpc": "2.0", "id": request_id, "result": response})
        except Exception as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
