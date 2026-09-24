"""What the atlas knows. The gateway only serves these ids, so it can't be used as an open proxy."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BundleIndex:
    refdes: set[str] = field(default_factory=set)
    erddap: dict[str, str] = field(default_factory=dict)
    stations: dict[str, dict] = field(default_factory=dict)
    pi_keys: set[str] = field(default_factory=set)

    @classmethod
    def from_dir(cls, path: Path) -> "BundleIndex":
        ix = cls()
        for s in json.loads((path / "sensors.json").read_text())["sensors"]:
            if s.get("refdes"):
                ix.refdes.add(s["refdes"])
            for a in s.get("access", []):
                if a["kind"] == "erddap":
                    ix.erddap[s["refdes"]] = a["datasetId"]
                elif a["kind"] == "earthscope":
                    ix.stations[f"{a['network']}.{a['station']}"] = {"channel": a.get("channel")}
                elif a["kind"] == "pi_portal":
                    ix.pi_keys.add(a["instrumentKey"])
        return ix

    def has_refdes(self, refdes: str) -> bool:
        return refdes in self.refdes

    def erddap_dataset(self, refdes: str) -> str | None:
        return self.erddap.get(refdes)

    def station(self, net: str, sta: str) -> dict | None:
        return self.stations.get(f"{net}.{sta}")

    def has_pi(self, key: str) -> bool:
        return key in self.pi_keys
