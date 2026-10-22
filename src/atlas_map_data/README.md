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

## Offshore faults

`faults/qfaults.geojson` is committed: the USGS Quaternary Fault and Fold Database traces in the atlas area (public domain). The build keeps the faults that lie on the seafloor within the overview terrain (the Cascadia megathrust's deformation front, Daisy Bank, Alvin Canyon, Nehalem Bank and others) and drops folds and the Cascadia fold and fault belt. To refresh it from USGS:

    PYTHONPATH=src .venv/bin/python -m atlas_map_data.faults --refresh

## OSU Axial monitoring plots

The four Axial BOTPT pressure/tilt instruments and the four seafloor CTDs beside them get Oregon State University's plots from [axial.ceoas.oregonstate.edu](https://axial.ceoas.oregonstate.edu/) (`osu_axial.py`). OSU redraws them every 15 minutes under fixed file names. The build reads each page's figures and captions from the copy archived under `source_material/original_documents/AxialCEOAS`; the map loads the images from OSU and links each card to its OSU page. If OSU adds or renames a plot, re-archive the pages. The build fails if a figure name matches none of the group or span rules.

## Axial summit 1 m tiles (optional)

These tiles are built from MBARI's AUV grid, which is supplied by the COSZO project and not stored in git. Place the `.grd` file anywhere, then run:

    uv pip install --python .venv/bin/python -r src/atlas_map_data/requirements-auv.txt
    PYTHONPATH=src .venv/bin/python -m atlas_map_data.auv_tiles --source <path>/MBARI_AxialSeamount_V2506_AUV_Summit_AUVOverShip_Topo1mSq.grd

This writes `src/atlas_map/public/atlas/auv/`, about 23 MB, which is committed (the rest of the bundle is not), since the source grid is not in the repo. The levels are 16 m and 4 m over the whole summit, plus 1 m within 1.2 km of each site. Run it after the main build, since it reads `sensors.json`.

## Axial subsurface (optional)

Earthquakes (2015–2021), the magma chamber (AMC) top, and the west and east caldera-wall faults, from [axial_visuals](https://github.com/MaleenKidiwela/axial_visuals). The builder reproduces that notebook's geometry and writes it in lon/lat and metres below sea level, undoing the notebook's 1,500 m datum:

    git clone https://github.com/MaleenKidiwela/axial_visuals <dir>
    uv pip install --python .venv/bin/python -r src/atlas_map_data/requirements-subsurface.txt
    PYTHONPATH=src .venv/bin/python -m atlas_map_data.subsurface --source <dir>

This writes `src/atlas_map/public/atlas/subsurface.json`, about 1.3 MB.
