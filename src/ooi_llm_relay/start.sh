#!/usr/bin/env bash
# Starts the OOI LLM relay and a Cloudflare quick tunnel to it on a JupyterHub server, then prints the tunnel URL
# for the Worker's OOI_RELAY_ORIGIN secret. Safe to rerun: running pieces are left alone.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LOGS="$HOME/.local/state/ooi-llm-relay"; mkdir -p "$LOGS" "$HOME/.local/bin"
CLOUDFLARED="$HOME/.local/bin/cloudflared"

if [ ! -x "$CLOUDFLARED" ]; then
  curl -fsSL -o "$CLOUDFLARED" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod 755 "$CLOUDFLARED"
fi

if ! curl -fs -m 2 http://127.0.0.1:8787/health >/dev/null; then
  nohup python3 -I "$HERE/relay.py" >> "$LOGS/relay.log" 2>&1 &
  sleep 1
  curl -fs -m 2 http://127.0.0.1:8787/health >/dev/null || { echo "relay did not start; see $LOGS/relay.log" >&2; exit 1; }
fi

if ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:8787" >/dev/null; then
  : > "$LOGS/tunnel.log"
  nohup "$CLOUDFLARED" tunnel --no-autoupdate --url http://127.0.0.1:8787 >> "$LOGS/tunnel.log" 2>&1 &
fi
for _ in $(seq 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/tunnel.log" | tail -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "${URL:-}" ] || { echo "no tunnel URL yet; see $LOGS/tunnel.log" >&2; exit 1; }
echo "Relay:  http://127.0.0.1:8787  (log $LOGS/relay.log)"
echo "Tunnel: $URL"
echo "Health: $(curl -fs -m 10 "$URL/health" || echo 'not reachable yet, retry in a few seconds')"
echo
echo "On the Worker machine: npx wrangler secret put OOI_RELAY_ORIGIN   # paste $URL"
