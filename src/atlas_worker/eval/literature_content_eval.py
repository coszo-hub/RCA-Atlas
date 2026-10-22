"""Literature content questions with known answers, from the supplied papers' abstracts: ask the deployed Worker and
check that each answer carries the paper's key facts. Q1-Q10 test papers on Axial and the Cascadia margin, S1-S13
spread across sensors and datasets (hydrophones, DAS, echosounders, oxygen, moorings, seismometers, vent samplers),
F1-F2 ask facts beyond the abstracts. Facts marked "extra" are in the paper but not asked for: they are reported, not scored. A miss on an asked fact is a
fact left out or a wrong value; read the answers in the JSON to tell.
Paces requests 25 s apart to stay under the free models' rate limits.
Usage: python3 literature_content_eval.py [case ids...]"""
import json, re, sys, time, urllib.request
from pathlib import Path

# Answers must not copy papers: any 12-word run shared with a paper chunk (abstract or full text) is counted.
CORPUS = Path(__file__).resolve().parents[3] / "runtime_data/GraphRAG/normalized/chunks.jsonl"
words = lambda t: re.sub(r"[^a-z0-9 ]", " ", t.lower().replace("\u2011", "-")).split()
PAPER_RUNS = set()
if CORPUS.exists():
    for line in CORPUS.open():
        c = json.loads(line)
        if c["collection_id"] in ("literature", "literature_fulltext") or "doi.org" in (c.get("source_url") or ""):
            w = words(c["body"])
            PAPER_RUNS.update(" ".join(w[i:i + 12]) for i in range(len(w) - 11))
WORKER = "https://rca-atlas.quakehunt.workers.dev/v1/answer"
CASES = [  # (id, paper, question, [(fact label, regex)], answerable from the abstract)
 ("Q1", "COSZO-REF-084", "What linear drift rates were measured for the two quartz pressure gauges on the drift-corrected (self-calibrating) pressure recorder at Axial Seamount, and how big were the residuals?",
  [("0.45 kPa/yr", r"0\.45"), ("0.36 kPa/yr", r"0\.36"), ("~6 mm / 0.06 kPa", r"\b6 ?mm|0\.06 ?kPa")], True),
 ("Q2", "COSZO-REF-027", "How long did the January 1998 earthquake swarm at Axial Volcano last, and how many earthquakes were detected?",
  [("11 days", r"\b11\b|eleven"), ("8247 detected", r"8,?247"), ("1037 located", r"1,?037", "extra")], True),
 ("Q3", "COSZO-REF-011", "How far apart are the stacked melt lenses imaged beneath Axial Seamount, and how wide is the conduit?",
  [("300-450 m", r"300\s*(?:–|-|to)\s*450"), ("3-5 km wide", r"3\s*(?:–|-|to)\s*5\s*km")], True),
 ("Q4", "COSZO-REF-143", "What is Pythia's Oasis, how warm is its fluid, and which fault is thought to drain the overpressured reservoir?",
  [("~9 °C above background", r"\b9\s*°?\s*C|9 degrees"), ("Alvin Canyon fault", r"Alvin Canyon"), ("10-30 cm/s flow", r"10\s*(?:–|-|to)\s*30\s*cm", "extra")], True),
 ("Q5", "COSZO-REF-038", "What slip rates and lengths were found for the WNW-trending left-lateral strike-slip faults on the Oregon-Washington margin?",
  [("5.5-8.5 mm/yr", r"5\.5.{0,25}8\.5"), ("33-115 km", r"33\s*(?:–|-|to)\s*115"), ("at least nine", r"\bnine\b|\b9\b", "extra")], True),
 ("Q6", "COSZO-REF-019", "How accurate are the absolute self-calibrating pressure recorder (ASCPR) campaign measurements off Newport, Oregon, and where were they made?",
  [("~25 ppm of depth", r"25\s*ppm"), ("seven benchmarks", r"\bseven\b|\b7\b"), ("100 km line from Newport", r"100\s*km")], True),
 ("Q7", "COSZO-REF-145", "How high did methane bubble plumes rise above Southern Hydrate Ridge, and how did that compare with the hydrate stability zone?",
  [("320-620 m below sea level", r"320\s*(?:–|-|to)\s*620"), ("~190 m above stability limit", r"190")], True),
 ("Q8", "COSZO-REF-078", "What is the typical in situ long-term drift and resolution of Paroscientific seafloor pressure sensors?",
  [("-0.88 kPa/a drift", r"0\.88"), ("20.7 Pa noise", r"20\.7"), ("118 time series", r"\b118\b", "extra")], True),
 ("Q9", "COSZO-REF-030", "What did five years of bottom pressure recorder measurements in Axial's caldera show about subsidence events?",
  [("five events", r"\bfive\b|\b5\b"), ("3-10 cm", r"3\s*(?:–|-|to)\s*10\s*cm"), ("10-14 days", r"10\s*(?:–|-|to)\s*14\s*days")], True),
 ("Q10", "COSZO-REF-091", "How many earthquakes are in the Cascadia Initiative offshore seismicity catalog, and where is offshore seismicity sparse?",
  [("271 earthquakes", r"\b271\b"), ("M 0.4-4.0", r"0\.4", "extra"), ("sparse off Vancouver Is./Washington", r"Vancouver|Washington")], True),
 ("F1", "COSZO-REF-129", "At what acoustic frequencies does the COVIS sonar at the ASHES vent field operate?",
  [("400 kHz", r"400\s*kHz"), ("200 kHz", r"200\s*kHz")], False),
 ("F2", "COSZO-REF-084", "Which RCA junction box was the drift-corrected (self-calibrating) pressure recorder at Axial connected to?",
  [("MJ03F", r"MJ03F")], False),
 ("S1", "OOI-ZOT-103", "How many low-frequency and broadband hydrophones does the OOI network have, and at what sample rates do they record?",
  [("5 low-frequency", r"\b(five|5)\b[^.]{0,40}low"), ("6 broadband", r"\b(six|6)\b[^.]{0,40}broadband"), ("200 Hz", r"200\s*Hz"), ("64 kHz", r"64\s*kHz")], True),
 ("S2", "OOI-ZOT-089", "On the OOI broadband hydrophones on the Oregon margin, at what frequency does underwater rain noise correlate best with rain rate, and at what depths were the hydrophones?",
  [("13 kHz", r"13\s*kHz"), ("81 m", r"\b81\s*m"), ("581 m", r"\b581\s*m")], True),
 ("S3", "OOI-ZOT-119", "Which whale calls and other sounds were recorded in the November 2021 DAS experiment on the RCA cables offshore central Oregon?",
  [("20 Hz fin whale", r"fin whale"), ("blue whale A and B", r"blue whale"), ("ship noise", r"ship"), ("4 days", r"\b(four|4)[- ]days?", "extra")], True),
 ("S4", "OOI-ZOT-023", "In the 4-day OOI ocean-bottom DAS experiment, how many oceanic earthquakes were detected, and how small a repeating earthquake could be used for seismic ocean thermometry?",
  [("92 earthquakes", r"\b92\b"), ("M3.5", r"M\s*3\.5|magnitude 3\.5")], True),
 ("S5", "OOI-ZOT-081", "What method was developed to summarize long-term echosounder time series into a few daily echogram patterns?",
  [("principal component pursuit", r"principal component pursuit"), ("non-negative matrix factorization", r"non-?negative matrix factori[sz]ation")], True),
 ("S6", "OOI-ZOT-129", "How extensive was near-bottom hypoxia on the Pacific Northwest shelf in summer 2021, and how has the hypoxic fraction changed since 1950?",
  [("15,500 km2", r"15,?500"), ("2% in 1950-1980", r"\b2\s*%"), ("24% in 2009-2018", r"24\s*%"), ("56% in 2021", r"56\s*%")], True),
 ("S7", "OOI-ZOT-126", "Which mooring site and water depth were used to study subsurface marine heatwaves off central Oregon in 2014-2021, and when was the largest bottom temperature anomaly?",
  [("NH-10", r"NH-?10"), ("80 m", r"\b80\s*m"), ("late 2016", r"2016")], True),
 ("S8", "OOI-ZOT-034", "How much power and efficiency did the inductive charging system for McLane moored profilers achieve, and where was it tested?",
  [("~225 W", r"225\s*W"), ("~70%", r"70\s*%"), ("Puget Sound", r"Puget Sound"), ("Station ALOHA", r"ALOHA")], True),
 ("S9", "OOI-ZOT-080", "What earthquake stress drops were found on Axial Seamount's caldera ring faults before and after the 2015 eruption?",
  [("6.4 MPa inflation", r"6\.4"), ("3.2 MPa deflation", r"3\.2"), ("0.6-43 MPa", r"0\.6.{0,15}43", "extra"), ("423 earthquakes", r"\b423\b", "extra")], True),
 ("S10", "COSZO-REF-119", "According to the cabled seismic network, what structure accommodated inflation at Axial Seamount before the 2015 eruption, and when did the eruption begin?",
  [("outward-dipping ring fault", r"outward[- ]dipping"), ("tidal triggering", r"tidal", "extra"), ("24 April 2015", r"24 April|April 24")], True),
 ("S11", "OOI-ZOT-041", "What explosive signals did seafloor hydrophones record during the 2015 Axial Seamount eruption?",
  [("lava-water explosions", r"lava.{0,5}water|impulsive"), ("submarine Hawaiian explosions", r"Hawaiian"), ("waning phase / diffuse events", r"diffuse|waning")], True),
 ("S12", "OOI-ZOT-093", "How many vent fluid samples did the remotely triggered sampler collect at Main Endeavour Field, and what event was seen near the end of the deployment?",
  [("nine samples", r"\bnine\b|\b9\b"), ("~20 °C drop", r"20\s*°?\s*C"), ("Fe decrease 24-77%", r"24.{0,6}77")], True),
 ("S13", "OOI-ZOT-049", "What frequency range and signal duration characterize methane bubble sounds recorded near Heceta Bank on the Oregon margin?",
  [("1-45 kHz", r"1(\.0)?\s*(?:–|-|to)\s*45\s*kHz"), ("10-20 ms", r"10\s*(?:–|-|to)\s*20\s*ms"), ("1228 m depth", r"1,?228", "extra")], True),
]


def post(body):
    req = urllib.request.Request(WORKER, json.dumps(body).encode(), {"content-type": "application/json", "origin": "https://coszo.org", "user-agent": "curl/8.0 atlas-eval"})
    return json.load(urllib.request.urlopen(req, timeout=180))


only = sys.argv[1:]
out = []
for cid, paper, q, facts, abstract in CASES:
    if only and cid not in only:
        continue
    try:
        d = post({"query": q})
    except Exception as e:
        d = {"error": str(e)}
    a = d.get("answer") or d.get("error") or ""
    plain = a.translate({0x2010: "-", 0x2011: "-", 0x2012: "-", 0x00a0: " ", 0x202f: " ", 0x2009: " "})
    got = [(label, bool(re.search(rx, plain, re.I)), bool(extra)) for label, rx, *extra in facts]
    cites = [c.get("title", "")[:90] for c in d.get("answer_citations", [])]
    asked = [g for _, g, x in got if not x]
    w = words(a)
    copied = sum(" ".join(w[i:i + 12]) in PAPER_RUNS for i in range(len(w) - 11))
    out.append({"id": cid, "paper": paper, "question": q, "abstract": abstract, "facts": got, "model": d.get("answer_model"), "answer": a, "citations": cites, "copied_runs": copied})
    print(f"{cid} {sum(asked)}/{len(asked)} copied {copied} [{d.get('answer_model')}] {', '.join(l + ('✓' if g else '✗') + (' (extra)' if x else '') for l, g, x in got)}", flush=True)
    time.sleep(25)
json.dump(out, open("literature_content_results.json", "w"), indent=1, ensure_ascii=False)
asked = [g for r in out for _, g, x in r["facts"] if not x]
extra = [g for r in out for _, g, x in r["facts"] if x]
print(f"\nasked facts found {sum(asked)}/{len(asked)}; extra details included {sum(extra)}/{len(extra)}; results in literature_content_results.json")
