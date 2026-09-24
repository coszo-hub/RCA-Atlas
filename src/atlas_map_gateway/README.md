# Atlas gateway

A local service for live lookups. The atlas website calls it through Vite's `/api` proxy.

    uv pip install --python .venv/bin/python -r src/atlas_map_gateway/requirements.txt
    PYTHONPATH=src .venv/bin/uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787

Needs the bundle from `atlas_map_data`. Chat needs the Graph-RAG API running; set `ATLAS_API_URL` and `ATLAS_API_KEY`, or rely on `GRAPHRAG_API_PORT` and `GRAPHRAG_API_KEY` in the repo `.env`.

| Route | Source | Cache |
|---|---|---|
| `GET /status/{refdes}` | Nereus | 2 min |
| `GET /series/{refdes}/variables` | ERDDAP | 1 h |
| `GET /series/{refdes}?var&start&end` | ERDDAP (≤31 days, ≤2,000 points) | 5 min |
| `GET /plots/{refdes}` | RCA QA/QC | 30 min |
| `GET /waveform/{NET.STA}?minutes` | EarthScope (≤60 min) | 5 min |
| `GET /files/{instrumentKey}?path&endpoint` | PI portal (`endpoint` required when the instrument has several) | 5 min |
| `POST /chat` | Graph-RAG `/v1/answer` | none |

`/files` entries are `{name, kind, path, url, date}`, newest first; `path` is relative to the endpoint root. `message` is set when the PI portal folder has more than 5,000 entries, so the newest may be missing; link out via `sourceUrl`. `/status` reports `evidenceMode` as `live` or `snapshot`. Unexpected failures return 500 with source `atlas`.

Waveform MiniSEED is written under a temp dir (`atlas-gateway-earthscope-*`) and each request's folder is deleted after decoding; the temp dir itself is removed when the gateway shuts down.

Settings (environment or the repo `.env`): `ATLAS_BUNDLE_DIR` (where `sensors.json` is; default `src/atlas_map/public/atlas`),
`ATLAS_ALLOWED_ORIGINS` (comma-separated browser origins allowed cross-site, e.g. `https://coszo.org`; none by default),
`ATLAS_CHAT=off` (turns `/chat` off: 404).

## Run on the VM (for coszo.org)

The published map (coszo.org/rca-atlas/map/) calls this gateway from the browser, so it has to be reachable over HTTPS.
It runs on the same VM as the Graph-RAG API, on loopback, behind the same Cloudflare Tunnel with a hostname of its own.
It needs no secrets: every upstream is public. Chat is not served here; the map asks the RCA Atlas Worker.

1. Code and Python, once (the gateway imports the toolkits under `src/`):

       git clone https://github.com/coszo-hub/RCA-Atlas ~/RCA-Atlas   # or `git pull` in an existing checkout
       cd ~/RCA-Atlas && uv venv --python 3.11 .venv
       uv pip install --python .venv/bin/python -r src/atlas_map_gateway/requirements.txt

2. The sensor list it serves, from the published map, so the two always match (repeat after each site publish):

       mkdir -p runtime_data/AtlasGateway/bundle
       curl -fsSo runtime_data/AtlasGateway/bundle/sensors.json https://coszo.org/rca-atlas/map/atlas/sensors.json

3. The service (a systemd user unit; `linger` keeps it running without a login session):

       mkdir -p ~/.config/systemd/user && cp src/atlas_map_gateway/deploy/atlas-gateway.service ~/.config/systemd/user/
       systemctl --user daemon-reload && systemctl --user enable --now atlas-gateway
       sudo loginctl enable-linger "$USER"
       curl -s http://127.0.0.1:8787/health          # {"ok":true}

4. A public hostname on the existing tunnel, pointing at `http://127.0.0.1:8787`, e.g. `atlas-live.<your domain>`:
   - Dashboard-managed tunnel (started with a token): Zero Trust → Networks → Tunnels → the tunnel → Public Hostname → Add.
   - Locally managed tunnel (`~/.cloudflared/config.yml`): add, above the final catch-all rule,

         - hostname: atlas-live.<your domain>
           service: http://127.0.0.1:8787

     then `cloudflared tunnel route dns <tunnel> atlas-live.<your domain>` and restart cloudflared.

   Check from anywhere: `curl -H "Origin: https://coszo.org" -i https://atlas-live.<your domain>/status/RS03CCAL-MJ03F-05-BOTPTA301`
   returns 200 with `access-control-allow-origin: https://coszo.org`.

5. Point the map at it: build with `VITE_ATLAS_GATEWAY=https://atlas-live.<your domain>` (see `src/atlas_map/README.md`)
   and publish the build to the site.

Logs: `journalctl --user -u atlas-gateway -f`. Update: `git pull`, then `systemctl --user restart atlas-gateway`.

Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_gateway/tests -t src -v`
