#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
: "${NEREUS_QUERY_DIR:=$script_dir/queries}"
: "${NEREUS_SNAPSHOT_DIR:=$project_root/data/Nereus/graphrag/snapshots}"
: "${NEREUS_CACHE_DIR:=${TMPDIR:-/tmp}/rcn-agent-nereus-cache}"
: "${NEREUS_PYTHON:=python3}"
export NEREUS_QUERY_DIR NEREUS_SNAPSHOT_DIR NEREUS_CACHE_DIR
exec "$NEREUS_PYTHON" "$script_dir/mcp_server.py"
