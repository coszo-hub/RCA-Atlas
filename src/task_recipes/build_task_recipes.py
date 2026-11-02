#!/usr/bin/env python3
"""Builds the task recipes: for each task in tasks.json (plot an earthquake's waveform, a hydrophone's spectrogram ...),
its steps, a Python script that has been run, what to change in it, its pitfalls, the instruments it works for and its
sources. Ask Atlas uses them to write code for a task a question asks for, from the tested script and the asked
instrument's download recipe (data/DataRecipes).

  --test  runs each task's script in the download recipes' sandbox (data_recipes/test_recipes.py: a fresh container
          with no host folder and a capped work folder) into runtime_data/TaskRecipes/test_results.json; a task passes
          when its script exits cleanly having written a file that is not empty.
  (always) writes data/TaskRecipes (one chunk per task that passed) and src/atlas_worker/src/task_recipes.json (each
          task's chunk and the words that ask for it).

Usage: python3 build_task_recipes.py [--test] [--only TASK_ID]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = HERE / "tasks.json"
BUNDLE = ROOT / "src/atlas_map/public/atlas/sensors.json"
RECIPE_SOURCES = ROOT / "runtime_data/DataRecipes/sources.json"   # build_data_recipes.py --refresh
RESULTS = ROOT / "runtime_data/TaskRecipes/test_results.json"
OUT = ROOT / "data/TaskRecipes"
WORKER = ROOT / "src/atlas_worker/src/task_recipes.json"

sys.path.insert(0, str(ROOT / "src/data_recipes"))
import test_recipes  # noqa: E402  the sandbox


def seismometers() -> str:
    """Each OO seismic station with its seismometer's channels now (instrument code H), from EarthScope."""
    names = {s["id"]: s["name"] for s in json.loads(BUNDLE.read_text())["sensors"]}
    lines = []
    for station, info in json.loads(RECIPE_SOURCES.read_text())["earthscope"].items():
        net, sta = station.split(".")
        now = [c for c in info["channels"] if not c["end"] and re.fullmatch(r"[HEBS]H[ZNE12]", c["channel"])]
        if not now:
            continue
        bands = sorted({(c["channel"][:2] + "?", float(c["rate"])) for c in now}, key=lambda b: -b[1])
        sensor = now[0]["sensor"].split(",")[:2]
        kind = "broadband" if "360 s" in sensor[-1] else "short-period" if "1s" in sensor[-1] else ""
        name = re.sub(rf"\s*{sta}$", "", names.get(f"EARTHSCOPE-{net}-{sta}", station))
        lines.append(f"{sta} ({name}): {', '.join(f'{b} {r:g} Hz' for b, r in bands)}; {kind} {sensor[0].strip()}".rstrip())
    return "Stations it works for (network OO, channels now): " + "; ".join(lines) + "."


def hydrophones() -> str:
    """The broadband hydrophones (OOIPy's nodes) and the low-frequency ones (their seismic stations), from the map."""
    sensors = json.loads(BUNDLE.read_text())["sensors"]
    broadband = sorted({(s["refdes"].split("-")[1], s["name"]) for s in sensors
                        if re.fullmatch(r"(?:RS|CE)\w{6}-\w{5}-\w{2}-HYDBB\w+", s.get("refdes") or "")})
    low = sorted({(s["refdes"], s["name"]) for s in sensors if re.fullmatch(r"RS\w{6}-\w{5}-\w{2}-HYDLF\w+", s.get("refdes") or "")})
    sources = json.loads(RECIPE_SOURCES.read_text())["earthscope"]
    stations = {s: [c["channel"] for c in info["channels"] if c["channel"] == "HDH" and not c["end"]] for s, info in sources.items()}
    lf = [f"{st.split('.')[1]} ({name})" for refdes, name in low for st, chans in stations.items() if chans
          and any(a.get("station") == st.split(".")[1] for s in sensors if s.get("refdes") == refdes for a in s.get("access", []))]
    return ("Hydrophones it works for: broadband (64 kHz, HYDROPHONE = its node) " + "; ".join(f"{n} ({name})" for n, name in broadband)
            + "; low-frequency (200 Hz, HYDROPHONE = its seismic station) " + "; ".join(lf) + ".")


INSTRUMENTS = {"seismometers": seismometers, "hydrophones": hydrophones}


def chunk(task: dict, result: dict) -> dict:
    code = (HERE / task["script"]).read_text().rstrip()
    steps = " ".join(f"{i}. {s}" for i, s in enumerate(task["steps"], 1))
    pitfalls = " ".join(f"- {p}" for p in task["pitfalls"])
    # One citation each in the Worker (withRouteCitations), which reads "title (url); ...": no ( ) or ; in a title.
    assert not any(re.search(r"[();]", s["title"]) for s in task["sources"]), task["id"]
    sources = "; ".join(f"{s['title']} ({s['url']})" for s in task["sources"])
    text = (f"How to {task['title'][0].lower()}{task['title'][1:]} (task recipe). {task['summary']}\n"
            f"Steps: {steps}\n"
            f"```python\n{code}\n```\n"
            f"Tested {result['date']}: the script ran in a clean Python environment and wrote a {result['wrote']}.\n"
            f"To change: {task['change']}\n"
            f"Pitfalls: {pitfalls}\n"
            + (f"{INSTRUMENTS[task['instruments']]()}\n" if task.get("instruments") else "")
            + f"Sources: {sources}.")
    return {"chunk_id": f"task_{task['id']}", "title": f"Task recipe: {task['title']}", "text": text,
            "entity_ids": [f"TASK-{task['id']}"], "source_ids": [f"TASK-SOURCE-{task['id']}"],
            "source_urls": [task["sources"][0]["url"]]}


def test(tasks: list[dict]) -> None:
    img = test_recipes.image()
    results = json.loads(RESULTS.read_text())["results"] if RESULTS.exists() else {}
    for task in tasks:
        result = test_recipes.run({"id": f"task-{task['id']}", "kind": "task", "code": (HERE / task["script"]).read_text()}, img)
        results[task["id"]] = result
        print(("PASS " if result["passed"] else "FAIL ") + task["id"] + "  " + (result.get("wrote") or result.get("error", "")), flush=True)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps({"tested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "image": img,
                                   "results": results}, indent=1))


def build(tasks: list[dict]) -> None:
    results = json.loads(RESULTS.read_text())["results"] if RESULTS.exists() else {}
    passed = [t for t in tasks if results.get(t["id"], {}).get("passed")]
    for t in tasks:
        if t not in passed:
            print(f"left out (its script has not passed in the sandbox): {t['id']}")
    chunks = [chunk(t, results[t["id"]]) for t in passed]
    entities = [{"entity_id": f"TASK-{t['id']}", "entity_type": "task_recipe", "name": t["title"],
                 "attributes": {"script": t["script"], "instruments": t.get("instruments")}} for t in passed]
    # A task recipe is cited as itself, linking to its first source; each source is a graph neighbour.
    sources = {f"TASK-SOURCE-{t['id']}": {"source_id": f"TASK-SOURCE-{t['id']}", "title": f"Task recipe: {t['title']}",
                                          "source_url": t["sources"][0]["url"], "kind": "task_recipe"} for t in passed}
    refs = {}
    for t in passed:
        for s in t["sources"]:
            refs.setdefault(s["url"], {"source_id": "TASK-REF-" + re.sub(r"[^A-Za-z0-9]+", "-", s["url"].split("//", 1)[-1]).strip("-"),
                                       "title": s["title"], "source_url": s["url"], "kind": "reference"})
    sources.update({r["source_id"]: r for r in refs.values()})
    relationships = [{"relationship_id": f"TASK-{t['id']}-CITES-{refs[s['url']]['source_id']}", "source_id": f"TASK-{t['id']}",
                      "target_id": refs[s["url"]]["source_id"], "relationship_type": "CITES"} for t in passed for s in t["sources"]]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("chunks", chunks), ("entities", entities), ("relationships", relationships),
                       ("source_documents", list(sources.values()))):
        (OUT / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (OUT / "manifest.json").write_text(json.dumps({
        "corpus": "RCA Atlas task recipes", "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task_count": len(passed), "chunk_count": len(chunks), "entity_count": len(entities),
        "relationship_count": len(relationships), "source_document_count": len(sources)}, indent=2))
    WORKER.write_text(json.dumps([{"chunk_id": f"task_{t['id']}", "instruments": t.get("instruments"), **t["match"]}
                                  for t in passed], indent=1) + "\n")
    print(f"{len(passed)} task recipes of {len(tasks)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--test", action="store_true", help="run the scripts in the sandbox first")
    parser.add_argument("--only", help="test only this task")
    args = parser.parse_args()
    tasks = json.loads(TASKS.read_text())
    if args.test:
        test([t for t in tasks if not args.only or t["id"] == args.only])
    build(tasks)
