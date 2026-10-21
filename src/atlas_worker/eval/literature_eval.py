"""Literature questions with a known answer (a paper title in the corpus): where the Worker's search ranks the
paper, and whether the live chat answer cites it.

Needs the local Graph-RAG API (127.0.0.1:18000, key from the repository's .env) and, with --answers, the deployed
Worker. --answers paces requests 25 s apart to stay under the free models' rate limits.
Usage: python3 literature_eval.py [--answers] [question substrings...]"""
import json, re, subprocess, sys, time, urllib.request

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[3])   # the repository
KEY = next(l.split("=", 1)[1].strip() for l in open(f"{ROOT}/.env") if l.startswith("GRAPHRAG_API_KEY="))
WORKER = "https://rca-atlas.quakehunt.workers.dev/v1/answer"

CASES = [
    ("which paper studied whether tidal triggering of earthquakes at axial predicts eruptions", r"tidal triggering of earthquakes at Axial"),
    ("which study found stacked sills beneath axial seamount", r"Stacked sills"),
    ("what paper describes VLFEs offshore cascadia", r"Widespread Very Low Frequency Earthquakes"),
    ("which paper looked at wind dependent low frequency sound on OOI hydrophones", r"wind-dependent low-frequency ambient sound"),
    ("which paper demonstrated G-FAST EEW for cascadia", r"G-FAST"),
    ("is there a paper on a warm high-flux seep showing fluid overpressure in the CSZ", r"warm, high-flux seafloor seep"),
    ("which paper ran 2-D dynamic rupture simulations of the cascadia megathrust transition region", r"Transition Region Along the Cascadia Megathrust"),
    ("which paper used DAS for seismic ocean thermometry", r"Seismic Ocean Thermometry"),
    ("what paper reviews the seismo-acoustics of submarine eruptions", r"Seismo-acoustics of Submarine Volcanic Eruptions"),
    ("which paper took a long term view of ETS in cascadia", r"Long.Term View of Episodic Tremor"),
    ("which proposal planned compliance instruments to watch the AMC at axial", r"Compliance Instruments for Axial"),
    ("which dataset has APG calibration sheets for the cascadia margin", r"Calibration sheets used with seafloor APG"),
    ("which paper used offshore observations to augment onshore GNSS in cascadia", r"Augmenting Onshore GNSS"),
    ("which paper measured amphibious surface-wave phase velocities in the CSZ", r"Amphibious surface-wave"),
    ("which paper studied methanogen communities in hydrothermal vents", r"methanogen community"),
    ("which paper built a catalog of offshore seismicity in cascadia from CI OBS data", r"Catalog of Offshore Seismicity in Cascadia"),
    ("which paper describes the dv/v for cascadia subduction zone", r"Active Protothrusts"),
    ("which paper used periodic tidal loading at axial to study stress", r"Periodic tidal loading"),
    ("which paper designed an offshore network for EEW and tsunami warning in the pacific northwest", r"Designing an offshore geophysical network"),
    ("which paper integrated microbial and geophysical processes in zero-age crust at axial", r"zero-age, hydrothermally active oceanic crust"),
]


def post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", "user-agent": "curl/8.0 atlas-eval", **headers})
    return json.load(urllib.request.urlopen(req, timeout=150))


def expanded(q):
    js = f'import("{ROOT}/src/atlas_worker/src/helpers.js").then(m => console.log(m.searchText({json.dumps(q)})))'
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout.strip()


answers = "--answers" in sys.argv
only = [a for a in sys.argv[1:] if a != "--answers"]
score = {"retrieved": 0, "answered": 0, "n": 0}
for q, pat in CASES:
    if only and not any(o.lower() in q.lower() for o in only):
        continue
    rx = re.compile(pat, re.I)
    hits = post("http://127.0.0.1:18000/v1/context", {"query": expanded(q), "limit": 10, "graph_hops": 2, "neighbors_per_seed": 8, "tool_limit": 3}, {"x-api-key": KEY})["hits"]
    ranks = [i for i, h in enumerate(hits) if rx.search(h.get("title") or "")]
    score["n"] += 1; score["retrieved"] += bool(ranks)
    line = f"{'ok' if ranks else '!!'} rank {str(ranks[:3]) if ranks else '-':<10} {q}"
    if answers:
        try:
            d = post(WORKER, {"query": q}, {"origin": "https://coszo.org"})
            a = d.get("answer") or d.get("error") or ""
            named = bool(rx.search(a)) or any(rx.search(c.get("title") or "") for c in d.get("answer_citations", [])
                                              if re.search(rf"\[{d['answer_citations'].index(c) + 1}\b|\b{d['answer_citations'].index(c) + 1}\]", a))
            score["answered"] += named
            line += f"\n      answer {'NAMES IT' if named else 'MISSES IT'} [{d.get('answer_model')}]: {a[:160].replace(chr(10), ' ')}"
        except Exception as e:
            line += f"\n      answer ERROR {e}"
        time.sleep(25)   # stay under the free models' per-minute limits
    print(line, flush=True)
print(f"\nretrieved {score['retrieved']}/{score['n']}" + (f", answer names the paper {score['answered']}/{score['n']}" if answers else ""))
