#!/usr/bin/env python3
"""Runs every download recipe in a sandbox on this machine: the recipe's own code, with its example timeframe set to a
short window inside the dataset's coverage (a day of ERDDAP rows, the newest hour of a Gold Copy stream, ten minutes of
raw files, a minute of waveforms, the newest portal file), each in a fresh container of sandbox.Dockerfile's image
(Python and only requirements-recipes.txt; an unprivileged user, no capabilities, memory, CPU and process limits, and
no host folder at all: the code goes in on stdin and the work folder is a tmpfs capped at 1.5 GB), under a time limit.
A route whose files are over 1 GB (the HD camera's videos) is not run, and is left without a tested note. A recipe passes when the code exits cleanly
and writes a data file that is not empty. Results go to runtime_data/DataRecipes/test_results.json, which the next
build reads: a failing route is left out of its recipe, and a passing one says when it was tested.

M2M recipes (an instrument with no public route) need an OOI account; they run only with --m2m N (at most N of them),
using OOI_API_USERNAME and OOI_API_TOKEN from the project's .env, which reach only that container.

Usage: python3 test_recipes.py [--jobs 4] [--only SUBSTRING] [--m2m N]   (then rebuild: build_data_recipes.py)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SANDBOX = ROOT / "runtime_data/DataRecipes/sandbox"
TESTS = ROOT / "runtime_data/DataRecipes/tests.json"
RESULTS = ROOT / "runtime_data/DataRecipes/test_results.json"
TIMEOUT_S = 900
WORK_CAP = "1500m"       # the container's work folder is a tmpfs of this size: a test cannot fill the host's disk
MAX_FILE_BYTES = 1e9     # a route whose files are larger (the HD camera's 14 GB videos) is not run


IMAGE = "rca-atlas-recipes:" + __import__("hashlib").sha256(
    (HERE / "sandbox.Dockerfile").read_bytes() + (HERE / "requirements-recipes.txt").read_bytes()).hexdigest()[:12]
DOCKER_ENV = {**os.environ, "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR") or str(Path.home() / ".docker/run")}


def image() -> str:
    """The sandbox image, built when its Dockerfile or requirements change."""
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, env=DOCKER_ENV).returncode:
        subprocess.run(["docker", "build", "-q", "-t", IMAGE, "-f", str(HERE / "sandbox.Dockerfile"), str(HERE)],
                       check=True, env=DOCKER_ENV)
    return IMAGE


def ooi_account() -> bool:
    """OOI_API_USERNAME and OOI_API_TOKEN from .env into this process's environment (never printed)."""
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        key, _, value = line.partition("=")
        if key in ("OOI_API_USERNAME", "OOI_API_TOKEN") and value:
            os.environ.setdefault(key, value.strip().strip('"'))
    return bool(os.environ.get("OOI_API_USERNAME") and os.environ.get("OOI_API_TOKEN"))


def windowed(test: dict) -> str | None:
    """The recipe's code with the test's timeframe in place of its example one."""
    code, kind = test["code"], test["kind"]
    if kind in ("erddap", "gold"):
        code, n = re.subn(r'^START, END = .*$', f'START, END = "{test["start"]}", "{test["end"]}"', code, count=1, flags=re.M)
    elif kind == "raw":
        a, b = (datetime.fromisoformat(test[k]) for k in ("start", "end"))
        args = lambda t: f"{t.year}, {t.month}, {t.day}, {t.hour}, {t.minute}, {t.second}"
        code, n = re.subn(r"^START, END = .*$", f"START, END = datetime({args(a)}), datetime({args(b)})", code, count=1, flags=re.M)
    elif kind == "earthscope":
        code, n = re.subn(r'^t1, t2 = .*$', f't1, t2 = UTCDateTime("{test["start"]}"), UTCDateTime("{test["end"]}")', code,
                          count=1, flags=re.M)
    elif kind == "portal":
        code, n = re.subn(r"^for name in names:", "for name in names[-1:]:", code, count=1, flags=re.M)
    else:
        n = 1
    return code if n else None


def parse_size(text: str | None) -> float:
    """Bytes in a listing's size (832K, 19M, 14G)."""
    m = re.fullmatch(r"([\d.]+)([KMGT]?)", text or "")
    return float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)] if m else 0


def size(n: int) -> str:
    return (f"{n / 1e9:.0f} GB" if n >= 1e9 else f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} kB" if n >= 1e3
            else f"{n:.0f} bytes")


def run(test: dict, img: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = {"date": today, "kind": test["kind"], "passed": False}
    code = windowed(test) if test.get("code") else None
    if not code:
        return {**result, "error": "no code, or its timeframe line was not found"}
    largest = max((parse_size(x) for x in test.get("file_sizes", [])), default=0)
    if largest > MAX_FILE_BYTES:
        return {**result, "passed": True, "skipped": f"its files are up to {size(largest)}",
                "wrote": f"nothing (not run: its files are up to {size(largest)})"}
    name = "recipe-" + re.sub(r"[^a-z0-9]+", "-", test["id"].lower())[:60] + "-" + os.urandom(3).hex()
    account = ["-e", "OOI_API_USERNAME", "-e", "OOI_API_TOKEN"] if test["kind"] == "m2m" else []
    # The code goes in on stdin; the work folder is a capped tmpfs; the files written are listed after a marker.
    inside = (f"cat > recipe.py && timeout {TIMEOUT_S} python recipe.py; rc=$?; echo @@FILES@@; "
              "find . -maxdepth 1 -type f ! -name recipe.py -size +0 -printf '%s %f\\n'; exit $rc")
    cmd = ["docker", "run", "--rm", "-i", "--name", name, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "4g", "--cpus", "2", "--pids-limit", "256", "--tmpfs", "/tmp:size=256m",
           "--mount", f"type=tmpfs,destination=/work,tmpfs-size={WORK_CAP},tmpfs-mode=1777",
           *account, img, "sh", "-c", inside]
    try:
        p = subprocess.run(cmd, input=code, capture_output=True, text=True, timeout=TIMEOUT_S + 60, env=DOCKER_ENV)
        listed = p.stdout.rpartition("@@FILES@@")[2].split("\n")
        files = [(int(n), f) for n, _, f in (line.partition(" ") for line in listed if line.strip()) if n.isdigit()]
        if p.returncode == 0 and files:
            biggest = max(files)
            ext = biggest[1].rsplit(".", 1)[-1] if "." in biggest[1] else "a"
            extra = f" and {len(files) - 1} more file{'s' if len(files) > 2 else ''}" if len(files) > 1 else ""
            return {**result, "passed": True, "wrote": f"{ext} file of {size(biggest[0])}{extra}"}
        return {**result, "error": (p.stderr.strip().splitlines() or ["exited cleanly but wrote no data file"])[-1][:300],
                "returncode": p.returncode}
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, env=DOCKER_ENV)
        return {**result, "error": f"timed out after {TIMEOUT_S} s"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only", help="run only the tests whose id contains this")
    parser.add_argument("--m2m", type=int, default=0, help="run at most this many M2M recipes (needs the OOI account in .env)")
    args = parser.parse_args()
    tests = [t for t in json.loads(TESTS.read_text()) if not args.only or args.only in t["id"]]
    m2m = [t for t in tests if t["kind"] == "m2m"]
    tests = [t for t in tests if t["kind"] != "m2m"] + (m2m[:args.m2m] if args.m2m and ooi_account() else [])
    SANDBOX.mkdir(parents=True, exist_ok=True)
    img = image()
    previous = json.loads(RESULTS.read_text())["results"] if RESULTS.exists() else {}
    results = dict(previous)
    with ThreadPoolExecutor(args.jobs) as pool:
        for test, result in zip(tests, pool.map(lambda t: run(t, img), tests)):
            results[test["id"]] = result
            print(("PASS " if result["passed"] else "FAIL ") + test["id"] + "  " + (result.get("wrote") or result.get("error", "")), flush=True)
    RESULTS.write_text(json.dumps({"tested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                   "image": img,
                                   "results": results}, indent=1))
    ran = [results[t["id"]] for t in tests]
    print(f"\n{sum(r['passed'] and not r.get('skipped') for r in ran)} passed, {sum(bool(r.get('skipped')) for r in ran)} not run "
          f"(file too large), {sum(not r['passed'] for r in ran)} failed, of {len(ran)}; results in {RESULTS}")


if __name__ == "__main__":
    main()
