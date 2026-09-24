# Atlas map data bundle

Builds `src/atlas_map/public/atlas/` (gitignored) from the restored corpus, GMRT terrain, and the committed cable route.

    uv venv --python 3.11 .venv                      # once
    PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle --refresh-terrain --refresh-external   # first time
    PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle                                        # after corpus rebuilds

The build fails, and writes nothing, when:
- an instrument type has no family
- counts don't reconcile
- a sensor lies outside the terrain
- a listed depth is more than 250 m from the seafloor without a reviewed entry in `corrections.json`

Tests: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_data/tests -t src -v`

## Axial summit 1 m tiles (optional)

These tiles are built from MBARI's AUV grid, which is supplied by the COSZO project and not stored in git. Place the `.grd` file anywhere, then run:

    uv pip install --python .venv/bin/python -r src/atlas_map_data/requirements-auv.txt
    PYTHONPATH=src .venv/bin/python -m atlas_map_data.auv_tiles --source <path>/MBARI_AxialSeamount_V2506_AUV_Summit_AUVOverShip_Topo1mSq.grd

This writes `src/atlas_map/public/atlas/auv/`, about 23 MB. The levels are 16 m and 4 m over the whole summit, plus 1 m within 1.2 km of each site. Run it after the main build, since it reads `sensors.json`.
