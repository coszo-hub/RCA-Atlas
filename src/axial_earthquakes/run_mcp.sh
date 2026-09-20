#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
export AXIAL_DB_PATH="${AXIAL_DB_PATH:-$PROJECT_ROOT/runtime_data/AxialEarthquakes/graphrag/events.sqlite}"
exec python3 "$SCRIPT_DIR/mcp_server.py"
