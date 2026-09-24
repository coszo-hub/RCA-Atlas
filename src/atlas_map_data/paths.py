from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
RUNTIME = REPO / "runtime_data" / "AtlasMap"
BUNDLE = REPO / "src" / "atlas_map" / "public" / "atlas"
PACKAGE = Path(__file__).resolve().parent
