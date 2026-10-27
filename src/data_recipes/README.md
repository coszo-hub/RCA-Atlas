# Data download recipes

For every instrument the atlas maps, the easiest way to get its data, then the other ways, each with the facts a
script needs and a Python script that has been run. Ask Atlas uses them to answer "how do I download …" with one
script for the asked instrument and timeframe (`data_recipes` collection, `src/atlas_worker/src/recipe_ids.json`).
For a question that names a type and no place, each type has an overview of every instrument of it (place, mount,
depth, easiest route and dataset ID) and one example recipe (`TYPE:<id>` and `EXAMPLE:<id>` in `recipe_ids.json`).

## Routes, easiest first for what most people want

| Route | Login | Gives | Recipe uses |
|---|---|---|---|
| EarthScope FDSN | none | seismometer and low-frequency hydrophone waveforms (MiniSEED, with response) | ObsPy |
| OOI raw-data archive | none | the original files: broadband hydrophone MiniSEED, camera stills and video, sonar | requests |
| OOI ERDDAP | none | processed tables with QARTOD flags (about one row a minute) | erddapy |
| OOI Gold Copy THREDDS | none | every sample, every stream, read through OPeNDAP (only the asked variables and times) | xarray |
| RCA PI data portal | none | PI instruments and experiments (DAS, COVIS, SCPR, A-0-A, MARUM) | requests |
| GitHub | none | FETCH | requests |
| OOI M2M | free OOI account | the same streams before they reach the Gold Copy; given as a script only where no public route has the data, as each request is queued (up to 20 minutes) | requests + xarray |

## Build

```sh
python src/data_recipes/build_data_recipes.py --refresh   # read every service (~15 min) into runtime_data/DataRecipes/sources.json
python src/data_recipes/build_data_recipes.py             # write data/DataRecipes and recipe_ids.json from the cache
python src/data_recipes/test_recipes.py --jobs 4          # run every recipe in the sandbox
python src/data_recipes/build_data_recipes.py             # again: failed routes drop out, passed ones say when they were tested
```

`--refresh-erddap`, `--refresh-gold`, `--refresh-raw` and `--refresh-portal` re-read one service.

## The sandbox

`test_recipes.py` runs each recipe's own code with its example timeframe replaced by a short window inside the
dataset's coverage, in a fresh container of `sandbox.Dockerfile` (Python and `requirements-recipes.txt` only): an
unprivileged user with no capabilities, memory, CPU and process limits, no host folder (the code goes in on stdin), and
a work folder that is a tmpfs capped at 1.5 GB, so a recipe cannot fill the disk. A recipe passes when it exits cleanly
having written a data file that is not empty. Routes whose files are over 1 GB (the HD camera's 14 GB videos) are not
run. M2M recipes run only with `--m2m N` and `OOI_API_USERNAME` / `OOI_API_TOKEN` in `.env`, which reach only that
container; their requests turn off the notification email (`email=None`), as OOI's own ooi-data-explorations does.

## Safety

Names read from remote listings go into code people run, so only plain names are kept (letters, digits, `._:+-`), and
every value enters a script through `repr()`.
