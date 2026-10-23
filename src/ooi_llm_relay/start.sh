#!/usr/bin/env bash
# Starts the OOI LLM relay and its Cloudflare Tunnel on a JupyterHub server. Safe to rerun: running pieces are
# left alone. Rerun after every JupyterHub restart.
#
# With ~/.config/ooi-llm/tunnel_token (the named tunnel "ooi-llm-relay", see README.md) the Worker reaches the relay
# through its Workers VPC binding, and needs nothing after a restart. Without it, a quick tunnel is started and its
# new trycloudflare URL has to be set as the Worker's OOI_RELAY_ORIGIN each time.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$HOME/.config/ooi-llm"
LOGS="$HOME/.local/state/ooi-llm-relay"; mkdir -p "$LOGS" "$HOME/.local/bin"
CLOUDFLARED="$HOME/.local/bin/cloudflared"
TOKEN_FILE="$CONFIG/tunnel_token"
QUICK="cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8787"
NAMED="cloudflared tunnel --no-autoupdate run --token-file"

if [ ! -x "$CLOUDFLARED" ]; then
  curl -fsSL -o "$CLOUDFLARED" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod 755 "$CLOUDFLARED"
fi

if ! curl -fs -m 2 http://127.0.0.1:8787/health >/dev/null; then
  nohup python3 -I "$HERE/relay.py" >> "$LOGS/relay.log" 2>&1 &
  sleep 1
  curl -fs -m 2 http://127.0.0.1:8787/health >/dev/null || { echo "relay did not start; see $LOGS/relay.log" >&2; exit 1; }
fi
echo "Relay:  http://127.0.0.1:8787  (log $LOGS/relay.log)"

if [ -s "$TOKEN_FILE" ]; then
  chmod 600 "$TOKEN_FILE"
  pkill -f "$QUICK" 2>/dev/null || true   # a quick tunnel left from before the named one existed
  if ! pgrep -f "$NAMED" >/dev/null; then
    : > "$LOGS/tunnel.log"
    nohup "$CLOUDFLARED" tunnel --no-autoupdate run --token-file "$TOKEN_FILE" >> "$LOGS/tunnel.log" 2>&1 &
  fi
  # The named tunnel has no public hostname (only the Worker's VPC binding reaches it), so the check is the
  # connector registering, not a request through the tunnel.
  for _ in $(seq 30); do grep -q "Registered tunnel connection" "$LOGS/tunnel.log" && break; sleep 1; done
  if grep -q "Registered tunnel connection" "$LOGS/tunnel.log"; then
    echo "Tunnel: named tunnel connected (log $LOGS/tunnel.log). The Worker needs no change."
  else
    echo "named tunnel did not connect; see $LOGS/tunnel.log" >&2; exit 1
  fi
  exit 0
fi

if ! pgrep -f "$QUICK" >/dev/null; then
  : > "$LOGS/tunnel.log"
  nohup "$CLOUDFLARED" tunnel --no-autoupdate --url http://127.0.0.1:8787 >> "$LOGS/tunnel.log" 2>&1 &
fi
for _ in $(seq 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGS/tunnel.log" | tail -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "${URL:-}" ] || { echo "no tunnel URL yet; see $LOGS/tunnel.log" >&2; exit 1; }
echo "Tunnel: $URL  (quick tunnel; no $TOKEN_FILE)"
echo "Health: $(curl -fs -m 10 "$URL/health" || echo 'not reachable yet, retry in a few seconds')"
echo
echo "On the Worker machine: npx wrangler secret put OOI_RELAY_ORIGIN   # paste $URL"
