"""Compares the evidence two Graph-RAG APIs give the Worker (for instance the live search and a new one), without a
model: for every question of the asset, literature content and literature title evals, the Worker's answer path
runs locally against each API (evidence_prompts.mjs) and each expected fact or paper title is looked for in the
prompt the model would get. Reports the facts each API's evidence holds and the questions where they differ.
Usage: python3 evidence_ab.py <api origin A> <api origin B> [--out dir]"""
import ast, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))


def literal_cases(path):
    """The CASES list of an eval script that runs on import, read without running it."""
    tree = ast.parse(Path(path).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "CASES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"no CASES in {path}")


def cases():
    import asset_eval
    out = []
    for cid, q, facts_of, _ in asset_eval.CASES:
        out.append(("asset", cid, q, [(label, rx) for label, rx, *extra in facts_of() if not extra]))
    for cid, _paper, q, facts, _abstract in literal_cases(HERE / "literature_content_eval.py"):
        out.append(("content", cid, q, [(label, rx) for label, rx, *extra in facts if not extra]))
    for i, (q, title_rx) in enumerate(literal_cases(HERE / "literature_eval.py"), 1):
        out.append(("titles", f"L{i}", q, [("paper title", title_rx)]))
    return out


def prompts(origin, all_cases, out_dir, name):
    qpath = out_dir / "questions.json"
    qpath.write_text(json.dumps([{"id": f"{kind}:{cid}", "question": q} for kind, cid, q, _ in all_cases]))
    key = next(l.split("=", 1)[1].strip() for l in open(ROOT / ".env") if l.startswith("GRAPHRAG_API_KEY="))
    out = out_dir / f"prompts_{name}.json"
    subprocess.run(["node", str(HERE / "evidence_prompts.mjs"), origin, str(qpath), str(out)], check=True,
                   env={**os.environ, "ATLAS_API_KEY": key}, stderr=open(out_dir / f"prompts_{name}.log", "w"))
    return {r["id"]: r for r in json.loads(out.read_text())}


def found(prompt, rx):
    plain = prompt.translate({0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x00a0: " ", 0x202f: " ", 0x2009: " "})
    return bool(re.search(rx, plain, re.I))


def main():
    args = sys.argv[1:]
    out_dir = Path(args[args.index("--out") + 1]) if "--out" in args else HERE / "evidence_ab"
    a, b = [x for i, x in enumerate(args) if not x.startswith("--") and (i == 0 or args[i - 1] != "--out")][:2]
    out_dir.mkdir(parents=True, exist_ok=True)
    all_cases = cases()
    pa, pb = prompts(a, all_cases, out_dir, "A"), prompts(b, all_cases, out_dir, "B")
    totals, diffs = {}, []
    for kind, cid, q, facts in all_cases:
        ra, rb = pa[f"{kind}:{cid}"], pb[f"{kind}:{cid}"]
        ga = [found(ra["prompt"], rx) for _, rx in facts]
        gb = [found(rb["prompt"], rx) for _, rx in facts]
        t = totals.setdefault(kind, [0, 0, 0])
        t[0] += sum(ga); t[1] += sum(gb); t[2] += len(facts)
        if ga != gb or ra.get("error") or rb.get("error"):
            diffs.append(f"{kind}:{cid} A {sum(ga)}/{len(facts)} B {sum(gb)}/{len(facts)}"
                         + "".join(f"\n    {label}: A {'✓' if x else '✗'} B {'✓' if y else '✗'}" for (label, _), x, y in zip(facts, ga, gb) if x != y)
                         + (f"\n    errors: A {ra.get('error')} B {rb.get('error')}" if ra.get("error") or rb.get("error") else "")
                         + f"\n    {q}")
    for kind, (x, y, n) in totals.items():
        print(f"{kind:8} facts in evidence: A {x}/{n}  B {y}/{n}")
    print("\n".join(["", "questions that differ:"] + diffs if diffs else ["", "no question differs"]))


if __name__ == "__main__":
    main()
