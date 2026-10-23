"""Loopback relay from the RCA Atlas Worker to the OOI JupyterHub LLM (LiteLLM alias "coder").

The OOI model server is only reachable inside the OOI network, so a Cloudflare Tunnel on a JupyterHub server
points here, never at the LiteLLM proxy itself. The relay accepts one route, POST /v1/chat/completions, with the
Worker's bearer token; it rebuilds the request (fixed model, thinking off, bounded max_tokens) and adds the OOI key
itself, so that key never leaves this machine. Standard library only.

    python relay.py            # listens on 127.0.0.1:8787

Files (each one line, chmod 600):
    ~/.config/ooi-llm/key           the OOI LiteLLM virtual key (sk-...)
    ~/.config/ooi-llm/relay_token   the token the Worker sends; generated on first run
"""

import hmac
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG = Path(os.environ.get("OOI_LLM_CONFIG", Path.home() / ".config" / "ooi-llm"))
UPSTREAM = os.environ.get("OOI_LLM_UPSTREAM", "https://ciw-ais-01.intra.oceanobservatories.org") + "/v1/chat/completions"
MODEL = "coder"
PORT = int(os.environ.get("OOI_RELAY_PORT", "8787"))
MAX_BODY = 1_000_000          # the evidence prompt with full-text passages stays well under this
MAX_TOKENS = 6000             # the Worker's largest answer budget
UPSTREAM_TIMEOUT_S = 50       # under the Worker's 55 s postJson timeout, so the Worker sees a clean 504
# The GPU is shared with every JupyterHub user: a few answers at a time, and a busy relay says so (429) rather
# than queueing visitors behind each other.
SLOTS = threading.BoundedSemaphore(int(os.environ.get("OOI_RELAY_CONCURRENCY", "3")))


def read_secret(name, create=False):
    path = CONFIG / name
    if create and not path.exists():
        CONFIG.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(32) + "\n")
        path.chmod(0o600)
    return path.read_text().strip()


OOI_KEY = read_secret("key")
RELAY_TOKEN = read_secret("relay_token", create=True)


def chat_request(body):
    """Keeps only plain-text messages and a bounded temperature and max_tokens; everything else is fixed here."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages required")
    clean = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant") or not isinstance(m.get("content"), str):
            raise ValueError("messages must be {role, content: string}")
        clean.append({"role": m["role"], "content": m["content"]})
    temperature = body.get("temperature", 0.15)
    max_tokens = body.get("max_tokens", 3000)
    return {
        "model": MODEL,
        "messages": clean,
        "temperature": min(max(float(temperature), 0.0), 1.0) if isinstance(temperature, (int, float)) else 0.15,
        "max_tokens": min(max(int(max_tokens), 1), MAX_TOKENS) if isinstance(max_tokens, (int, float)) else 3000,
        # Gemma 4 reasons first by default, and its reasoning counts against max_tokens: a 400-token request came
        # back with reasoning only and no answer. With thinking off the same question answered in 46 tokens.
        "chat_template_kwargs": {"enable_thinking": False},
    }


class Relay(BaseHTTPRequestHandler):
    server_version = "ooi-llm-relay"
    sys_version = ""

    def send(self, status, data):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, {"status": "ok"})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        t0 = time.monotonic()
        status, tokens = self.answer()
        # One line per request, never the prompt: time, status, seconds, completion tokens.
        print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {status} {time.monotonic() - t0:.1f}s tokens={tokens}", flush=True)

    def answer(self):
        if self.path != "/v1/chat/completions":
            self.send(404, {"error": "not found"})
            return 404, 0
        auth = self.headers.get("authorization", "")
        if not hmac.compare_digest(auth.encode(), f"Bearer {RELAY_TOKEN}".encode()):
            self.send(401, {"error": "unauthorized"})
            return 401, 0
        length = int(self.headers.get("content-length") or 0)
        if not 0 < length <= MAX_BODY:
            self.send(413, {"error": "body too large or empty"})
            return 413, 0
        try:
            request = chat_request(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError) as error:
            self.send(400, {"error": str(error)})
            return 400, 0
        if not SLOTS.acquire(timeout=5):
            self.send(429, {"error": "OOI model busy"})
            return 429, 0
        try:
            upstream = urllib.request.Request(UPSTREAM, data=json.dumps(request).encode(), method="POST",
                                              headers={"authorization": f"Bearer {OOI_KEY}", "content-type": "application/json"})
            with urllib.request.urlopen(upstream, timeout=UPSTREAM_TIMEOUT_S) as res:
                data = json.load(res)
        except urllib.error.HTTPError as error:
            # LiteLLM's message can name the key's team or budget; the Worker only needs the status.
            self.send(502, {"error": f"OOI model returned HTTP {error.code}"})
            return 502, 0
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self.send(504, {"error": f"OOI model unreachable: {type(error).__name__}"})
            return 504, 0
        finally:
            SLOTS.release()
        message = (data.get("choices") or [{}])[0].get("message") or {}
        self.send(200, {
            "model": "google/gemma-4-26B-A4B-it",
            "choices": [{"message": {"role": "assistant", "content": message.get("content") or ""},
                         "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason")}],
            "usage": data.get("usage", {}),
        })
        return 200, (data.get("usage") or {}).get("completion_tokens", 0)

    def log_message(self, *args):
        pass  # do_POST prints its own line without the client address


if __name__ == "__main__":
    if not OOI_KEY.startswith("sk-"):
        sys.exit(f"no OOI key in {CONFIG / 'key'}")
    print(f"ooi-llm-relay on 127.0.0.1:{PORT} -> {UPSTREAM}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Relay).serve_forever()
