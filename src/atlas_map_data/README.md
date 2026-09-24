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
