# Cascadia Offshore Sensor Atlas (website)

## Run locally

1. Build the data bundle (plan 1):
   `PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle --refresh-terrain --refresh-external`
2. Start the live gateway (plan 2):
   `PYTHONPATH=src .venv/bin/uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787`
3. Start the site:
   `cd src/atlas_map && npm install && npm run dev`
4. Open http://127.0.0.1:5175

Optional, the 1 m Axial summit terrain (MBARI AUV survey; needs h5py and numpy from `src/atlas_map_data/requirements-auv.txt`):
`PYTHONPATH=src .venv/bin/python -m atlas_map_data.auv_tiles --source <MBARI_AxialSeamount_V2506_AUV_Summit_AUVOverShip_Topo1mSq.grd>`
writes `public/atlas/auv/`, which is committed (about 23 MB), so the map has the 1 m summit without the source grid. Rebuild it only when the survey or tiling changes. Without it the summit uses the GMRT grid.

Optional, Axial's subsurface (earthquakes 2015–2021, the magma chamber top, the caldera-wall faults; needs numpy and scipy from `src/atlas_map_data/requirements-subsurface.txt`):
`git clone https://github.com/MaleenKidiwela/axial_visuals <dir>` then `PYTHONPATH=src .venv/bin/python -m atlas_map_data.subsurface --source <dir>`
writes `public/atlas/subsurface.json`. With it, Controls gets a Subsurface switch and a month slider for the earthquakes.

Without the gateway, the map still works from the bundle, and live sections say so.

Ask Atlas (the left sidebar) answers from the RCA Atlas Worker (`src/atlas_worker`). In development Vite proxies
`/api/ask` to the deployed Worker with the `Origin` it accepts; to try unreleased Worker changes, run `npx wrangler dev
--port 8788` in `src/atlas_worker` and start the site with `VITE_ATLAS_ASK=http://127.0.0.1:8788 npm run dev`. The local
Worker reads its keys from `src/atlas_worker/.dev.vars` (not committed): `GEMINI_API_KEY`, `ATLAS_API_KEY`,
`ATLAS_API_ORIGIN` (e.g. `http://127.0.0.1:18000`) and `ATLAS_MAP_GATEWAY_ORIGIN`; if your Gemini key is out of quota,
`OPENAI_API_KEY` plus `AUTO_FALLBACK_OPENAI_MODEL=gpt-5.4-mini` let Auto finish on OpenAI locally (the deployed Worker
never sets it). Cited
sensors, sites, and DAS cables rise on the map as numbered spikes; the Axial quake count shows the day's hypocentres.

## Test

    npm test          # unit and component tests
    npm run e2e       # browser tests with a mocked gateway; screenshots in e2e/screens/
