#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${COSZO_PYTHON:-}" ]; then
  PYTHON="$COSZO_PYTHON"
elif [ -x "/Users/quakehunter/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then
  PYTHON="/Users/quakehunter/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
else
  PYTHON="python3"
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" "$SCRIPT_DIR/mcp_server.py"
