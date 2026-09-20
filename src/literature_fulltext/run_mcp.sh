#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
: "${LITERATURE_CORPUS_PATH:=$project_root/data/Literature/literature.jsonl}"
: "${LITERATURE_FULL_TEXT_CACHE_DIR:=$project_root/runtime_data/Literature/full_text_cache}"
: "${LITERATURE_FULL_TEXT_PYTHON:=python3}"
export LITERATURE_CORPUS_PATH LITERATURE_FULL_TEXT_CACHE_DIR
exec "$LITERATURE_FULL_TEXT_PYTHON" "$script_dir/mcp_server.py"
