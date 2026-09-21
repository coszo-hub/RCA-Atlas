import React, { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BorderBeam } from "border-beam";
import { ThinkingOrb } from "thinking-orbs";
import "./style.css";

const ForceGraph3D = lazy(() => import("react-force-graph-3d"));
const WORKER_URL = "https://rca-atlas.quakehunt.workers.dev";

function evidenceGraph(result) {
  const seen = new Set();
  const nodes = [];
  const add = (id, group) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    nodes.push({ id, group });
  };
  const hits = (result?.hits || []).slice(0, 6);
  const neighbors = (result?.neighbors || []).slice(0, 12);
  hits.forEach((hit) => add(hit.title || hit.chunk_id, "evidence"));
  neighbors.forEach((neighbor) => add(neighbor.name || neighbor.local_id, "entity"));
  const links = neighbors.flatMap((neighbor, index) => {
    const hit = hits[index % Math.max(1, hits.length)];
    const target = neighbor.name || neighbor.local_id;
    return hit && target ? [{ source: hit.title || hit.chunk_id, target }] : [];
  });
  return { nodes, links };
}

function App() {
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("How many earthquakes occurred at Axial Seamount yesterday?");
  const [askedQuestion, setAskedQuestion] = useState("");
  const graph = useMemo(() => evidenceGraph(result), [result]);
  const answer = result?.answer || "";

  useEffect(() => {
    if (!answer) return undefined;
    setTyped("");
    let index = 0;
    const timer = window.setInterval(() => {
      index += 3;
      setTyped(answer.slice(0, index));
      if (index >= answer.length) window.clearInterval(timer);
    }, 12);
    return () => window.clearInterval(timer);
  }, [answer]);

  const complete = Boolean(answer) && typed.length === answer.length;
  async function ask(event) {
    event.preventDefault();
    const question = query.trim();
    if (question.length < 2 || loading) return;
    setSearched(true);
    setAskedQuestion(question);
    setLoading(true);
    setResult(null);
    setTyped("");
    setError("");
    try {
      const response = await fetch(`${WORKER_URL}/v1/answer`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: question }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.answer) throw new Error(data.error || "Atlas is temporarily unavailable");
      setResult(data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Atlas is temporarily unavailable");
    } finally {
      setLoading(false);
    }
  }

  return <div className={searched ? "app searched" : "app"} data-theme="dark">
    <div className="wordmark">Ask Atlas</div>
    <main className="atlas-main">
      <form className="query-form" onSubmit={ask}>
        <BorderBeam size="md" colorVariant="colorful" strength={0.7} active={!loading}>
          <div className="search-box"><span className="atlas-chip">Atlas</span><textarea value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Research question" rows="2" disabled={loading}/><div className="composer-footer"><span className="composer-chip">Evidence</span><span className="composer-chip">Auto</span><button type="submit" aria-label="Search Ask Atlas" disabled={loading}>↑</button></div></div>
        </BorderBeam>
      </form>
      {searched && <section className="response" aria-live="polite">
        <div className="question-bubble">{askedQuestion}</div>
        {loading && <div className="solving"><ThinkingOrb state="solving" size={64} theme="dark" aria-label="Synthesizing evidence"/><span>Retrieving evidence</span></div>}
        {error && <p className="error">{error}</p>}
        {answer && <p className="generated">{typed}<span className={complete ? "cursor done" : "cursor"}>|</span></p>}
        {complete && <div className="sources"><span>Sources</span>{(result.answer_citations || []).map((source) => source.url ? <a key={`${source.id}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">{source.title || source.id} ↗</a> : <span className="source-label" key={source.id}>{source.title || source.id}</span>)}</div>}
        {complete && graph.nodes.length > 0 && <section className="graph-view"><div className="graph-caption"><span>Evidence graph</span><small>Drag to orbit · select a node</small></div><div className="graph-stage"><Suspense fallback={<p className="graph-loading">Loading graph…</p>}><ForceGraph3D graphData={graph} backgroundColor="#000000" nodeLabel="id" nodeColor={() => "#ffffff"} nodeVal={(node) => node.group === "evidence" ? 5 : 3} linkColor={() => "#191919"} linkWidth={0.65} linkOpacity={1}/></Suspense></div></section>}
      </section>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
