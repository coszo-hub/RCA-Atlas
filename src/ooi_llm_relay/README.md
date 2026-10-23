# OOI LLM relay

Lets the RCA Atlas Worker answer with the OOI JupyterHub LLM (LiteLLM alias `coder`,
`google/gemma-4-26B-A4B-it`). That server is only reachable inside the OOI network, so this relay runs on an OOI
JupyterHub server and a Cloudflare Tunnel carries the Worker's requests to the relay, never to the LiteLLM proxy.

```
coszo.org -> Worker -> Workers VPC binding -> named tunnel -> relay.py (JupyterHub, 127.0.0.1:8787) -> OOI LiteLLM
```

The relay serves one route, `POST /v1/chat/completions`, to callers holding `~/.config/ooi-llm/relay_token`
(generated on first run). It fixes the model, turns Gemma's thinking off (otherwise reasoning uses the whole token
budget and the answer comes back empty), caps `max_tokens` at 6000 and runs three answers at a time. The OOI key
(`~/.config/ooi-llm/key`) never leaves the JupyterHub server.

## Start (JupyterHub, after every restart)

```bash
bash src/ooi_llm_relay/start.sh
```

With `~/.config/ooi-llm/tunnel_token` it runs the named tunnel (`--token-file`, so the token is never on a command
line) and the Worker needs nothing. Without it, it starts a quick tunnel and prints a new trycloudflare URL, which
has to be set as the Worker's `OOI_RELAY_ORIGIN`. JupyterHub stops both when it stops the server; the Worker then
fails fast and Auto moves on to Gemini.

## Named tunnel and Workers VPC (once)

The tunnel has no public hostname. The Worker reaches it through a Workers VPC service, so nothing on the internet
can call the relay, and the account needs no DNS zone. The relay token stays as a second check.

1. **Tunnel (Cloudflare dashboard).** Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared, named
   `ooi-llm-relay`, in the account the Worker deploys to. Skip the public hostname step. Copy the token from the
   install command shown (the long string after `--token`) and save it on JupyterHub, without it reaching shell
   history:
   `read -rs t && printf '%s\n' "$t" > ~/.config/ooi-llm/tunnel_token && chmod 600 ~/.config/ooi-llm/tunnel_token && unset t`
   Do not run `cloudflared tunnel login` on the shared server: its `cert.pem` can create tunnels for the whole
   account.
2. **Connect (JupyterHub).** Rerun `start.sh`; it stops a quick tunnel left from before and connects the named one.
3. **VPC service (the machine with `wrangler login`).** Point a VPC service at the relay's port on the far side of
   the tunnel:
   ```bash
   cd src/atlas_worker
   npx wrangler vpc service create ooi-llm-relay --type http --tunnel-id <tunnel id> --ipv4 127.0.0.1 --http-port 8787
   ```
   and put the service id it prints in `wrangler.toml` under `[[vpc_services]]`, binding `OOI_RELAY`. In use now:
   tunnel `a1f09c54-f537-47df-8a28-5d30931f4771`, service `01a169d3-cc78-7b72-a336-31414354a57e`.

Check: `npx wrangler tunnel info <tunnel id>` shows the tunnel healthy, and an answer with model `ooi-gemma-4-26b`
appears as a `200` line in `~/.local/state/ooi-llm-relay/relay.log`.

## Worker (the machine with `wrangler login`)

```bash
cd src/atlas_worker
npx wrangler secret put OOI_RELAY_TOKEN    # contents of ~/.config/ooi-llm/relay_token on JupyterHub
npx wrangler secret put OOI_RELAY_ORIGIN   # only for a quick tunnel: the trycloudflare URL start.sh printed
npx wrangler deploy
```

The Worker tries the VPC binding first, then `OOI_RELAY_ORIGIN` if it is set. The model id is `ooi-gemma-4-26b`.
Auto tries it first, then Gemini, Groq and GPT-5.4 mini.
