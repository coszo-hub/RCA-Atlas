#!/usr/bin/env python3
"""Newline-delimited stdio MCP server for the RCA Atlas sandbox tasks."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


def protocol_channel():
    """Keep fd 1 for JSON-RPC only: native libraries (LAPACK) print errors to stdout,
    which would corrupt the stream, so their fd 1 is pointed at stderr."""
    channel = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return channel


def main():
    channel = protocol_channel()
    from atlas_tasks.tools import Sandbox, TOOL_SCHEMAS, dispatch

    def send(value):
        channel.write(json.dumps(value, ensure_ascii=False) + "\n")
        channel.flush()

    sandbox = Sandbox(os.getenv("ATLAS_SANDBOX_DIR"))
    for line in sys.stdin:
        if not line.strip():
            continue
        req_id = None
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            continue
        try:
            method, req_id = req.get("method"), req.get("id")
            if method == "initialize":
                asked = (req.get("params") or {}).get("protocolVersion")
                result = {"protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "rca-atlas-sandbox-tasks", "version": "1.0.0"}}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOL_SCHEMAS}
            elif method == "tools/call":
                params = req.get("params", {})
                value = dispatch(sandbox, params.get("name", ""), params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                          "isError": not value.get("ok", False)}
            elif method and method.startswith("notifications/"):
                continue
            else:
                send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Exception as exc:
            # Answer with the request's id, or the client waits on it forever.
            send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
