# OOI LLM relay

Lets the RCA Atlas Worker answer with the OOI JupyterHub LLM (LiteLLM alias `coder`,
`google/gemma-4-26B-A4B-it`). That server is only reachable inside the OOI network, so this relay runs on an OOI
JupyterHub server and a Cloudflare Tunnel exposes the relay, never the LiteLLM proxy.

```
coszo.org -> Worker -> Cloudflare Tunnel -> relay.py (JupyterHub, 127.0.0.1:8787) -> OOI LiteLLM -> vLLM
```

The relay serves one route, `POST /v1/chat/completions`, to callers holding `~/.config/ooi-llm/relay_token`
(generated on first run). It fixes the model, turns Gemma's thinking off (otherwise reasoning uses the whole token
budget and the answer comes back empty), caps `max_tokens` at 6000 and runs three answers at a time. The OOI key
(`~/.config/ooi-llm/key`) never leaves the JupyterHub server.

## Start (JupyterHub)

```bash
bash src/ooi_llm_relay/start.sh     # prints the trycloudflare URL
```

The quick-tunnel URL changes whenever the tunnel restarts, and both stop when JupyterHub stops the server; the
Worker then fails fast and Auto moves on to Gemini.

## Worker (the machine with `wrangler login`)

```bash
cd src/atlas_worker
npx wrangler secret put OOI_RELAY_ORIGIN   # the trycloudflare URL
npx wrangler secret put OOI_RELAY_TOKEN    # contents of ~/.config/ooi-llm/relay_token on JupyterHub
npx wrangler deploy
```

The model id is `ooi-gemma-4-26b`. Auto tries it first, then Gemini, Groq, OpenRouter and GPT-5.4 mini.
