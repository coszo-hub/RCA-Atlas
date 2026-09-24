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
writes `public/atlas/auv/`. Without it the summit uses the GMRT grid.

Optional, Axial's subsurface (earthquakes 2015–2021, the magma chamber top, the caldera-wall faults; needs numpy and scipy from `src/atlas_map_data/requirements-subsurface.txt`):
`git clone https://github.com/MaleenKidiwela/axial_visuals <dir>` then `PYTHONPATH=src .venv/bin/python -m atlas_map_data.subsurface --source <dir>`
writes `public/atlas/subsurface.json`. With it, Controls gets a Subsurface switch and a month slider for the earthquakes.

Without the gateway, the map still works from the bundle, and live sections say so. Chat also needs the Graph-RAG API.

## Publish to coszo.org

coszo.org is GitHub Pages, served from the `coszo-hub/coszo-hub.github.io` repository. That repository holds built files only; nothing
there builds from this one. The map lives at `rca-atlas/map/` (https://coszo.org/rca-atlas/map/).

1. Build the data bundle (above), including the optional AUV tiles and subsurface, so `public/atlas/` is complete.
2. `npm run build`. `dist/` uses relative URLs, so it runs from any folder, and it includes the bundle (~30 MB).
3. In a checkout of `coszo-hub.github.io`: `rsync -a --delete <this repo>/src/atlas_map/dist/ rca-atlas/map/`, then commit and open a PR there.
   Pages redeploys a minute or two after the merge.

Build for the site with both services set:

    VITE_ATLAS_CHAT_URL=https://rca-atlas.quakehunt.workers.dev \
    VITE_ATLAS_GATEWAY=https://<gateway hostname> npm run build

- `VITE_ATLAS_CHAT_URL`: chat goes to the RCA Atlas Cloudflare Worker (`src/atlas_worker`), the same one behind
  coszo.org/rca-atlas/. It only accepts the coszo.org origin, so this works on the site, not locally.
- `VITE_ATLAS_GATEWAY`: live status, charts, waveforms, plots and files come from the gateway on the VM
  (`src/atlas_map_gateway/README.md`, "Run on the VM"). Without it those sections say the service is not running.

## Test

    npm test          # unit and component tests
    npm run e2e       # browser tests with a mocked gateway; screenshots in e2e/screens/
