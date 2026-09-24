"""Maleen's toolkits, imported from their folders without modification."""
from __future__ import annotations

import importlib
import os
import sys

from .config import REPO, Settings


def _load(folder: str, module: str):
    path = str(REPO / "src" / folder)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(module)


def make(settings: Settings) -> dict:
    t = int(settings.upstream_timeout)
    os.environ.setdefault("PI_PORTAL_TIMEOUT_SECONDS", str(t))
    os.environ.setdefault("EARTHSCOPE_TIMEOUT_SECONDS", str(t))
    return {
        "nereus": _load("nereus_pipeline", "nereus_agent_tools").NereusToolkit(timeout=t),
        "qaqc": _load("agentic_qaqc", "qaqc_agent_tools").QAQCToolkit(timeout=t),
        "pi": _load("coszo_hub_tools", "pi_portal_agent_tools").PIPortalToolkit(),
        "earthscope": _load("coszo_hub_tools", "earthscope_fdsn_agent_tools").EarthScopeFDSNToolkit(),
    }
