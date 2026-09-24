# RCA cable route

`rca_cable.geojson` was built on 2026-09-23 by `build_geojson.py` and `skeleton.py`. The scripts need shapely, pyproj and networkx; they are not needed to build the atlas bundle.

- **Charted (~85% of length):** NOAA/BOEM Marine Cadastre "Submarine Cable Areas", records 506 and 508 ("RSN Backbone Cable"). These are public domain and not for navigation. The ~61 m right-of-way strips were reduced to centerlines.
- **Mapped (~97 km of backbone, 25 km of secondary cable):** from the US EEZ limit to PN3A and PN3A to PN3B, and the secondary cables at Axial Base and in the caldera, from [ooi_cables.csv](https://github.com/MaleenKidiwela/CascadiaEarthquakes/blob/main/ooi_cables.csv) (M. Kidiwela). `merge_csv.py` merges it; the file matches the charted route within metres where both exist (median 1 m, worst 0.19 km), but beyond the EEZ its points are up to ~50 km apart. These replaced two straight lines that were off by up to 12 km. PN3A now sits where the backbone turns at Axial Base, ~0.5 km from the MJ03A junction box that stood in for it; PN3B is the end of the mapped backbone.
- **Nodes:** from OOI mariner safety notices, OOI asset-management, and the COSZO ship-time request in the corpus.
- **Better data:** the UW RCA team (ioceans@uw.edu) shares as-laid route files on request.
