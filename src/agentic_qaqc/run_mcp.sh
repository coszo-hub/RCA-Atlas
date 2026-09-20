#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

: "${QAQC_INSTRUMENT_ROOT:=$project_root/data/Instruments}"
: "${QAQC_HITL_SNAPSHOT:=$project_root/data/QAQC/graphrag/hitl_snapshot.jsonl}"
: "${QAQC_INDEX_CACHE:=${TMPDIR:-/tmp}/rcn-agent-qaqc-index.json}"
: "${QAQC_PYTHON:=python3}"

export QAQC_INSTRUMENT_ROOT QAQC_HITL_SNAPSHOT QAQC_INDEX_CACHE
exec "$QAQC_PYTHON" "$script_dir/mcp_server.py"
