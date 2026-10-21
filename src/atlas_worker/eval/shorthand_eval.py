"""For each question, find the corpus chunks that answer it (by a spelled-out pattern), then report where the
Graph-RAG search ranks them for the raw question and for the Worker's expanded searchText.

Needs the local Graph-RAG API (127.0.0.1:18000, key from the repository's .env).
Usage: python3 shorthand_eval.py [question substrings...]"""
import glob, json, os, re, subprocess, sys, urllib.request

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[3])   # the repository
KEY = next(l.split("=", 1)[1].strip() for l in open(f"{ROOT}/.env") if l.startswith("GRAPHRAG_API_KEY="))

# question, pattern that a relevant chunk's title or text must match
CASES = [
    ("which paper describes VLFEs offshore cascadia", r"very[- ]low[- ]frequency earthquake"),
    ("what papers discuss SSEs on the cascadia margin", r"slow[- ]slip"),
    ("is there research on ETS in cascadia", r"episodic tremor and slip"),
    ("where are the BPRs deployed for COSZO", r"bottom pressure recorder"),
    ("what does the BOTPT measure at axial", r"bottom pressure (?:and )?tilt"),
    ("what is an APG used for in COSZO", r"absolute pressure gauge"),
    ("which study used GNSS-A in cascadia", r"gnss[- ]?a\b|gnss[- ]acoustic"),
    ("how deep is the AMC at axial seamount", r"axial magma chamber|magma chamber"),
    ("which paper used T-phases recorded on RCA hydrophones", r"\bt[- ]phases?\b"),
    ("what is the Vp/Vs at axial", r"vp\s*/\s*vs"),
    ("what is the b-value of axial seismicity", r"b[- ]value"),
    ("what instruments are at OSB", r"slope base"),
    ("what instruments are at SHR", r"southern hydrate ridge"),
    ("what does ONC operate near the RCA", r"ocean networks canada"),
    ("which study used CI OBS data offshore oregon", r"cascadia initiative"),
    ("what does the ZPLS measure on the shallow profiler", r"bio-?acoustic sonar|zplsc|zpls"),
    ("what does the HPIES measure", r"hpies|horizontal electric field|inverted echo sounder"),
    ("what does the TRHPH measure at ASHES", r"trhph|temperature[^.]{0,40}resistivity"),
    ("what instruments are at the IDF at axial", r"international district"),
    ("what does the DTS measure on the RCA cables", r"distributed temperature sensing|\bdts\b"),
    ("which paper studied MORB at axial", r"mid-ocean ridge basalt|\bmorb\b"),
    ("what is the PN1B node used for", r"primary node"),
    ("which study used OBS data at axial", r"ocean bottom seismometer"),
    ("what does the ADCP measure at slope base", r"acoustic doppler current profiler|\badcp"),
    ("which paper describes the dv/v for cascadia subduction zone", r"seismic velocity|dv/v"),
]


def chunks():
    for f in glob.glob(f"{ROOT}/data/**/chunks.jsonl", recursive=True):
        for l in open(f):
            r = json.loads(l)
            yield r.get("chunk_id"), r.get("title") or "", r.get("text") or ""


def search(q):
    body = json.dumps({"query": q, "limit": 10, "graph_hops": 2, "neighbors_per_seed": 8, "tool_limit": 3}).encode()
    req = urllib.request.Request("http://127.0.0.1:18000/v1/context", body, {"content-type": "application/json", "x-api-key": KEY})
    return json.load(urllib.request.urlopen(req, timeout=60))["hits"]


def expanded(q):
    js = f'import("{ROOT}/src/atlas_worker/src/helpers.js").then(m => console.log(m.searchText({json.dumps(q)})))'
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout.strip()


corpus = list(chunks())
only = sys.argv[1:] or None
for q, pat in CASES:
    if only and not any(o.lower() in q.lower() for o in only):
        continue
    rx = re.compile(pat, re.I)
    gt = {cid for cid, title, text in corpus if rx.search(title) or rx.search(text)}
    if not gt:
        print(f"--  {q}\n      no chunk in the corpus matches /{pat}/")
        continue
    exp = expanded(q)
    rows = []
    for label, query in (("raw", q), ("expanded", exp)):
        hits = search(query)
        ranks = [i for i, h in enumerate(hits) if h["chunk_id"] in gt or rx.search(h.get("title") or "") or rx.search(h.get("text") or "")]
        rows.append((label, ranks, hits))
    ok = bool(rows[1][1]) and rows[1][1][0] <= 2
    print(f"{'OK' if ok else '!!'}  {q}   ({len(gt)} matching chunks in corpus)")
    for label, ranks, hits in rows:
        top = hits[ranks[0]]["title"][:70] if ranks else "-"
        print(f"      {label:8} relevant ranks {ranks[:5]}  first: {top}")
    if exp != q:
        print(f"      expanded query: {exp[len(q):][:110]}")
