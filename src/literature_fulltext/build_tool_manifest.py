#!/usr/bin/env python3
"""Write the literature full-text MCP manifest consumed by Graph-RAG discovery."""

import argparse
import json
from pathlib import Path

from literature_fulltext_tools import TOOL_SCHEMAS


def build():
    return {
        "schema_version": "1.0",
        "server": {
            "name": "rcn-agent-literature-full-text",
            "transport": "stdio",
            "command": ["src/literature_fulltext/run_mcp.sh"],
            "working_directory": "project root",
        },
        "routing": {
            "first_step": "Search data/Literature/chunks.jsonl and read the abstract.",
            "fetch_condition": "Invoke literature_full_text_evidence only when the abstract is relevant but insufficient for the question.",
            "required_reason": "abstract_relevant_but_insufficient",
            "cache_behavior": "Reuse a validated cached extraction before any network request.",
            "answer_behavior": "Return bounded passages with page or section locators; do not place the complete paper in model context.",
        },
        "access": {
            "credentials_required": False,
            "scope": "Publicly accessible scholarly full text and open-access resolver metadata; no paywall bypass.",
        },
        "runtime_storage": "runtime_data/Literature/full_text_cache",
        "environment": {
            "LITERATURE_CORPUS_PATH": "set automatically by run_mcp.sh",
            "LITERATURE_FULL_TEXT_CACHE_DIR": "set automatically by run_mcp.sh",
            "LITERATURE_FULL_TEXT_TIMEOUT": "optional seconds; default 35",
            "LITERATURE_FULL_TEXT_MAX_BYTES": "optional bytes; default 52428800",
            "UNPAYWALL_EMAIL": "optional; enables Unpaywall DOI resolution",
        },
        "tools": TOOL_SCHEMAS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "tools": len(TOOL_SCHEMAS)}, indent=2))


if __name__ == "__main__":
    main()
