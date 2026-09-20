#!/usr/bin/env python3
"""Newline-delimited stdio MCP server for literature full-text evidence."""

import json
import os
import sys

from literature_fulltext_tools import LiteratureFullTextToolkit, TOOL_SCHEMAS, dispatch


def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tool_result(value):
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": not value.get("ok", False)}


def main():
    toolkit = LiteratureFullTextToolkit(
        corpus_path=os.environ["LITERATURE_CORPUS_PATH"],
        cache_dir=os.environ["LITERATURE_FULL_TEXT_CACHE_DIR"],
        timeout=int(os.getenv("LITERATURE_FULL_TEXT_TIMEOUT", "35")),
        max_bytes=int(os.getenv("LITERATURE_FULL_TEXT_MAX_BYTES", str(50 * 1024 * 1024))),
        unpaywall_email=os.getenv("UNPAYWALL_EMAIL"),
    )
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method, request_id = request.get("method"), request.get("id")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "rcn-agent-literature-full-text", "version": "1.0.0"}}
            elif method == "tools/list":
                result = {"tools": TOOL_SCHEMAS}
            elif method == "tools/call":
                params = request.get("params", {})
                result = tool_result(dispatch(toolkit, params.get("name", ""), params.get("arguments", {})))
            elif method and method.startswith("notifications/"):
                continue
            else:
                send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
