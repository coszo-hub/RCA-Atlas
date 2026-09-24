# Cascadia Offshore Sensor Atlas (website)

## Run locally

1. Build the data bundle (plan 1):
   `PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle --refresh-terrain --refresh-external`
2. Start the live gateway (plan 2):
   `PYTHONPATH=src .venv/bin/uvicorn atlas_map_gateway.main:app --app-dir src --host 127.0.0.1 --port 8787`
3. Start the site:
   `cd src/atlas_map && npm install && npm run dev`
4. Open http://127.0.0.1:5175

Without the gateway, the map still works from the bundle, and live sections say so. Chat also needs the Graph-RAG API.

## Test

    npm test          # unit and component tests
    npm run e2e       # browser tests with a mocked gateway; screenshots in e2e/screens/
