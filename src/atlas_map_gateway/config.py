from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    bundle_dir: Path
    upstream_timeout: float = 8.0
    chat_timeout: float = 60.0
    max_series_days: int = 31
    max_waveform_minutes: int = 60
    max_points: int = 2000
    per_host_limit: int = 4


def read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_settings(env: Mapping[str, str] | None = None, dotenv: Path | None = None) -> Settings:
    merged = {**read_dotenv(dotenv or REPO / ".env"), **(os.environ if env is None else env)}
    port = merged.get("GRAPHRAG_API_PORT", "8000")
    return Settings(
        api_url=merged.get("ATLAS_API_URL", f"http://127.0.0.1:{port}"),
        api_key=merged.get("ATLAS_API_KEY", merged.get("GRAPHRAG_API_KEY", "")),
        bundle_dir=Path(merged.get("ATLAS_BUNDLE_DIR", REPO / "src" / "atlas_map" / "public" / "atlas")),
    )
