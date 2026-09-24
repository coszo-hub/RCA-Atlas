# Atlas Map, Plan 1 of 3: Data Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A build step that turns the corpus, the GMRT seafloor grids, and the researched cable route into a validated static bundle (`src/atlas_map/public/atlas/`) that the atlas website loads.

**Architecture:** A stdlib-only Python package `src/atlas_map_data/`. It has one module per concern: families, sensors, status, terrain, access, sites, cable and validation. A CLI (`build_atlas_bundle.py`) wires them together. Network access happens only in explicit `--refresh-*` steps, which cache results under `runtime_data/AtlasMap/`. The normal build is offline and deterministic.

**Tech Stack:** Python 3.11 (repo-local `.venv` created with `uv`), standard library only, `unittest` (the repo's convention).

**Spec:** `docs/superpowers/specs/2026-09-23-atlas-map-design.md`

**Plan series:**
1. Data bundle (this plan)
2. `2026-09-23-atlas-map-2-gateway.md`
3. `2026-09-23-atlas-map-3-website.md`

Each plan produces working, tested software. Plans 2 and 3 consume this bundle.

## Global Constraints

- Nothing outside `src/atlas_map_data/`, `src/atlas_map_gateway/`, `src/atlas_map/`, `docs/`, and `.gitignore` changes. Spec: "Any change to existing code under `src/` other than the three new folders" is out of scope.
- `data/` and `runtime_data/` are gitignored and restored from private releases. The generated bundle (`src/atlas_map/public/atlas/`) is derived from them and must be gitignored too.
- Family colors, verbatim from the spec:
  - seismic `#d95926`
  - pressure `#c98500`
  - water properties `#3987e5`
  - currents `#199e70`
  - sound and imaging `#d55181`
  - fiber `#d9d6cc`
- Every family also has a distinct glyph: circle, triangle, square, diamond, hexagon, bar.
- An unknown instrument type fails the build. It must never default to a family.
- Status rules, from the spec:
  - Use the Nereus status when the reference designator matches (via `instrument_crosswalk.jsonl`).
  - Otherwise "planned" for new COSZO sensor suites.
  - Otherwise "unknown".
- A site is every sensor within 150 m of another, whatever its OOI site code.
- Depth-versus-seafloor tolerance is 250 m. Mismatches must be in `corrections.json` or the build fails.
- GMRT credit string: `GMRT, Ryan et al. (2009), CC BY 4.0`.
- Terrain grids:
  - overview: 43.95–46.35°N, 130.6–123.7°W, `med` resolution
  - Axial patch: 45.78–46.08°N, 130.15–129.6°W, `high` resolution
  - Hydrate patch: 44.35–44.75°N, 125.5–124.9°W, `high` resolution
- Bundle files are little-endian Int16 meters for terrain and UTF-8 JSON for everything else.

## Review Focus

1. **A new instrument type appears in a corpus rebuild.** The build must stop and name the type, not quietly file it under water properties. The preview did exactly that for two types. Pinned in Task 1.
2. **A sensor with coordinates but no depth.** It must still get a site and a seafloor depth from terrain, and must not crash the depth check. Pinned in Task 6 and Task 8.
3. **A sensor outside every terrain grid.** It is placed with the fallback depth and flagged by validation; it is not dropped. Pinned in Task 4 and Task 8.
4. **The ERDDAP or QA/QC cache is missing,** for example on a fresh machine without `--refresh-external`. The build still succeeds, those access routes are omitted, and a warning is printed. Pinned in Task 5.
5. **Unlocated sensors whose site code matches no located site.** They are listed under `unplaced` in the bundle, not lost. Pinned in Task 6.

---

## File Structure

```text
src/atlas_map_data/
  __init__.py
  paths.py                 repo-relative paths, one place
  families.py              type → family table, family metadata
  corpus.py                JSONL reading
  sensors.py               inventory row → sensor record; depth ranges; corrections
  corrections.json         reviewed fixes (position, depth) with reasons
  status.py                Nereus status resolution
  terrain.py               GMRT fetch, ESRI ASCII parse, sampling, Int16 writer
  access.py                data-access routes per sensor; external caches
  sites.py                 physical-location clustering, regions, water column
  cable.py                 cable GeoJSON → cable.json
  cable/rca_cable.geojson  processed route (public sources), committed
  cable/build_geojson.py   route build script (from research), committed
  cable/skeleton.py        centerline tracer (from research), committed
  cable/README.md          sources and accuracy
  validate.py              bundle validation
  build_atlas_bundle.py    CLI
  tests/__init__.py
  tests/fixtures/…         tiny inputs
  tests/test_*.py
```

---

### Task 1: Package scaffold, environment, and the family table

**Files:**
- Create: `src/atlas_map_data/__init__.py`, `src/atlas_map_data/paths.py`, `src/atlas_map_data/families.py`
- Create: `src/atlas_map_data/tests/__init__.py`, `src/atlas_map_data/tests/test_families.py`
- Modify: `.gitignore` (append two lines)

**Interfaces:**
- Produces:
  - `paths.REPO: Path`
  - `paths.DATA: Path`
  - `paths.RUNTIME: Path` (= `REPO/"runtime_data"/"AtlasMap"`)
  - `paths.BUNDLE: Path` (= `REPO/"src"/"atlas_map"/"public"/"atlas"`)
  - `families.FAMILIES: list[dict]` with keys `key, label, color, glyph`
  - `families.family_for(instrument_type: str) -> str`, which raises `families.UnknownInstrumentType`
  - `families.FAMILY_ORDER: dict[str, int]`

- [ ] **Step 1: Create the environment**

```bash
cd /Users/yaoderek/conductor/workspaces/rca-atlas/surabaya
uv venv --python 3.11 .venv
.venv/bin/python --version
```
Expected: `Python 3.11.x`. `.venv/` is already in `.gitignore`.

- [ ] **Step 2: Write the failing test**

`src/atlas_map_data/tests/__init__.py`: empty file.

`src/atlas_map_data/tests/test_families.py`:
```python
import unittest

from atlas_map_data import families


class FamilyTableTest(unittest.TestCase):
    def test_every_corpus_type_has_a_family(self):
        corpus_types = [
            "absolute_pressure_gauge", "adcp", "bottom_pressure_recorder", "bottom_pressure_tilt",
            "broadband_seismometer", "camera", "camera_temperature_campaign_system", "ctd", "das",
            "differential_pressure_gauge", "dissolved_gas", "dissolved_oxygen",
            "distributed_fiber_sensing_experiment", "dna_sampler", "fiber_optic_strainmeter",
            "fluid_sampler", "fluorometer", "geodetic_and_seismic_sensor_module", "hpies", "hydrophone",
            "irradiance", "low_frequency_hydrophone", "mass_spectrometer", "nitrate",
            "ocean_bottom_seismic_package", "osmotic_sampler", "par", "pco2", "ph", "pressure",
            "seismometer", "self_calibrating_pressure_recorder", "self_calibrating_pressure_sensor",
            "short_period_seismometer", "sonar", "spectrophotometer", "thermistor", "thermistor_array",
            "thermistor_ph", "three_dimensional_current_meter", "tiltmeter", "velocimeter",
        ]
        for t in corpus_types:
            self.assertIn(families.family_for(t), {f["key"] for f in families.FAMILIES}, t)

    def test_types_the_prototype_misfiled(self):
        self.assertEqual(families.family_for("short_period_seismometer"), "seismic")
        self.assertEqual(families.family_for("distributed_fiber_sensing_experiment"), "fiber")

    def test_unknown_type_fails_loudly(self):
        with self.assertRaises(families.UnknownInstrumentType) as ctx:
            families.family_for("gravimeter")
        self.assertIn("gravimeter", str(ctx.exception))

    def test_family_metadata_matches_spec(self):
        by_key = {f["key"]: f for f in families.FAMILIES}
        self.assertEqual(by_key["seismic"]["color"], "#d95926")
        self.assertEqual(by_key["pressure"]["color"], "#c98500")
        self.assertEqual(by_key["chemistry"]["color"], "#3987e5")
        self.assertEqual(by_key["currents"]["color"], "#199e70")
        self.assertEqual(by_key["acoustic"]["color"], "#d55181")
        self.assertEqual(by_key["fiber"]["color"], "#d9d6cc")
        self.assertEqual(len({f["glyph"] for f in families.FAMILIES}), 6)
        self.assertEqual(list(families.FAMILY_ORDER), [f["key"] for f in families.FAMILIES])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_data/tests -t src -v`
Expected: ERROR `ModuleNotFoundError: No module named 'atlas_map_data'`

- [ ] **Step 4: Implement**

`src/atlas_map_data/__init__.py`:
```python
"""Build the static data bundle for the Cascadia Offshore Sensor Atlas."""
```

`src/atlas_map_data/paths.py`:
```python
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
RUNTIME = REPO / "runtime_data" / "AtlasMap"
BUNDLE = REPO / "src" / "atlas_map" / "public" / "atlas"
PACKAGE = Path(__file__).resolve().parent
```

`src/atlas_map_data/families.py`:
```python
"""Instrument type → sensor family. One table; an unknown type is an error, never a default."""
from __future__ import annotations

FAMILIES = [
    {"key": "seismic", "label": "Seismic", "color": "#d95926", "glyph": "triangle"},
    {"key": "pressure", "label": "Pressure & strain", "color": "#c98500", "glyph": "square"},
    {"key": "chemistry", "label": "Water properties", "color": "#3987e5", "glyph": "circle"},
    {"key": "currents", "label": "Currents & light", "color": "#199e70", "glyph": "diamond"},
    {"key": "acoustic", "label": "Sound & imaging", "color": "#d55181", "glyph": "hexagon"},
    {"key": "fiber", "label": "Fiber-optic", "color": "#d9d6cc", "glyph": "bar"},
]
FAMILY_ORDER = {f["key"]: i for i, f in enumerate(FAMILIES)}

_TYPES = {
    "seismic": """seismometer broadband_seismometer short_period_seismometer ocean_bottom_seismic_package
                  geodetic_and_seismic_sensor_module tiltmeter bottom_pressure_tilt""",
    "pressure": """bottom_pressure_recorder pressure absolute_pressure_gauge differential_pressure_gauge
                   self_calibrating_pressure_recorder self_calibrating_pressure_sensor fiber_optic_strainmeter hpies""",
    "chemistry": """ctd dissolved_oxygen ph pco2 nitrate fluorometer spectrophotometer mass_spectrometer
                    dissolved_gas thermistor thermistor_ph thermistor_array osmotic_sampler dna_sampler fluid_sampler""",
    "currents": "adcp velocimeter three_dimensional_current_meter par irradiance",
    "acoustic": "hydrophone low_frequency_hydrophone camera sonar camera_temperature_campaign_system",
    "fiber": "das distributed_fiber_sensing_experiment",
}
FAMILY_OF_TYPE = {t: fam for fam, types in _TYPES.items() for t in types.split()}


class UnknownInstrumentType(ValueError):
    pass


def family_for(instrument_type: str) -> str:
    try:
        return FAMILY_OF_TYPE[instrument_type]
    except KeyError:
        raise UnknownInstrumentType(
            f"instrument type {instrument_type!r} has no family; add it to atlas_map_data/families.py"
        ) from None
```

Append to `.gitignore`:
```text
# Atlas map: generated from private corpus data
/src/atlas_map/public/atlas/
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_data/tests -t src -v`
Expected: 4 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add .gitignore src/atlas_map_data/__init__.py src/atlas_map_data/paths.py src/atlas_map_data/families.py src/atlas_map_data/tests/
git commit -m "Add atlas data package with sensor family table"
```

---

### Task 2: Sensor records, depth ranges, and corrections

**Files:**
- Create: `src/atlas_map_data/corpus.py`, `src/atlas_map_data/sensors.py`, `src/atlas_map_data/corrections.json`
- Test: `src/atlas_map_data/tests/test_sensors.py`

**Interfaces:**
- Consumes: `families.family_for`
- Produces:
  - `corpus.load_jsonl(path: Path) -> list[dict]`
  - `sensors.COLUMN_KIND: dict[str, str]`, keyed by node prefix: `"SF"`, `"PC"`, `"DP"`
  - `sensors.depth_range(node: str | None, water_depth: float | None) -> list[int] | None`
  - `sensors.sensor_from_row(row: dict) -> dict`. The returned dict has keys:
    - `id`, `instrumentId`, `name`, `type`, `family`
    - `lat`, `lon`, `depth`, `depthRange`, `waterDepth`
    - `siteCode`, `node`, `refdes`, `location`, `projects`, `coszoRole`
    - `manufacturer`, `model`, `sources`, `arcadaId`, `corrections`
  - `sensors.load_corrections(path: Path) -> list[dict]`
  - `sensors.apply_corrections(records: list[dict], corrections: list[dict]) -> None`, which mutates in place. A record matches when, for every field in `match`, its value is in the listed values; include the wrong coordinate in `match` for position fixes, so sensors without positions are never moved.

- [ ] **Step 1: Write the failing test**

`src/atlas_map_data/tests/test_sensors.py`:
```python
import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import sensors

ROW = {
    "instrument_id": "INSTRUMENT-a", "canonical_id": "RS03AXPS-SF03A-2A-CTDPFA302",
    "name": "Axial Base Shallow Profiler CTD", "instrument_type": "ctd",
    "location": "Axial Seamount Base", "projects": ["Regional Cabled Array"], "coszo_role": None,
    "site": "RS03AXPS", "node": "SF03A", "instrument_code": "2A-CTDPFA302",
    "latitude": 45.9316, "longitude": -129.9808, "depth_m": 2607,
    "manufacturer": "Sea-Bird", "model": "SBE 16plus", "source_urls": ["https://example.org/a"],
    "arcada_document_id": "ARCADA-INSTRUMENT-x",
}


class SensorRecordTest(unittest.TestCase):
    def test_profiler_depths_come_from_node_not_water_depth(self):
        self.assertEqual(sensors.depth_range("SF03A", 2607), [5, 200])
        self.assertEqual(sensors.depth_range("PC03A", 2607), [200, 200])
        self.assertEqual(sensors.depth_range("DP03A", 2607), [250, 2457])
        self.assertIsNone(sensors.depth_range("MJ03B", 1542))
        self.assertIsNone(sensors.depth_range(None, 1542))

    def test_deep_profiler_without_water_depth_has_no_range(self):
        self.assertIsNone(sensors.depth_range("DP03A", None))

    def test_sensor_from_row(self):
        s = sensors.sensor_from_row(ROW)
        self.assertEqual(s["id"], "RS03AXPS-SF03A-2A-CTDPFA302")
        self.assertEqual(s["family"], "chemistry")
        self.assertEqual(s["refdes"], "RS03AXPS-SF03A-2A-CTDPFA302")
        self.assertEqual(s["depthRange"], [5, 200])
        self.assertEqual(s["depth"], 5)
        self.assertEqual(s["waterDepth"], 2607)
        self.assertEqual(s["sources"], ["https://example.org/a"])
        self.assertEqual(s["corrections"], [])

    def test_row_without_refdes_parts(self):
        row = dict(ROW, canonical_id="COSZO-BPR-O2B", site=None, node=None, instrument_code=None,
                   instrument_type="bottom_pressure_recorder", depth_m=None)
        s = sensors.sensor_from_row(row)
        self.assertIsNone(s["refdes"])
        self.assertIsNone(s["depth"])
        self.assertIsNone(s["depthRange"])

    def test_apply_position_correction(self):
        recs = [sensors.sensor_from_row(ROW)]
        unlocated = sensors.sensor_from_row(dict(ROW, canonical_id="RS03AXPS-PC03A-4B-CTDPFK301", latitude=None, longitude=None))
        recs.append(unlocated)
        fixes = [{"match": {"siteCode": ["RS03AXPS", "RS03AXPD"], "lat": [45.9316]}, "set": {"lat": 45.8168, "lon": -129.754},
                  "reason": "Inventory places the Axial Base profilers in the caldera."}]
        sensors.apply_corrections(recs, fixes)
        self.assertEqual((recs[0]["lat"], recs[0]["lon"]), (45.8168, -129.754))
        self.assertEqual(recs[0]["corrections"], ["Inventory places the Axial Base profilers in the caldera."])
        # a sensor with no recorded position is not given one by a position fix
        self.assertIsNone(unlocated["lat"])
        self.assertEqual(unlocated["corrections"], [])

    def test_correction_matching_nothing_is_reported(self):
        recs = [sensors.sensor_from_row(ROW)]
        with self.assertRaises(ValueError):
            sensors.apply_corrections(recs, [{"match": {"id": ["NOPE"]}, "set": {"lat": 1}, "reason": "x"}])

    def test_shipped_corrections_file_loads(self):
        fixes = sensors.load_corrections(Path(sensors.__file__).with_name("corrections.json"))
        self.assertTrue(any("RS03AXPS" in f["match"].get("siteCode", []) for f in fixes))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_sensors -v`
Expected: ERROR `cannot import name 'sensors'`

- [ ] **Step 3: Implement**

`src/atlas_map_data/corpus.py`:
```python
from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
```

`src/atlas_map_data/sensors.py`:
```python
"""Inventory rows → atlas sensor records, with profiler depth ranges and reviewed corrections."""
from __future__ import annotations

import json
from pathlib import Path

from .families import family_for

# OOI node prefixes for moorings that sample the water column. Depths in meters.
COLUMN_KIND = {"SF": "Shallow profiler", "PC": "200 m platform", "DP": "Deep profiler"}


def depth_range(node: str | None, water_depth: float | None) -> list[int] | None:
    prefix = (node or "")[:2]
    if prefix == "SF":
        return [5, 200]
    if prefix == "PC":
        return [200, 200]
    if prefix == "DP" and water_depth:
        return [250, int(round(water_depth)) - 150]
    return None


def sensor_from_row(row: dict) -> dict:
    site, node, code = row.get("site"), row.get("node"), row.get("instrument_code")
    refdes = f"{site}-{node}-{code}" if site and node and code else None
    water = row.get("depth_m")
    rng = depth_range(node, water)
    return {
        "id": row["canonical_id"],
        "instrumentId": row["instrument_id"],
        "name": row["name"],
        "type": row["instrument_type"],
        "family": family_for(row["instrument_type"]),
        "lat": row.get("latitude"),
        "lon": row.get("longitude"),
        "depth": rng[0] if rng else water,
        "depthRange": rng,
        "waterDepth": water,
        "siteCode": site,
        "node": node,
        "refdes": refdes,
        "location": row.get("location"),
        "projects": row.get("projects") or [],
        "coszoRole": row.get("coszo_role"),
        "manufacturer": row.get("manufacturer"),
        "model": row.get("model"),
        "sources": list(row.get("source_urls") or []),
        "arcadaId": row.get("arcada_document_id"),
        "corrections": [],
    }


def load_corrections(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["corrections"]


def _matches(record: dict, match: dict) -> bool:
    return all(record.get(field) in values for field, values in match.items())


def apply_corrections(records: list[dict], corrections: list[dict]) -> None:
    for fix in corrections:
        hits = [r for r in records if _matches(r, fix["match"])]
        if not hits:
            raise ValueError(f"correction matched no sensors: {fix['match']}")
        for r in hits:
            r.update(fix["set"])
            r["corrections"].append(fix["reason"])
```

`src/atlas_map_data/corrections.json`:
```json
{
  "corrections": [
    {
      "match": {"siteCode": ["RS03AXPS", "RS03AXPD"], "lat": [45.9316]},
      "set": {"lat": 45.8168, "lon": -129.754},
      "reason": "The inventory places the Axial Base shallow and deep profilers at 45.9316, -129.9808 in the caldera, where the seafloor is 1,516 m, but lists them at 2,607 m. Moved to the Axial Base seafloor package position (RS03AXBS)."
    }
  ]
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_sensors -v`
Expected: 7 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_map_data/corpus.py src/atlas_map_data/sensors.py src/atlas_map_data/corrections.json src/atlas_map_data/tests/test_sensors.py
git commit -m "Build atlas sensor records with profiler depths and reviewed corrections"
```

---

### Task 3: Status resolution

**Files:**
- Create: `src/atlas_map_data/status.py`
- Test: `src/atlas_map_data/tests/test_status.py`

**Interfaces:**
- Consumes: sensor records from Task 2 (`instrumentId`, `coszoRole`)
- Produces:
  - `status.load_status_index(entities: list[dict], crosswalk: list[dict]) -> dict[str, dict]`. It maps `instrumentId` to `{"status": str, "refdes": str, "asOf": str}`.
  - `status.resolve(record: dict, index: dict[str, dict]) -> dict`. It returns `{"status", "statusSource", "statusAsOf"}`.
  - `status.STATUS_GROUP: dict[str, str]`, which maps a raw status to one of `operating`, `offline`, `planned` or `unknown`.

- [ ] **Step 1: Write the failing test**

`src/atlas_map_data/tests/test_status.py`:
```python
import unittest

from atlas_map_data import status

ENTITIES = [
    {"entity_type": "instrument", "reference_designator": "RS03CCAL-MJ03F-05-BOTPTA301",
     "operational_status": "OPERATIONAL", "retrieved_at": "2026-09-19T07:41:44+00:00"},
    {"entity_type": "instrument", "reference_designator": "RS01SBPD-DP01A-00-ENG000000",
     "operational_status": "NOT_DEPLOYED", "retrieved_at": "2026-09-19T07:41:44+00:00"},
    {"entity_type": "deployment", "deployment_id": 1},
]
CROSSWALK = [
    {"reference_designator": "RS03CCAL-MJ03F-05-BOTPTA301", "instrument_graph_id": "INSTRUMENT-1",
     "match_type": "exact_reference_designator"},
    {"reference_designator": "RS01SBPD-DP01A-00-ENG000000", "instrument_graph_id": None,
     "match_type": "not_present_in_current_instrument_graph"},
]


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.index = status.load_status_index(ENTITIES, CROSSWALK)

    def test_index_uses_exact_crosswalk_matches_only(self):
        self.assertEqual(set(self.index), {"INSTRUMENT-1"})
        self.assertEqual(self.index["INSTRUMENT-1"]["status"], "OPERATIONAL")

    def test_nereus_status_wins(self):
        r = status.resolve({"instrumentId": "INSTRUMENT-1", "coszoRole": "new_sensor_suite"}, self.index)
        self.assertEqual(r, {"status": "OPERATIONAL", "statusSource": "Nereus snapshot",
                             "statusAsOf": "2026-09-19T07:41:44+00:00"})

    def test_new_coszo_suites_are_planned(self):
        for role in ("new_sensor_suite", "Oregon_Shelf_suite"):
            r = status.resolve({"instrumentId": "INSTRUMENT-9", "coszoRole": role}, self.index)
            self.assertEqual(r["status"], "PLANNED")
            self.assertEqual(r["statusSource"], "Inventory: new COSZO sensor")

    def test_everything_else_is_unknown(self):
        for role in (None, "existing_RCA_foundation", "related_deployment_site_asset"):
            r = status.resolve({"instrumentId": "INSTRUMENT-9", "coszoRole": role}, self.index)
            self.assertEqual(r, {"status": "UNKNOWN", "statusSource": None, "statusAsOf": None})

    def test_every_raw_status_has_a_group(self):
        for raw in ("OPERATIONAL", "PARTIALLY_FUNCTIONAL", "NOT_DEPLOYED", "RETIRED", "SUPERSEDED",
                    "RECOVERED", "UNCABLED", "PLANNED", "UNKNOWN"):
            self.assertIn(status.STATUS_GROUP[raw], {"operating", "offline", "planned", "unknown"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_status -v`
Expected: ERROR `cannot import name 'status'`

- [ ] **Step 3: Implement**

`src/atlas_map_data/status.py`:
```python
"""Sensor status: Nereus when the reference designator matches, else planned (new COSZO), else unknown."""
from __future__ import annotations

PLANNED_ROLES = {"new_sensor_suite", "Oregon_Shelf_suite"}
STATUS_GROUP = {
    "OPERATIONAL": "operating", "PARTIALLY_FUNCTIONAL": "operating",
    "NOT_DEPLOYED": "offline", "RETIRED": "offline", "SUPERSEDED": "offline",
    "RECOVERED": "offline", "UNCABLED": "offline",
    "PLANNED": "planned", "UNKNOWN": "unknown",
}


def load_status_index(entities: list[dict], crosswalk: list[dict]) -> dict[str, dict]:
    by_refdes = {e["reference_designator"]: e for e in entities if e.get("entity_type") == "instrument"}
    index = {}
    for row in crosswalk:
        if row.get("match_type") != "exact_reference_designator" or not row.get("instrument_graph_id"):
            continue
        ent = by_refdes.get(row["reference_designator"])
        if ent:
            index[row["instrument_graph_id"]] = {"status": ent["operational_status"],
                                                 "refdes": row["reference_designator"],
                                                 "asOf": ent.get("retrieved_at")}
    return index


def resolve(record: dict, index: dict[str, dict]) -> dict:
    hit = index.get(record["instrumentId"])
    if hit:
        return {"status": hit["status"], "statusSource": "Nereus snapshot", "statusAsOf": hit["asOf"]}
    if record.get("coszoRole") in PLANNED_ROLES:
        return {"status": "PLANNED", "statusSource": "Inventory: new COSZO sensor", "statusAsOf": None}
    return {"status": "UNKNOWN", "statusSource": None, "statusAsOf": None}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_status -v`
Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_map_data/status.py src/atlas_map_data/tests/test_status.py
git commit -m "Resolve atlas sensor status from Nereus, COSZO plans, or unknown"
```

---

### Task 4: Terrain grids

**Files:**
- Create: `src/atlas_map_data/terrain.py`
- Test: `src/atlas_map_data/tests/test_terrain.py`, `src/atlas_map_data/tests/fixtures/tiny.asc`

**Interfaces:**
- Produces:
  - `terrain.GRIDS: dict[str, dict]` with keys `overview`, `axial` and `hydrate`. Each value is `{north, south, east, west, resolution}`.
  - `terrain.Grid`, a dataclass with fields `name, ncols, nrows, west, south, cellsize, values: array('h')`, and these methods:
    - `.sample(lon, lat) -> float | None`, bilinear sampling in meters, where negative means below sea level
    - `.bounds() -> tuple[west, south, east, north]`
    - `.meta() -> dict`
  - `terrain.read_esri_ascii(path: Path, name: str) -> Grid`
  - `terrain.write_bin(grid: Grid, path: Path) -> None`, which writes little-endian Int16
  - `terrain.read_bin(path: Path, meta: dict, name: str) -> Grid`
  - `terrain.Stack(grids: list[Grid])`, ordered finest first, with:
    - `.elev(lon, lat) -> float`
    - `.covered(lon, lat) -> bool`
    - `.FALLBACK = -2500.0`
  - `terrain.fetch_gmrt(name: str, dest: Path, urlopen=urllib.request.urlopen) -> Path`

- [ ] **Step 1: Write the fixture and the failing test**

`src/atlas_map_data/tests/fixtures/tiny.asc`, a 3×2 grid where row 0 is the north edge:
```text
ncols 3
nrows 2
xllcorner -130.0
yllcorner 45.0
cellsize 0.1
nodata_value -2147483648
-1000 -1100 -1200
-2000 -2100 -2147483648
```

`src/atlas_map_data/tests/test_terrain.py`:
```python
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import terrain

FIX = Path(__file__).parent / "fixtures" / "tiny.asc"


class TerrainTest(unittest.TestCase):
    def setUp(self):
        self.g = terrain.read_esri_ascii(FIX, "tiny")

    def test_header_and_nodata(self):
        self.assertEqual((self.g.ncols, self.g.nrows), (3, 2))
        self.assertEqual(list(self.g.values), [-1000, -1100, -1200, -2000, -2100, -3000])

    def test_sample_at_cell_centers(self):
        # row 0 (north) cell centers are at lat 45.15; row 1 at 45.05
        self.assertAlmostEqual(self.g.sample(-129.95, 45.15), -1000)
        self.assertAlmostEqual(self.g.sample(-129.85, 45.05), -2100)

    def test_bilinear_between_centers(self):
        self.assertAlmostEqual(self.g.sample(-129.90, 45.15), -1050)

    def test_outside_is_none(self):
        self.assertIsNone(self.g.sample(-131.0, 45.1))

    def test_bin_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiny.bin"
            terrain.write_bin(self.g, p)
            self.assertEqual(p.stat().st_size, 12)
            back = terrain.read_bin(p, self.g.meta(), "tiny")
            self.assertEqual(list(back.values), list(self.g.values))

    def test_stack_prefers_first_grid_and_falls_back(self):
        s = terrain.Stack([self.g])
        self.assertAlmostEqual(s.elev(-129.95, 45.15), -1000)
        self.assertFalse(s.covered(-140.0, 45.0))
        self.assertEqual(s.elev(-140.0, 45.0), terrain.Stack.FALLBACK)

    def test_fetch_builds_gmrt_url_and_writes_file(self):
        seen = {}

        class Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(url, timeout):
            seen["url"] = url
            return Resp(FIX.read_bytes())

        with tempfile.TemporaryDirectory() as d:
            out = terrain.fetch_gmrt("axial", Path(d), urlopen=fake_urlopen)
            self.assertTrue(out.exists())
        self.assertIn("gmrt.org/services/GridServer", seen["url"])
        self.assertIn("format=esriascii", seen["url"])
        self.assertIn("resolution=high", seen["url"])
        self.assertIn("north=46.08", seen["url"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_terrain -v`
Expected: ERROR `cannot import name 'terrain'`

- [ ] **Step 3: Implement**

`src/atlas_map_data/terrain.py`:
```python
"""GMRT seafloor grids: fetch (ESRI ASCII), parse, sample, and write compact Int16 files."""
from __future__ import annotations

import array
import math
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GMRT_URL = "https://www.gmrt.org/services/GridServer"
CREDIT = "GMRT, Ryan et al. (2009), CC BY 4.0"
NODATA_FILL = -3000
GRIDS = {
    "axial": {"north": 46.08, "south": 45.78, "east": -129.6, "west": -130.15, "resolution": "high"},
    "hydrate": {"north": 44.75, "south": 44.35, "east": -124.9, "west": -125.5, "resolution": "high"},
    "overview": {"north": 46.35, "south": 43.95, "east": -123.7, "west": -130.6, "resolution": "med"},
}
FINEST_FIRST = ["axial", "hydrate", "overview"]


@dataclass
class Grid:
    name: str
    ncols: int
    nrows: int
    west: float
    south: float
    cellsize: float
    values: array.array

    def _h(self, r: int, c: int) -> float:
        r = min(self.nrows - 1, max(0, r))
        c = min(self.ncols - 1, max(0, c))
        return self.values[r * self.ncols + c]

    def sample(self, lon: float, lat: float) -> float | None:
        fc = (lon - self.west) / self.cellsize - 0.5
        fr = self.nrows - (lat - self.south) / self.cellsize - 0.5   # row 0 is the north edge
        if fc < -0.5 or fr < -0.5 or fc > self.ncols - 0.5 or fr > self.nrows - 0.5:
            return None
        c0, r0 = math.floor(fc), math.floor(fr)
        tc, tr = fc - c0, fr - r0
        top = self._h(r0, c0) * (1 - tc) + self._h(r0, c0 + 1) * tc
        bottom = self._h(r0 + 1, c0) * (1 - tc) + self._h(r0 + 1, c0 + 1) * tc
        return top * (1 - tr) + bottom * tr

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.west + self.ncols * self.cellsize, self.south + self.nrows * self.cellsize)

    def meta(self) -> dict:
        return {"ncols": self.ncols, "nrows": self.nrows, "west": self.west, "south": self.south,
                "cellsize": self.cellsize, "min": min(self.values), "max": max(self.values)}


def read_esri_ascii(path: Path, name: str) -> Grid:
    with open(path, encoding="ascii") as fh:
        header = {}
        for _ in range(6):
            key, value = fh.readline().split()
            header[key.lower()] = float(value)
        nodata = header["nodata_value"]
        values = array.array("h")
        for line in fh:
            for token in line.split():
                v = float(token)
                values.append(NODATA_FILL if v == nodata else int(max(-32000, min(32000, round(v)))))
    return Grid(name, int(header["ncols"]), int(header["nrows"]), header["xllcorner"],
                header["yllcorner"], header["cellsize"], values)


def write_bin(grid: Grid, path: Path) -> None:
    data = array.array("h", grid.values)
    if sys.byteorder != "little":
        data.byteswap()
    path.write_bytes(data.tobytes())


def read_bin(path: Path, meta: dict, name: str) -> Grid:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if sys.byteorder != "little":
        values.byteswap()
    return Grid(name, meta["ncols"], meta["nrows"], meta["west"], meta["south"], meta["cellsize"], values)


class Stack:
    FALLBACK = -2500.0

    def __init__(self, grids: list[Grid]):
        self.grids = grids

    def covered(self, lon: float, lat: float) -> bool:
        return any(g.sample(lon, lat) is not None for g in self.grids)

    def elev(self, lon: float, lat: float) -> float:
        for g in self.grids:
            v = g.sample(lon, lat)
            if v is not None:
                return v
        return self.FALLBACK


def fetch_gmrt(name: str, dest: Path, urlopen=urllib.request.urlopen) -> Path:
    spec = GRIDS[name]
    query = urllib.parse.urlencode({**{k: spec[k] for k in ("north", "south", "east", "west")},
                                    "layer": "topo", "format": "esriascii", "resolution": spec["resolution"]})
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{name}.asc"
    with urlopen(f"{GMRT_URL}?{query}", timeout=300) as resp:
        out.write_bytes(resp.read())
    return out
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_terrain -v`
Expected: 7 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_map_data/terrain.py src/atlas_map_data/tests/test_terrain.py src/atlas_map_data/tests/fixtures/tiny.asc
git commit -m "Add GMRT terrain fetch, parsing, sampling, and Int16 output"
```

---

### Task 5: Data-access routes and external caches

**Files:**
- Create: `src/atlas_map_data/access.py`
- Test: `src/atlas_map_data/tests/test_access.py`

**Interfaces:**
- Consumes: sensor records (`id`, `instrumentId`, `refdes`, `sources`)
- Produces:
  - `access.erddap_dataset_id(refdes: str) -> str`, returning `"ooi-" + refdes.lower()`
  - `access.earthscope_station(record: dict) -> tuple[str, str] | None`, returning `(network, station)`
  - `access.load_external(runtime: Path) -> dict`. It returns `{"erddap": set[str], "qaqc": set[str], "warnings": list[str]}`.
  - `access.refresh_erddap(runtime: Path, urlopen=...) -> int`, which writes `erddap_datasets.json` and returns the count
  - `access.refresh_qaqc(runtime: Path, index_paths: list[str]) -> int`, which writes `qaqc_refdes.json`
  - `access.build_access(record, external, pi_endpoints: dict[str, list[dict]], vertical_channels: dict[str, str]) -> list[dict]`. Each entry is `{kind, label, url, how}`, and an entry may also carry `datasetId`, `network`, `station`, `channel`, `instrumentKey` or `refdes`.
- `kind` values: `erddap`, `qaqc`, `pi_portal`, `earthscope`, `ooi_explorer`, `documentation`.

- [ ] **Step 1: Write the failing test**

`src/atlas_map_data/tests/test_access.py`:
```python
import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import access

EXT = {"erddap": {"ooi-rs03axps-pc03a-4a-ctdpfa303"}, "qaqc": {"RS03AXPS-PC03A-4A-CTDPFA303"}, "warnings": []}
PI = {"INSTRUMENT-pi": [{"instrument_key": "PI-COVIS", "label": "COVIS raw", "url": "http://piweb.ooirsn.uw.edu/covis/data/COVIS/raw/"}]}


def rec(**kw):
    base = {"id": "X", "instrumentId": "INSTRUMENT-x", "refdes": None, "sources": []}
    base.update(kw)
    return base


class AccessTest(unittest.TestCase):
    def test_erddap_id_pattern(self):
        self.assertEqual(access.erddap_dataset_id("RS03AXPS-PC03A-4A-CTDPFA303"), "ooi-rs03axps-pc03a-4a-ctdpfa303")

    def test_ooi_sensor_with_feed_and_plots(self):
        routes = access.build_access(rec(refdes="RS03AXPS-PC03A-4A-CTDPFA303"), EXT, PI, {})
        kinds = [r["kind"] for r in routes]
        self.assertEqual(kinds[:3], ["erddap", "qaqc", "ooi_explorer"])
        erd = routes[0]
        self.assertEqual(erd["datasetId"], "ooi-rs03axps-pc03a-4a-ctdpfa303")
        self.assertTrue(erd["url"].startswith("https://erddap.dataexplorer.oceanobservatories.org/erddap/tabledap/"))

    def test_ooi_sensor_without_public_feed_has_no_erddap(self):
        routes = access.build_access(rec(refdes="RS01SBPD-DP01A-01-CTDPFL104"), EXT, PI, {})
        self.assertNotIn("erddap", [r["kind"] for r in routes])
        self.assertIn("ooi_explorer", [r["kind"] for r in routes])

    def test_earthscope_station(self):
        r = rec(id="EARTHSCOPE-OO-AXCC1")
        self.assertEqual(access.earthscope_station(r), ("OO", "AXCC1"))
        routes = access.build_access(r, EXT, PI, {"OO.AXCC1": "HHZ"})
        es = [x for x in routes if x["kind"] == "earthscope"][0]
        self.assertEqual((es["network"], es["station"], es["channel"]), ("OO", "AXCC1", "HHZ"))

    def test_pi_portal_endpoints(self):
        routes = access.build_access(rec(instrumentId="INSTRUMENT-pi"), EXT, PI, {})
        pi = [x for x in routes if x["kind"] == "pi_portal"]
        self.assertEqual(pi[0]["instrumentKey"], "PI-COVIS")
        self.assertEqual(pi[0]["url"], "http://piweb.ooirsn.uw.edu/covis/data/COVIS/raw/")

    def test_documentation_only_sensor(self):
        routes = access.build_access(rec(sources=["https://coszo.org/x"]), EXT, PI, {})
        self.assertEqual([r["kind"] for r in routes], ["documentation"])

    def test_disallowed_hosts_are_dropped(self):
        routes = access.build_access(rec(sources=["https://evil.example.com/x", "http://10.0.0.5/x"]), EXT, PI, {})
        self.assertEqual(routes, [])

    def test_missing_caches_warn_but_do_not_fail(self):
        with tempfile.TemporaryDirectory() as d:
            ext = access.load_external(Path(d))
        self.assertEqual(ext["erddap"], set())
        self.assertEqual(ext["qaqc"], set())
        self.assertEqual(len(ext["warnings"]), 2)

    def test_refresh_qaqc_parses_refdes_from_plot_paths(self):
        paths = ["RS03AXPS/RS03AXPS-PC03A-4A-CTDPFA303_temperature_week_none_full.png",
                 "CE04OSPS/CE04OSPS-SF01B-2A-CTDPFA107_salinity_day_none_full.png"]
        with tempfile.TemporaryDirectory() as d:
            n = access.refresh_qaqc(Path(d), paths)
            saved = json.loads((Path(d) / "qaqc_refdes.json").read_text())
        self.assertEqual(n, 1)
        self.assertEqual(saved["refdes"], ["RS03AXPS-PC03A-4A-CTDPFA303"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_access -v`
Expected: ERROR `cannot import name 'access'`

- [ ] **Step 3: Implement**

`src/atlas_map_data/access.py`:
```python
"""Per-sensor data-access routes. External coverage lists are cached by explicit refresh steps."""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ERDDAP = "https://erddap.dataexplorer.oceanobservatories.org/erddap"
QAQC = "https://ec2.qaqc.ooi-rca.net"
OOI_EXPLORER = "https://dataexplorer.oceanobservatories.org"
ALLOWED_HOSTS = {
    "erddap.dataexplorer.oceanobservatories.org", "dataexplorer.oceanobservatories.org",
    "oceanobservatories.org", "ooinet.oceanobservatories.org", "ec2.qaqc.ooi-rca.net",
    "piweb.ooirsn.uw.edu", "service.earthscope.org", "ds.iris.edu", "www.earthscope.org",
    "interactiveoceans.washington.edu", "coszo.org", "www.coszo.org", "github.com", "doi.org",
}


def erddap_dataset_id(refdes: str) -> str:
    return "ooi-" + refdes.lower()


def earthscope_station(record: dict) -> tuple[str, str] | None:
    m = re.fullmatch(r"EARTHSCOPE-([A-Z0-9]+)-([A-Z0-9]+)", record["id"])
    return (m.group(1), m.group(2)) if m else None


def _allowed(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ALLOWED_HOSTS


def load_external(runtime: Path) -> dict:
    out = {"erddap": set(), "qaqc": set(), "warnings": []}
    for key, name, field in (("erddap", "erddap_datasets.json", "datasetIds"), ("qaqc", "qaqc_refdes.json", "refdes")):
        path = runtime / name
        if path.exists():
            out[key] = set(json.loads(path.read_text())[field])
        else:
            out["warnings"].append(f"{name} missing; run build_atlas_bundle.py --refresh-external")
    return out


def refresh_erddap(runtime: Path, urlopen=urllib.request.urlopen) -> int:
    url = f"{ERDDAP}/tabledap/allDatasets.csv?datasetID&datasetID=~%22ooi-rs.*%22"
    with urlopen(url, timeout=60) as resp:
        rows = list(csv.reader(io.StringIO(resp.read().decode("utf-8"))))
    ids = sorted({r[0] for r in rows[2:] if r and r[0].startswith("ooi-rs")})
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "erddap_datasets.json").write_text(json.dumps(
        {"retrievedAt": datetime.now(timezone.utc).isoformat(), "source": url, "datasetIds": ids}, indent=1))
    return len(ids)


def refresh_qaqc(runtime: Path, index_paths: list[str]) -> int:
    refdes = sorted({p.rsplit("/", 1)[-1].split("_", 1)[0] for p in index_paths if p.startswith("RS")})
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "qaqc_refdes.json").write_text(json.dumps(
        {"retrievedAt": datetime.now(timezone.utc).isoformat(), "source": f"{QAQC}/QAQC_plots/index.json",
         "refdes": refdes}, indent=1))
    return len(refdes)


def build_access(record: dict, external: dict, pi_endpoints: dict[str, list[dict]],
                 vertical_channels: dict[str, str]) -> list[dict]:
    routes: list[dict] = []
    refdes = record.get("refdes")
    if refdes:
        ds = erddap_dataset_id(refdes)
        if ds in external["erddap"]:
            routes.append({"kind": "erddap", "label": "OOI ERDDAP (public, no login)", "datasetId": ds,
                           "url": f"{ERDDAP}/tabledap/{ds}.html",
                           "how": "Choose variables and a time range, then download CSV or NetCDF."})
        if refdes in external["qaqc"]:
            routes.append({"kind": "qaqc", "label": "RCA QA/QC plots", "refdes": refdes,
                           "url": f"{QAQC}/", "how": "Pre-rendered charts of recent data, updated by the RCA team."})
        routes.append({"kind": "ooi_explorer", "label": "OOI Data Explorer", "refdes": refdes,
                       "url": f"{OOI_EXPLORER}/#ooi/search/{urllib.parse.quote(refdes)}",
                       "how": "Browse and request OOI data products for this instrument."})
    station = earthscope_station(record)
    if station:
        net, sta = station
        routes.append({"kind": "earthscope", "label": "EarthScope FDSN", "network": net, "station": sta,
                       "channel": vertical_channels.get(f"{net}.{sta}"),
                       "url": f"https://service.earthscope.org/fdsnws/station/1/query?net={net}&sta={sta}&level=channel&format=text",
                       "how": "Public seismic waveforms (MiniSEED) and station metadata; no login."})
    for ep in pi_endpoints.get(record["instrumentId"], []):
        routes.append({"kind": "pi_portal", "label": f"PI data portal: {ep['label']}", "instrumentKey": ep["instrument_key"],
                       "url": ep["url"], "how": "Public directory listing; open folders by date to find files."})
    if not routes:
        for url in record.get("sources", []):
            if _allowed(url):
                routes.append({"kind": "documentation", "label": "Documentation", "url": url,
                               "how": "No public data feed is known yet; this page documents the sensor."})
    return [r for r in routes if _allowed(r["url"])]
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_access -v`
Expected: 9 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_map_data/access.py src/atlas_map_data/tests/test_access.py
git commit -m "Derive per-sensor data access routes with cached ERDDAP and QA/QC coverage"
```

---

### Task 6: Sites, regions, and water columns

**Files:**
- Create: `src/atlas_map_data/sites.py`
- Test: `src/atlas_map_data/tests/test_sites.py`

**Interfaces:**
- Consumes: sensor records (`lat`, `lon`, `family`, `status`, `node`, `depthRange`, `depth`, `location`, `siteCode`), and `terrain.Stack.elev`
- Produces:
  - `sites.REGIONS: list[dict]` with keys `key, label, lonMin, lonMax, view`. `view` is `{ll: [lon, lat], dist, polar, az, exag}`.
  - `sites.region_for(lon: float) -> str`
  - `sites.build_sites(located: list[dict], unlocated: list[dict], elev: Callable[[float, float], float]) -> tuple[list[dict], list[dict]]`. It returns `(sites, unplaced)`. Each site dict has keys `id, name, label, region, lat, lon, seafloor, sensorIds, parts, column, unlocatedIds`. `column` is a list of `{kind, a, b}`. Every sensor gets `site` (the site id) and `region`, mutated in place.

- [ ] **Step 1: Write the failing test**

`src/atlas_map_data/tests/test_sites.py`:
```python
import unittest

from atlas_map_data import sites


def s(id, lat, lon, loc="Axial Seamount Base", node="MJ03A", depth=2607, rng=None, code="RS03AXBS"):
    return {"id": id, "lat": lat, "lon": lon, "location": loc, "node": node, "depth": depth,
            "depthRange": rng, "siteCode": code, "family": "chemistry", "status": "OPERATIONAL"}


FLAT = lambda lon, lat: -2614.0


class SitesTest(unittest.TestCase):
    def test_colocated_platforms_merge_into_one_site_named_for_the_seafloor(self):
        located = [
            s("base-ctd", 45.8168, -129.754),
            s("sp-ctd", 45.8168, -129.754, loc="Axial Seamount Profiler", node="SF03A", depth=5, rng=[5, 200], code="RS03AXPS"),
            s("dp-ctd", 45.81685, -129.75405, loc="Axial Seamount Deep Profiler", node="DP03A", depth=250, rng=[250, 2457], code="RS03AXPD"),
        ]
        result, unplaced = sites.build_sites(located, [], FLAT)
        self.assertEqual(len(result), 1)
        site = result[0]
        self.assertEqual(site["name"], "Axial Seamount Base")
        self.assertEqual(site["label"], "Axial Base")
        self.assertEqual(site["region"], "axial")
        self.assertEqual(site["seafloor"], 2614)
        self.assertEqual(set(site["sensorIds"]), {"base-ctd", "sp-ctd", "dp-ctd"})
        self.assertEqual(site["parts"], ["Axial Seamount Base", "Axial Seamount Profiler", "Axial Seamount Deep Profiler"])
        self.assertEqual(site["column"], [{"kind": "Shallow profiler", "a": 5, "b": 200},
                                          {"kind": "Deep profiler", "a": 250, "b": 2457}])
        self.assertTrue(all(x["site"] == site["id"] for x in located))

    def test_sensors_150m_apart_are_separate_sites(self):
        a, b = s("a", 45.9, -130.0), s("b", 45.9, -130.0 + 0.0025)   # ~195 m east
        result, _ = sites.build_sites([a, b], [], FLAT)
        self.assertEqual(len(result), 2)

    def test_regions_by_longitude(self):
        self.assertEqual(sites.region_for(-130.0), "axial")
        self.assertEqual(sites.region_for(-125.39), "slope")
        self.assertEqual(sites.region_for(-125.15), "hydrate")
        self.assertEqual(sites.region_for(-124.3), "shelf")

    def test_sensor_without_depth_still_gets_a_site(self):
        result, _ = sites.build_sites([s("nodepth", 44.6, -124.3, loc="Oregon Shelf", depth=None, code=None)], [], FLAT)
        self.assertEqual(result[0]["seafloor"], 2614)
        self.assertEqual(result[0]["column"], [])

    def test_unlocated_sensors_attach_by_site_code_or_location(self):
        located = [s("a", 45.9, -130.0, loc="Axial Seamount Base", code="RS03AXBS")]
        by_code = s("u1", None, None, loc="somewhere", code="RS03AXBS")
        by_loc = s("u2", None, None, loc="Axial Seamount Base", code=None)
        orphan = s("u3", None, None, loc="Nowhere Ridge", code="RS09XXXX")
        result, unplaced = sites.build_sites(located, [by_code, by_loc, orphan], FLAT)
        self.assertEqual(result[0]["unlocatedIds"], ["u1", "u2"])
        self.assertEqual([u["id"] for u in unplaced], ["u3"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_sites -v`
Expected: ERROR `cannot import name 'sites'`

- [ ] **Step 3: Implement**

`src/atlas_map_data/sites.py`:
```python
"""Physical sites (sensors within 150 m), regions, and water-column reach."""
from __future__ import annotations

import math
import re
from typing import Callable

from .sensors import COLUMN_KIND

KX = 111.32 * math.cos(math.radians(45.15))
KZ = 111.13
SITE_RADIUS_KM = 0.15

REGIONS = [
    {"key": "axial", "label": "Axial Seamount", "lonMin": -180.0, "lonMax": -129.0,
     "view": {"ll": [-129.885, 45.885], "dist": 62, "polar": 0.72, "az": -0.3, "exag": 3}},
    {"key": "slope", "label": "Oregon Slope Base", "lonMin": -129.0, "lonMax": -125.3,
     "view": {"ll": [-125.39, 44.51], "dist": 14, "polar": 0.95, "az": -0.4, "exag": 2.5}},
    {"key": "hydrate", "label": "Hydrate Ridge", "lonMin": -125.3, "lonMax": -124.9,
     "view": {"ll": [-125.12, 44.57], "dist": 22, "polar": 0.92, "az": -0.4, "exag": 2.5}},
    {"key": "shelf", "label": "Oregon Shelf", "lonMin": -124.9, "lonMax": 0.0,
     "view": {"ll": [-124.62, 44.56], "dist": 95, "polar": 0.86, "az": -0.25, "exag": 4}},
]
OVERVIEW_VIEW = {"ll": [-126.75, 45.02], "dist": 650, "polar": 0.84, "az": 0.0, "exag": 6}


def region_for(lon: float) -> str:
    for r in REGIONS:
        if r["lonMin"] <= lon < r["lonMax"]:
            return r["key"]
    raise ValueError(f"longitude {lon} is outside every region")


def _km(a: dict, b: dict) -> float:
    return math.hypot((a["lon"] - b["lon"]) * KX, (a["lat"] - b["lat"]) * KZ)


def _in_water(sensor: dict, seafloor: float) -> bool:
    return bool(sensor.get("depthRange")) or (sensor.get("depth") is not None and sensor["depth"] < seafloor - 60)


def _label(name: str) -> str:
    return name.replace(", Axial Seamount", "").replace("Axial Seamount ", "Axial ")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_sites(located: list[dict], unlocated: list[dict],
                elev: Callable[[float, float], float]) -> tuple[list[dict], list[dict]]:
    clusters: list[list[dict]] = []
    for sensor in sorted(located, key=lambda x: (x["lat"], x["lon"], x["id"])):
        home = next((c for c in clusters if any(_km(sensor, m) < SITE_RADIUS_KM for m in c)), None)
        if home is None:
            clusters.append([sensor])
        else:
            home.append(sensor)

    result, used_ids = [], set()
    for members in clusters:
        lat = sum(m["lat"] for m in members) / len(members)
        lon = sum(m["lon"] for m in members) / len(members)
        seafloor = int(round(-elev(lon, lat)))
        weights: dict[str, int] = {}
        for m in members:
            name = m.get("location") or m.get("siteCode") or "Unnamed site"
            weights[name] = weights.get(name, 0) + (1 if _in_water(m, seafloor) else 100)
        name = max(weights, key=lambda k: (weights[k], k))
        parts = list(dict.fromkeys(m.get("location") or m.get("siteCode") or "Unnamed site" for m in members))
        column: dict[str, list[int]] = {}
        for m in members:
            if not _in_water(m, seafloor):
                continue
            kind = COLUMN_KIND.get((m.get("node") or "")[:2], "Water-column sensor")
            a, b = m["depthRange"] or [m["depth"], m["depth"]]
            column[kind] = [min(column[kind][0], a), max(column[kind][1], b)] if kind in column else [a, b]
        base_id = _slug(name)
        site_id = base_id
        n = 2
        while site_id in used_ids:
            site_id, n = f"{base_id}-{n}", n + 1
        used_ids.add(site_id)
        region = region_for(lon)
        for m in members:
            m["site"], m["region"] = site_id, region
        result.append({
            "id": site_id, "name": name, "label": _label(name), "region": region,
            "lat": round(lat, 6), "lon": round(lon, 6), "seafloor": seafloor,
            "sensorIds": [m["id"] for m in members], "parts": parts,
            "column": sorted(({"kind": k, "a": v[0], "b": v[1]} for k, v in column.items()), key=lambda c: c["a"]),
            "unlocatedIds": [],
        })

    unplaced = []
    for u in unlocated:
        home = next((t for t in result if any(
            (u.get("siteCode") and m.get("siteCode") == u["siteCode"]) or
            (u.get("location") and m.get("location") == u["location"])
            for m in located if m["site"] == t["id"])), None)
        if home:
            home["unlocatedIds"].append(u["id"])
            u["site"], u["region"] = home["id"], home["region"]
        else:
            unplaced.append(u)
    return result, unplaced
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_sites -v`
Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add src/atlas_map_data/sites.py src/atlas_map_data/tests/test_sites.py
git commit -m "Group atlas sensors into physical sites with regions and water-column reach"
```

---

### Task 7: Cable route

**Files:**
- Create: `src/atlas_map_data/cable.py`, `src/atlas_map_data/cable/README.md`
- Copy in: `src/atlas_map_data/cable/rca_cable.geojson`, `src/atlas_map_data/cable/build_geojson.py`, `src/atlas_map_data/cable/skeleton.py` (from `.context/cable/`)
- Test: `src/atlas_map_data/tests/test_cable.py`

**Interfaces:**
- Produces: `cable.load_cable(path: Path) -> dict`. It returns `{"lines": [...], "nodes": [...], "hidden": int}`.
  - Each line is `{name, kind, route, accuracy, lengthKm, source, coords}`.
  - Each node is `{code, name, accuracy, note, lon, lat, description}`.
  - `hidden` counts undocumented stubs and duplicate paths left off the map.

- [ ] **Step 1: Copy the researched route into the repo**

```bash
mkdir -p src/atlas_map_data/cable
cp .context/cable/rca_cable.geojson .context/cable/build_geojson.py .context/cable/skeleton.py src/atlas_map_data/cable/
```

`src/atlas_map_data/cable/README.md`:
```markdown
# RCA cable route

`rca_cable.geojson` was built on 2026-09-23 by `build_geojson.py` and `skeleton.py`. The scripts need shapely, pyproj and networkx; they are not needed to build the atlas bundle.

- **Charted (~85% of length):** NOAA/BOEM Marine Cadastre "Submarine Cable Areas", records 506 and 508 ("RSN Backbone Cable"). These are public domain and not for navigation. The ~61 m right-of-way strips were reduced to centerlines.
- **Approximate (~88 km):** from the US EEZ limit to PN3A and PN3A to PN3B. No public geometry exists there, so these are straight lines. PN3A uses the MJ03A junction box as a stand-in; PN3B is the center of its avoidance box (±2 km).
- **Nodes:** from OOI mariner safety notices, OOI asset-management, and the COSZO ship-time request in the corpus.
- **Better data:** the UW RCA team (ioceans@uw.edu) shares as-laid route files on request.
```

- [ ] **Step 2: Write the failing test**

`src/atlas_map_data/tests/test_cable.py`:
```python
import unittest
from pathlib import Path

from atlas_map_data import cable

GEOJSON = Path(cable.__file__).with_name("cable") / "rca_cable.geojson"


class CableTest(unittest.TestCase):
    def setUp(self):
        self.c = cable.load_cable(GEOJSON)

    def test_undocumented_segments_are_left_off(self):
        names = [l["name"] for l in self.c["lines"]]
        self.assertFalse(any(n.startswith("Unidentified") for n in names))
        self.assertFalse(any("path B" in n for n in names))
        self.assertEqual(self.c["hidden"], 5)

    def test_lines_split_kind_and_route(self):
        north = [l for l in self.c["lines"] if l["route"].startswith("Pacific City landfall") and l["kind"] == "North backbone"]
        self.assertEqual(len(north), 1)
        self.assertEqual(north[0]["accuracy"], "charted")
        self.assertIn("→", north[0]["route"])

    def test_approximate_segments_reach_axial(self):
        approx = [l for l in self.c["lines"] if l["accuracy"] == "approximate"]
        self.assertEqual(len(approx), 2)
        self.assertTrue(all(l["kind"] == "North backbone" for l in approx))

    def test_primary_nodes(self):
        codes = sorted(n["code"] for n in self.c["nodes"])
        self.assertEqual(codes, ["PN1A", "PN1B", "PN1C", "PN1D", "PN3A", "PN3B", "PN5A"])
        pn5a = [n for n in self.c["nodes"] if n["code"] == "PN5A"][0]
        self.assertIn("placeholder", pn5a["description"].lower())
        pn3a = [n for n in self.c["nodes"] if n["code"] == "PN3A"][0]
        self.assertEqual(pn3a["name"], "PN3A (Axial Base)")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_cable -v`
Expected: ERROR `cannot import name 'cable'`

- [ ] **Step 4: Implement**

`src/atlas_map_data/cable.py`:
```python
"""Researched RCA cable GeoJSON → the atlas cable file (visible lines + primary nodes)."""
from __future__ import annotations

import json
import re
from pathlib import Path

# Wording from OOI's own pages in the corpus (data/Websites).
NODE_DESCRIPTION = {
    "PN5A": "Placeholder node with minimal internal electronics, available for future network expansion. No sensors connect here.",
}
PRIMARY = "Primary node: a seafloor hub that takes power and data from the backbone cable and passes it to nearby sites."


def _hidden(name: str) -> bool:
    return name.startswith("Unidentified") or "path B" in name


def load_cable(path: Path) -> dict:
    features = json.loads(path.read_text())["features"]
    lines, nodes, hidden = [], [], 0
    for f in features:
        p, g = f["properties"], f["geometry"]
        if g["type"] == "Point":
            if re.match(r"PN\d[A-Z]", p["name"]):
                code = p["name"].split(" ")[0]
                nodes.append({"code": code, "name": re.sub(r"\s*-\s*(proxy|approximate)$", "", p["name"]),
                              "accuracy": p["accuracy"], "note": p.get("note", ""),
                              "lon": g["coordinates"][0], "lat": g["coordinates"][1],
                              "description": NODE_DESCRIPTION.get(code, PRIMARY)})
            continue
        if _hidden(p["name"]):
            hidden += 1
            continue
        kind, route = p["name"].split(":", 1) if ":" in p["name"] else ("RCA cable", p["name"])
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for coords in parts:
            lines.append({"name": p["name"], "kind": re.sub(r"\s*\(approximate\)", "", kind).strip(),
                          "route": route.strip().replace("->", "→"), "accuracy": p["accuracy"],
                          "lengthKm": p.get("length_km"), "source": p.get("source"),
                          "coords": [[round(x, 6), round(y, 6)] for x, y in coords]})
    return {"lines": lines, "nodes": nodes, "hidden": hidden}
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_cable -v`
Expected: 4 tests, OK.

- [ ] **Step 6: Commit**

```bash
git add src/atlas_map_data/cable.py src/atlas_map_data/cable/ src/atlas_map_data/tests/test_cable.py
git commit -m "Add researched RCA cable route and convert it for the atlas"
```

---

### Task 8: Validation, the build CLI, and a full-corpus build

**Files:**
- Create: `src/atlas_map_data/validate.py`, `src/atlas_map_data/build_atlas_bundle.py`, `src/atlas_map_data/README.md`
- Test: `src/atlas_map_data/tests/test_validate.py`, `src/atlas_map_data/tests/test_full_build.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `validate.validate(sensors: list[dict], sites: list[dict], unplaced: list[dict], total_rows: int, stack: terrain.Stack) -> list[str]`, which returns error strings; empty means valid.
  - `build_atlas_bundle.build(out: Path, runtime: Path, data: Path) -> dict`, which returns a summary dict.
  - `build_atlas_bundle.main(argv: list[str] | None = None) -> int`
- Bundle files written to `out`:
  - `families.json`
  - `sensors.json`, which is `{"sensors": [...], "unplaced": [...]}`
  - `sites.json`
  - `regions.json`, which is `{"overview": view, "regions": [...]}`
  - `cable.json`
  - `terrain/terrain.json`, which holds the three grid metas plus `credit`
  - `terrain/{axial,hydrate,overview}.bin`
  - `manifest.json`, which holds counts, `builtAt`, `corpusSnapshot` and warnings

- [ ] **Step 1: Write the failing validation test**

`src/atlas_map_data/tests/test_validate.py`:
```python
import unittest

from atlas_map_data import validate


class FlatStack:
    FALLBACK = -2500.0
    def elev(self, lon, lat): return -1500.0
    def covered(self, lon, lat): return lon > -131


def sensor(id, depth=1500, rng=None, water=None, corrections=(), lat=45.9, lon=-130.0, site="s1"):
    return {"id": id, "lat": lat, "lon": lon, "depth": depth, "depthRange": rng, "waterDepth": water if water is not None else depth,
            "family": "chemistry", "site": site, "region": "axial", "corrections": list(corrections),
            "status": "OPERATIONAL", "access": []}


SITE = {"id": "s1", "sensorIds": ["a"], "unlocatedIds": []}


class ValidateTest(unittest.TestCase):
    def test_clean_bundle(self):
        self.assertEqual(validate.validate([sensor("a")], [SITE], [], 1, FlatStack()), [])

    def test_depth_mismatch_fails_without_correction(self):
        errs = validate.validate([sensor("a", depth=2607)], [SITE], [], 1, FlatStack())
        self.assertTrue(any("a" in e and "1,107 m" in e for e in errs), errs)

    def test_depth_mismatch_allowed_with_correction(self):
        self.assertEqual(validate.validate([sensor("a", depth=2607, corrections=["moved"])], [SITE], [], 1, FlatStack()), [])

    def test_profilers_are_checked_by_water_depth(self):
        s = sensor("a", depth=5, rng=[5, 200], water=2607)
        errs = validate.validate([s], [SITE], [], 1, FlatStack())
        self.assertEqual(len(errs), 1)

    def test_sensor_without_depth_is_not_depth_checked(self):
        self.assertEqual(validate.validate([sensor("a", depth=None, water=None)], [SITE], [], 1, FlatStack()), [])

    def test_counts_must_reconcile(self):
        errs = validate.validate([sensor("a")], [SITE], [], 2, FlatStack())
        self.assertTrue(any("reconcile" in e for e in errs))

    def test_sensor_outside_terrain_is_flagged(self):
        errs = validate.validate([sensor("a", lon=-140.0)], [SITE], [], 1, FlatStack())
        self.assertTrue(any("outside" in e for e in errs))

    def test_site_references_must_agree(self):
        errs = validate.validate([sensor("a", site="s2")], [SITE], [], 1, FlatStack())
        self.assertTrue(any("site" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_validate -v`
Expected: ERROR `cannot import name 'validate'`

- [ ] **Step 3: Implement validation**

`src/atlas_map_data/validate.py`:
```python
"""Bundle checks. Any returned string fails the build."""
from __future__ import annotations

TOLERANCE_M = 250


def validate(sensors: list[dict], sites: list[dict], unplaced: list[dict], total_rows: int, stack) -> list[str]:
    errors = []
    located = [s for s in sensors if s.get("lat") is not None]
    unlocated = [s for s in sensors if s.get("lat") is None]
    if len(located) + len(unlocated) != total_rows:
        errors.append(f"counts do not reconcile: {len(located)} located + {len(unlocated)} unlocated != {total_rows} inventory rows")
    site_ids = {t["id"] for t in sites}
    listed = {i for t in sites for i in t["sensorIds"] + t["unlocatedIds"]} | {u["id"] for u in unplaced}
    for s in sensors:
        if s["id"] not in listed:
            errors.append(f"{s['id']}: not listed by any site or as unplaced")
        if s.get("lat") is not None and s.get("site") not in site_ids:
            errors.append(f"{s['id']}: site {s.get('site')!r} does not exist")
        if not s.get("family"):
            errors.append(f"{s['id']}: no family")
    for s in located:
        if not stack.covered(s["lon"], s["lat"]):
            errors.append(f"{s['id']}: position {s['lat']}, {s['lon']} is outside every terrain grid")
            continue
        checked = s.get("waterDepth") if s.get("depthRange") else s.get("depth")
        if checked is None or s.get("corrections"):
            continue
        seafloor = -stack.elev(s["lon"], s["lat"])
        if abs(checked - seafloor) > TOLERANCE_M:
            errors.append(f"{s['id']}: listed depth {checked:,.0f} m differs from the seafloor ({seafloor:,.0f} m) "
                          f"by {abs(checked - seafloor):,.0f} m; add a reviewed entry to corrections.json")
    return errors
```

- [ ] **Step 4: Run it and verify it passes**

Run: `PYTHONPATH=src .venv/bin/python -m unittest atlas_map_data.tests.test_validate -v`
Expected: 8 tests, OK.

- [ ] **Step 5: Write the failing full-build test**

`src/atlas_map_data/tests/test_full_build.py`:
```python
"""Builds the real bundle from the restored corpus. Skipped when data/ or the terrain cache is absent."""
import json
import tempfile
import unittest
from pathlib import Path

from atlas_map_data import build_atlas_bundle, paths

READY = (paths.DATA / "Instruments" / "instruments.jsonl").exists() and all(
    (paths.RUNTIME / "terrain" / f"{n}.asc").exists() for n in ("overview", "axial", "hydrate"))


@unittest.skipUnless(READY, "needs restored data/ and `build_atlas_bundle.py --refresh-terrain`")
class FullBuildTest(unittest.TestCase):
    def test_real_corpus_builds_and_reconciles(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            summary = build_atlas_bundle.build(out, paths.RUNTIME, paths.DATA)
            self.assertEqual(summary["errors"], [])
            self.assertEqual(summary["total"], 168)
            self.assertEqual(summary["located"], 155)
            bundle = json.loads((out / "sensors.json").read_text())
            by_id = {s["id"]: s for s in bundle["sensors"]}
            profiler = [s for s in bundle["sensors"] if s["siteCode"] == "RS03AXPS"][0]
            self.assertEqual((profiler["lat"], profiler["lon"]), (45.8168, -129.754))
            self.assertEqual(by_id["EARTHSCOPE-OO-AXCC1"]["family"], "seismic")
            sites = json.loads((out / "sites.json").read_text())["sites"]
            base = [t for t in sites if t["label"] == "Axial Base"]
            self.assertTrue(any(len(t["sensorIds"]) >= 30 for t in base))
            for name in ("overview", "axial", "hydrate"):
                self.assertTrue((out / "terrain" / f"{name}.bin").exists())
            cable = json.loads((out / "cable.json").read_text())
            self.assertEqual(len(cable["nodes"]), 7)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Implement the CLI**

`src/atlas_map_data/build_atlas_bundle.py`:
```python
"""Build the atlas bundle.

  python -m atlas_map_data.build_atlas_bundle                     # offline build from caches
  python -m atlas_map_data.build_atlas_bundle --refresh-terrain   # download GMRT grids first
  python -m atlas_map_data.build_atlas_bundle --refresh-external  # refresh ERDDAP + QA/QC coverage first
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import access, cable, families, paths, sensors, sites, status, terrain, validate
from .corpus import load_jsonl


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _vertical_channels(data: Path) -> dict[str, str]:
    best: dict[str, str] = {}
    for ch in load_jsonl(data / "StationMetadata" / "channels.jsonl"):
        key, code = f"{ch['network']}.{ch['station']}", ch["channel"] or ""
        for preferred in ("HHZ", "BHZ", "EHZ", "SHZ"):
            if code == preferred and (key not in best or ["HHZ", "BHZ", "EHZ", "SHZ"].index(preferred)
                                      < ["HHZ", "BHZ", "EHZ", "SHZ"].index(best[key])):
                best[key] = code
    return best


def _pi_endpoints(data: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ep in load_jsonl(data / "PIPortal" / "endpoints.jsonl"):
        out.setdefault(ep["instrument_id"], []).append(ep)
    return out


def build(out: Path, runtime: Path, data: Path) -> dict:
    rows = load_jsonl(data / "Instruments" / "instruments.jsonl")
    records = [sensors.sensor_from_row(r) for r in rows]
    sensors.apply_corrections(records, sensors.load_corrections(paths.PACKAGE / "corrections.json"))

    index = status.load_status_index(load_jsonl(data / "Nereus" / "graphrag" / "entities.jsonl"),
                                     load_jsonl(data / "Nereus" / "graphrag" / "instrument_crosswalk.jsonl"))
    external = access.load_external(runtime)
    pi = _pi_endpoints(data)
    channels = _vertical_channels(data)
    for r in records:
        r.update(status.resolve(r, index))
        r["statusGroup"] = status.STATUS_GROUP[r["status"]]
        r["access"] = access.build_access(r, external, pi, channels)

    grids = {n: terrain.read_esri_ascii(runtime / "terrain" / f"{n}.asc", n) for n in terrain.FINEST_FIRST}
    stack = terrain.Stack([grids[n] for n in terrain.FINEST_FIRST])
    located = [r for r in records if r["lat"] is not None]
    unlocated = [r for r in records if r["lat"] is None]
    site_list, unplaced = sites.build_sites(located, unlocated, stack.elev)
    errors = validate.validate(records, site_list, unplaced, len(rows), stack)

    if not errors:
        _write(out / "families.json", {"families": families.FAMILIES})
        _write(out / "sensors.json", {"sensors": records, "unplaced": [u["id"] for u in unplaced]})
        _write(out / "sites.json", {"sites": site_list})
        _write(out / "regions.json", {"overview": sites.OVERVIEW_VIEW, "regions": sites.REGIONS})
        _write(out / "cable.json", cable.load_cable(paths.PACKAGE / "cable" / "rca_cable.geojson"))
        for n, g in grids.items():
            (out / "terrain").mkdir(parents=True, exist_ok=True)
            terrain.write_bin(g, out / "terrain" / f"{n}.bin")
        _write(out / "terrain" / "terrain.json", {"credit": terrain.CREDIT, "grids": {n: g.meta() for n, g in grids.items()}})
    summary = {"builtAt": datetime.now(timezone.utc).isoformat(), "total": len(rows), "located": len(located),
               "unlocated": len(unlocated), "unplaced": len(unplaced), "sites": len(site_list),
               "corpusSnapshot": json.loads((data / "Instruments" / "manifest.json").read_text()).get("generated_at")
               if (data / "Instruments" / "manifest.json").exists() else None,
               "warnings": external["warnings"], "errors": errors}
    if not errors:
        _write(out / "manifest.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=paths.BUNDLE)
    ap.add_argument("--refresh-terrain", action="store_true")
    ap.add_argument("--refresh-external", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh_terrain:
        for name in terrain.FINEST_FIRST:
            print(f"downloading GMRT {name} …", flush=True)
            terrain.fetch_gmrt(name, paths.RUNTIME / "terrain")
    if args.refresh_external:
        print(f"ERDDAP datasets: {access.refresh_erddap(paths.RUNTIME)}")
        sys.path.insert(0, str(paths.REPO / "src" / "agentic_qaqc"))
        from qaqc_agent_tools import QAQCToolkit  # his toolkit; stdlib only
        print(f"QA/QC reference designators: {access.refresh_qaqc(paths.RUNTIME, QAQCToolkit().get_index())}")
    summary = build(args.out, paths.RUNTIME, paths.DATA)
    for w in summary["warnings"]:
        print(f"warning: {w}")
    for e in summary["errors"]:
        print(f"error: {e}")
    if summary["errors"]:
        print(f"build failed with {len(summary['errors'])} errors; nothing written")
        return 1
    print(f"wrote {args.out}: {summary['total']} sensors ({summary['located']} located), {summary['sites']} sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`src/atlas_map_data/README.md`:
```markdown
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
```

- [ ] **Step 7: Check that `get_index` exists on his toolkit, then populate the caches**

Run: `grep -n "def get_index" src/agentic_qaqc/qaqc_agent_tools.py`
Expected: one match. If the name differs, use the method that `search_plots` iterates over (`for path in self.get_index()`).

Run: `PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle --refresh-terrain --refresh-external`
Expected output includes:
- `ERDDAP datasets: 63` (the value can drift)
- `QA/QC reference designators: 74` (the value can drift)
- `wrote …/src/atlas_map/public/atlas: 168 sensors (155 located), N sites`, where N is about 29 (the prototype's count)

If the build prints `error:` lines instead, read each one. A depth mismatch means either a real data problem, which gets a reviewed `corrections.json` entry with a reason, or a bug. Never loosen the tolerance to make the build pass.

- [ ] **Step 8: Run the whole suite**

Run: `PYTHONPATH=src .venv/bin/python -m unittest discover -s src/atlas_map_data/tests -t src -v`
Expected: all tests pass, and `FullBuildTest` runs rather than skips.

- [ ] **Step 9: Commit**

```bash
git add src/atlas_map_data/validate.py src/atlas_map_data/build_atlas_bundle.py src/atlas_map_data/README.md src/atlas_map_data/tests/test_validate.py src/atlas_map_data/tests/test_full_build.py
git commit -m "Validate and write the atlas data bundle from the corpus"
```
