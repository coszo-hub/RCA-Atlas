#!/usr/bin/env python3
"""Newline-delimited stdio MCP server for COSZO Hub outputs."""

import json
import os
import sys

from coszo_hub_agent_tools import CoszoHubToolkit, TOOL_SCHEMAS, dispatch


def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tool_result(value):
    value = dict(value)
    image = value.pop("_mcp_image", None)
    content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]
    if image:
        content.append({"type": "image", **image})
    return {"content": content, "isError": not value.get("ok", False)}


def main():
    toolkit = CoszoHubToolkit(
        repository_root=os.getenv("COSZO_HUB_REPOSITORY_ROOT"),
        index_path=os.getenv("COSZO_HUB_INDEX_PATH"),
        cache_dir=os.getenv("COSZO_HUB_CACHE_DIR"),
    )
    for line in sys.stdin:
        try:
            req = json.loads(line)
            method, req_id = req.get("method"), req.get("id")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rcn-agent-coszo-hub", "version": "1.0.0"}}
            elif method == "tools/list":
                result = {"tools": TOOL_SCHEMAS}
            elif method == "tools/call":
                params = req.get("params", {})
                result = tool_result(dispatch(toolkit, params.get("name", ""), params.get("arguments", {})))
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
