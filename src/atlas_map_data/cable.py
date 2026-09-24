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
