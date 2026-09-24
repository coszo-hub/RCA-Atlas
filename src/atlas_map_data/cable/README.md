# RCA cable route

`rca_cable.geojson` was built on 2026-09-23 by `build_geojson.py` and `skeleton.py`. The scripts need shapely, pyproj and networkx; they are not needed to build the atlas bundle.

- **Charted (~85% of length):** NOAA/BOEM Marine Cadastre "Submarine Cable Areas", records 506 and 508 ("RSN Backbone Cable"). These are public domain and not for navigation. The ~61 m right-of-way strips were reduced to centerlines.
- **Approximate (~88 km):** from the US EEZ limit to PN3A and PN3A to PN3B. No public geometry exists there, so these are straight lines. PN3A uses the MJ03A junction box as a stand-in; PN3B is the center of its avoidance box (±2 km).
- **Nodes:** from OOI mariner safety notices, OOI asset-management, and the COSZO ship-time request in the corpus.
- **Better data:** the UW RCA team (ioceans@uw.edu) shares as-laid route files on request.
