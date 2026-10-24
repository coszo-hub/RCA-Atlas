"""Instrument metadata questions: serial numbers, makes and models, deployments, recoveries, swaps, node boxes,
calibrations, depths, papers' serial numbers and seismometer orientation. Each expected fact is computed from the
source files themselves when the eval runs (OOI asset-management, the curated source serials, the stations'
StationXML), so the eval follows the data when it is rebuilt. Asks the deployed Worker and checks each answer for
the facts. Facts marked "extra" are reported, not scored.
Usage: python3 asset_eval.py [--model gpt-5.4-mini] [--out results.json] [case ids...]"""
import json, re, sys, time, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/ooi_asset_management"))
from build_asset_metadata import REPO, Repository, calibration_for   # noqa: E402

WORKER = "https://rca-atlas.quakehunt.workers.dev/v1/answer"
SERIAL = "Manufacturer's Serial No./Other Identifier"

repo = Repository(REPO)
ASSETS, VOCAB, CALS = repo.assets(), repo.vocab(), repo.calibrations()
_by = defaultdict(dict)
for row in repo.deployments():
    cur = _by[row["Reference Designator"]].get(row["deploymentNumber"])
    if cur is None or int(row.get("versionNumber") or 0) >= int(cur.get("versionNumber") or 0):
        _by[row["Reference Designator"]][row["deploymentNumber"]] = row   # the latest version of each deployment
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def deps(refdes):
    return sorted(_by[refdes].values(), key=lambda d: int(d["deploymentNumber"]))


def serials(refdes):
    """Each sensor serial the instrument has had, in order of first use."""
    out = []
    for d in deps(refdes):
        s = ASSETS.get(d.get("sensor.uid", ""), {}).get(SERIAL)
        if s and s not in out:
            out.append(s)
    return out


def node_serials(node):
    out = []
    for refdes in sorted(_by):
        if refdes.startswith(node + "-"):
            for d in deps(refdes):
                s = ASSETS.get(d.get("node.uid", ""), {}).get(SERIAL)
                if s and s not in out:
                    out.append(s)
    return out


def depth_of(d):
    try:
        return float(d.get("deployment_depth") or "")
    except ValueError:
        return None


def ended(d):
    return bool(d.get("stopDateTime")) and d["stopDateTime"] <= NOW


MONTHS = "January February March April May June July August September October November December".split()


def on(day):
    """A date as an answer may write it: 2021-08-28, August 28, 2021, 28 August 2021, Aug 28 2021."""
    y, m, dd = int(day[:4]), int(day[5:7]), int(day[8:10])
    mon = MONTHS[m - 1]
    return (rf"{day[:10]}|{mon[:3]}\w*\.?\s+{dd},?\s+{y}|\b{dd}\s+{mon[:3]}\w*\.?,?\s+{y}")


def lit(text):
    return re.escape(text)


def serial_rx(s):
    """A serial as written, allowing the answer to drop or keep separators and leading zeros after letters."""
    core = re.escape(s).replace(r"\-", r"[-‐‑ ]?")
    return core


def station_azimuths():
    """Station -> {north channel: azimuth} for its current epoch, from the StationXML the corpus was built from."""
    ns = {"s": "http://www.fdsn.org/xml/station/1"}
    out = {}
    for path in sorted((ROOT / "source_material/stationxml").rglob("OO_*.xml")):
        for st in ET.parse(path).getroot().iterfind(".//s:Station", ns):
            code = st.get("code")
            for ch in st.iterfind("s:Channel", ns):
                end = ch.get("endDate") or ""
                if end and end[:19] <= NOW:
                    continue
                if ch.get("code", "")[-1] in "N1" and ch.get("code", "")[1] in "HLN":
                    az = ch.findtext("s:Azimuth", namespaces=ns)
                    if az is not None:
                        out.setdefault(code, {})[ch.get("code")] = round(float(az))
    return out


AZ = station_azimuths()
SOURCED = {e["id"]: e for e in json.loads((ROOT / "src/ooi_asset_management/source_serials.json").read_text())["entries"]}


def make(refdes):
    v = VOCAB.get(refdes, {})
    return v.get("Manufacturer", ""), v.get("Model", "")


# Each case: id, question, a function giving [(label, regex, *"extra")], and an optional regex a citation must match.
def c_a1():
    s = serials("RS01SLBS-MJ01A-05-OBSBBA102")
    return [(f"serial {x}", serial_rx(x)) for x in s]


def c_a2():
    m, model = make("RS03AXBS-MJ03A-05-OBSBBA303")
    return [(m, lit(m.split()[0])), (model, lit(model.split("/")[0])), ("serial " + serials("RS03AXBS-MJ03A-05-OBSBBA303")[0], serial_rx(serials("RS03AXBS-MJ03A-05-OBSBBA303")[0]), "extra")]


def c_a3():
    return [("first deployed " + deps("RS03CCAL-MJ03F-12-CTDPFB305")[0]["startDateTime"][:10], on(deps("RS03CCAL-MJ03F-12-CTDPFB305")[0]["startDateTime"]))]


def c_a4():
    d = deps("RS03CCAL-MJ03F-05-BOTPTA301")
    assert len(d) == 1 and not ended(d[0])
    return [("never recovered / still deployed", r"never (?:been )?recovered|not (?:been )?recovered|no recover|still (?:deployed|in place|in the water)|deployed (?:now|since|continuously)|remain"),
            ("since " + d[0]["startDateTime"][:10], on(d[0]["startDateTime"]))]


def c_a5():
    return [(f"serial {x}", serial_rx(x)) for x in serials("RS03AXBS-LJ03A-12-CTDPFB301")]


def c_a6():
    n = len(deps("CE02SHBP-LJ01D-06-CTDBPN106"))
    words = {11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"}
    return [(f"{n} deployments", rf"\b{n}\b|\b{words.get(n, n)}\b")]


def c_a7():
    m, model = make("RS01SUM1-LJ01B-12-VEL3DB104")
    return [(f"{m} {model}", lit(model))] + [(f"serial {x}", serial_rx(x)) for x in serials("RS01SUM1-LJ01B-12-VEL3DB104")]


def c_a8():
    m, model = make("RS03AXPD-DP03A-02-VEL3DA303")
    return [(m, lit(m.split()[0])), (model, lit(model))]


def c_a9():
    return [(f"serial {x}", rf"\b{serial_rx(x)}\b") for x in serials("RS03AXPD-DP03A-02-VEL3DA303")]


def c_a10():
    d = deps("RS03AXPD-DP03A-02-VEL3DA303")[-1]
    assert ended(d)
    return [("last deployment ended " + d["stopDateTime"][:10], on(d["stopDateTime"]))]


def c_a11():
    b = deps("RS01SBPS-PC01A-06-VADCPB101")[0]
    m, model = make("RS01SBPS-PC01A-06-VADCPB101")
    return [(f"{m} {model}", lit(model)), ("from " + b["startDateTime"][:10], on(b["startDateTime"]) + "|" + b["startDateTime"][:7] + r"|August 2024")]


def c_a12():
    return [("deployed on " + deps("RS03CCAL-MJ03F-11-PADCPA301")[0]["CUID_Deploy"], lit(deps("RS03CCAL-MJ03F-11-PADCPA301")[0]["CUID_Deploy"]))]


def c_a13():
    m, model = make("RS03ASHS-PN03B-06-CAMHDA301")
    return [(m, lit(m)), (model, lit(model))]


def c_a14():
    found = sorted({re.sub(r"^P\d-", "", s) for s in serials("RS03ASHS-PN03B-06-CAMHDA301")})
    return [(f"serial {x}", serial_rx(x)) for x in found]


def c_a15():
    latest = [(depth_of(deps(r)[-1]), r) for r in _by if re.fullmatch(r"[A-Z0-9]{8}-[A-Z0-9]{5}-[A-Z0-9]{2}-[A-Z0-9]{9}", r) and depth_of(deps(r)[-1])]
    depth, refdes = max(latest)
    site = VOCAB.get(refdes, {}).get("TOC_L2", "") or refdes[:8]
    return [(f"{int(depth)} m", rf"\b{int(depth):,}\s*m|\b{int(depth)}\s*m".replace(",", ",?")), (site, r"Slope Base" if "Slope Base" in site else lit(site))]


def c_a16():
    e = SOURCED["scpr_cabled_gauges"]
    return [(f"gauge {c['serial']}", lit(c["serial"])) for c in e["components"] if c["serial"]]


def c_a17():
    e = SOURCED["scpr_unit001_2013"]
    return [(f"gauge {c['serial']}", lit(c["serial"])) for c in e["components"]] + [(c["model"], r"410\s?K") for c in e["components"][:1]]


def c_a18():
    return [("SN0011", r"SN0?011"), ("SN0007", r"SN0?007")]


def c_a19():
    return [(f"box {x}", rf"SN0*{int(re.sub(r'\D', '', x))}\b") for x in node_serials("RS03CCAL-MJ03F")]


def c_a20():
    az = set(AZ["AXEC3"].values())
    assert len(az) == 1
    a = az.pop()
    return [(f"{a}°", rf"\b{a}\s*°|\b{a} degrees"), (f"east {a + 90}°", rf"\b{a + 90}\s*°|\b{a + 90} degrees", "extra")]


def c_a21():
    issues = sorted(st for st, chans in AZ.items() if len(set(chans.values())) > 1)
    return [(st, st) for st in issues]


def c_a22():
    d = deps("RS03AXBS-LJ03A-12-CTDPFB301")[-1]
    cal = calibration_for(d["sensor.uid"], d["startDateTime"], CALS)
    return [("calibration " + cal[0], on(cal[0])), ("serial " + ASSETS[d["sensor.uid"]][SERIAL], serial_rx(ASSETS[d["sensor.uid"]][SERIAL]), "extra")]


def c_a23():
    d = deps("RS01SLBS-LJ01A-10-ADCPTE101")[-1]
    depth = int(depth_of(d))
    return [(f"{depth} m", rf"\b{depth:,}\s*m|\b{depth}\s*m".replace(",", ",?"))]


def c_a24():
    kinds = {"BOTPT": r"BOTPT|bottom pressure|tilt", "CTDPF": r"CTD", "HYDLF": r"hydrophone", "OBSSP": r"short[- ]period", "OBSBB": r"broadband"}
    here = {r.split("-")[3][:5] for r in _by if r.startswith("RS03ECAL-MJ03E-")}
    return [(k, rx) for k, rx in kinds.items() if k in here]


def c_a25():
    b = deps("CE02SHBP-LJ01D-10-PHSENH110")[0]
    m, model = make("CE02SHBP-LJ01D-10-PHSENH110")
    return [(model, r"SeapHOx"), ("from " + b["startDateTime"][:10], on(b["startDateTime"]) + r"|August 2025")]


def c_a26():
    d = deps("RS01SUM2-MJ01B-06-MASSPA101")[-1]
    assert ended(d)
    return [("ended " + d["stopDateTime"][:10], on(d["stopDateTime"]) + r"|June 2019")]


def c_a27():
    return [(f"serial {x}", serial_rx(x)) for x in serials("RS03AXBS-MJ03A-05-HYDLFA301")]


def c_a28():
    d = deps("RS03INT2-MJ03D-11-CTDPFB307")
    n = len(d)
    return [(f"{n} deployments", rf"\b{n}\b|\b{['zero','one','two','three','four','five','six'][n]}\b"), ("first " + d[0]["startDateTime"][:10], on(d[0]["startDateTime"]))]


def c_a29():
    d = deps("RS03ASHS-MJ03B-12-COVISA301")
    return [(f"{len(d)} deployments", rf"\b{len(d)}\b|\btwo\b"), ("from " + d[0]["startDateTime"][:10], on(d[0]["startDateTime"])),
            ("until " + d[-1]["stopDateTime"][:10], on(d[-1]["stopDateTime"]))]


def c_a30():
    m, _ = make("RS01SUM2-MJ01B-00-OSMOIA101")
    return [(m, lit(m.split(",")[0]))]


CASES = [
    ("A1", "What is the serial number of the broadband seismometer at Oregon Slope Base?", c_a1, None),
    ("A2", "What make and model is the broadband ocean bottom seismometer at Axial Base?", c_a2, None),
    ("A3", "When was the Central Caldera CTD first deployed?", c_a3, None),
    ("A4", "Has the Central Caldera BOTPT ever been recovered?", c_a4, None),
    ("A5", "Which serial numbers has the Axial Base seafloor CTD used?", c_a5, None),
    ("A6", "How many times has the Oregon Shelf benthic package CTD been deployed?", c_a6, None),
    ("A7", "What VEL3D is on the Southern Hydrate Ridge flank and what serial numbers has it had?", c_a7, None),
    ("A8", "Who makes the current meter on the Axial Base deep profiler, and what model is it?", c_a8, None),
    ("A9", "What serial numbers has the Axial deep profiler VEL3D had?", c_a9, None),
    ("A10", "When did the Axial Base deep profiler VEL3D's last deployment end?", c_a10, None),
    ("A11", "What vertical ADCP replaced the 600 kHz one on the Slope Base shallow profiler, and when?", c_a11, None),
    ("A12", "Which cruise deployed the Central Caldera ADCP?", c_a12, None),
    ("A13", "Who makes the CAMHD camera at ASHES?", c_a13, None),
    ("A14", "What are the serial numbers of the CAMHD?", c_a14, None),
    ("A15", "What is the deepest cabled RCA instrument, and how deep is it?", c_a15, None),
    ("A16", "What is the serial number of the SCPR at Axial Seamount?", c_a16, r"Sasagawa|2022EA002434"),
    ("A17", "What were the serial numbers of the pressure gauges in SCPR unit 001 at Axial in 2013?", c_a17, r"Sasagawa|2016EA000190|JOE"),
    ("A18", "Which junction box serial numbers were swapped at Axial Base LJ03A in 2017?", c_a18, None),
    ("A19", "Which junction boxes has the Central Caldera node MJ03F had over time?", c_a19, None),
    ("A20", "What is the azimuth of AXEC3?", c_a20, None),
    ("A21", "What seismometers have orientation issues?", c_a21, None),
    ("A22", "Which calibration is the Axial Base seafloor CTD using in its latest deployment?", c_a22, None),
    ("A23", "At what depth is the Oregon Slope Base seafloor ADCP deployed?", c_a23, None),
    ("A24", "Which instruments are at the Eastern Caldera at Axial?", c_a24, None),
    ("A25", "Which pH sensor replaced the SAMI-pH on the Oregon Shelf benthic package, and when?", c_a25, None),
    ("A26", "When did the Southern Hydrate Ridge summit mass spectrometer's last deployment end?", c_a26, None),
    ("A27", "What is the serial number of the low-frequency hydrophone at Axial Base?", c_a27, None),
    ("A28", "How many deployments has the International District 2 CTD had, and when was it first deployed?", c_a28, None),
    ("A29", "How many times was COVIS deployed at ASHES, and from when to when?", c_a29, None),
    ("A30", "Who makes the osmotic fluid sampler at Southern Hydrate Ridge?", c_a30, None),
]


def post(body):
    req = urllib.request.Request(WORKER, json.dumps(body).encode(), {"content-type": "application/json", "origin": "https://coszo.org", "user-agent": "curl/8.0 atlas-eval"})
    return json.load(urllib.request.urlopen(req, timeout=180))


def main():
    args = sys.argv[1:]
    model = args[args.index("--model") + 1] if "--model" in args else None
    out_path = Path(args[args.index("--out") + 1]) if "--out" in args else Path(__file__).with_name("asset_results.json")
    only = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--model", "--out"))]
    out = []
    for cid, q, facts_of, cite_rx in CASES:
        if only and cid not in only:
            continue
        facts = facts_of()
        try:
            d = post({"query": q, **({"model": model} if model else {})})
        except Exception as e:
            d = {"error": str(e)}
        a = d.get("answer") or d.get("error") or ""
        plain = a.translate({0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x00a0: " ", 0x202f: " ", 0x2009: " "})
        got = [(label, bool(re.search(rx, plain, re.I)), bool(extra)) for label, rx, *extra in facts]
        cites = [(c.get("title") or "") + " " + (c.get("url") or c.get("source_url") or "") for c in d.get("answer_citations", [])]
        if cite_rx:
            got.append(("cites " + cite_rx, any(re.search(cite_rx, c, re.I) for c in cites), False))
        asked = [g for _, g, x in got if not x]
        out.append({"id": cid, "question": q, "facts": got, "model": d.get("answer_model"), "answer": a, "citations": [c[:120] for c in cites]})
        print(f"{cid} {sum(asked)}/{len(asked)} [{d.get('answer_model')}] {', '.join(l + ('✓' if g else '✗') + (' (extra)' if x else '') for l, g, x in got)}", flush=True)
        time.sleep(3)
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    asked = [g for r in out for _, g, x in r["facts"] if not x]
    full = sum(all(g for _, g, x in r["facts"] if not x) for r in out)
    print(f"\nasked facts found {sum(asked)}/{len(asked)}; questions fully answered {full}/{len(out)}; results in {out_path}")


if __name__ == "__main__":
    main()
