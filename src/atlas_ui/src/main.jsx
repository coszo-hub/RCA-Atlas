import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { BorderBeam } from "border-beam";
import { ThinkingOrb } from "thinking-orbs";
import "./style.css";

const WORKER_URL = "https://rca-atlas.quakehunt.workers.dev";

function modelLabel(model) {
  if (model === "gemini-2.5-flash") return "Gemini 2.5 Flash";
  if (model === "gemini-3.5-flash-lite") return "Gemini 3.5 Flash-Lite";
  if (model === "RCA Atlas graph evidence (no LLM)") return "Graph evidence · no LLM";
  if (model === "Groq GPT-OSS 120B") return "Groq GPT-OSS 120B";
  if (model?.startsWith("OpenAI gpt-")) return model.replace("OpenAI ", "OpenAI ").replaceAll("-", " ");
  if (model === "RCA Atlas graph route") return "RCA Atlas graph route";
  if (model === "axial_count_events (live catalog)") return "Live Axial catalog";
  return model || "Atlas Auto";
}

function evidenceGraph(result) {
  const seen = new Set();
  const nodes = [];
  const add = (id, group) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    nodes.push({ id, group });
  };
  const hits = (result?.hits || []).slice(0, 6);
  const neighbors = (result?.neighbors || []).slice(0, 8);
  hits.forEach((hit) => add(hit.title || hit.chunk_id, "evidence"));
  neighbors.forEach((neighbor) => add(neighbor.name || neighbor.local_id, "entity"));
  const links = neighbors.flatMap((neighbor, index) => {
    const hit = hits[index % Math.max(1, hits.length)];
    const target = neighbor.name || neighbor.local_id;
    return hit && target ? [{ source: hit.title || hit.chunk_id, target }] : [];
  });
  return { nodes, links };
}

function EvidenceGraph({ graph }) {
  const width = 720;
  const height = 360;
  const center = { x: width / 2, y: height / 2 };
  const positions = new Map(graph.nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, graph.nodes.length) - Math.PI / 2;
    const radius = node.group === "evidence" ? 88 : 138;
    return [node.id, { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius, group: node.group }];
  }));
  return <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evidence relationship map">
    {graph.links.map((link, index) => {
      const source = positions.get(link.source);
      const target = positions.get(link.target);
      return source && target && <line key={`${link.source}-${link.target}-${index}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y}/>;
    })}
    {graph.nodes.map((node) => {
      const point = positions.get(node.id);
      return <g key={node.id}><title>{node.id}</title><circle cx={point.x} cy={point.y} r={point.group === "evidence" ? 5 : 3}/></g>;
    })}
  </svg>;
}

function App() {
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [typed, setTyped] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("How many earthquakes occurred at Axial Seamount yesterday?");
  const [answerModel, setAnswerModel] = useState("auto");
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
        body: JSON.stringify({ query: question, model: answerModel, answer_mode: "evidence" }),
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
          <div className="search-box"><span className="atlas-chip">Atlas</span><textarea value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Research question" rows="2" disabled={loading}/><div className="composer-footer"><span className="composer-chip">Evidence</span><label className="model-select"><span className="visually-hidden">Answer model</span><select value={answerModel} onChange={(event) => setAnswerModel(event.target.value)} disabled={loading}><option value="auto">Auto · free fallback</option><optgroup label="Gemini · free"><option value="gemini-2.5-flash">Flash</option><option value="gemini-3.5-flash-lite">Flash-Lite</option></optgroup><optgroup label="Groq · free"><option value="groq-gpt-oss-120b">GPT-OSS 120B</option><option value="groq-gpt-oss-20b">GPT-OSS 20B</option><option value="groq-qwen3-8-27b">Qwen 3.8 27B</option></optgroup><option value="gpt-5.4-mini">OpenAI GPT-5.4 Mini</option><optgroup label="OpenAI · API credit required"><option value="gpt-5.6-sol" disabled>GPT-5.6 Sol</option><option value="gpt-5.5" disabled>GPT-5.5</option><option value="gpt-5.5-pro" disabled>GPT-5.5 Pro</option></optgroup></select></label><button type="submit" aria-label="Search Ask Atlas" disabled={loading}>↑</button></div></div>
        </BorderBeam>
      </form>
      {searched && <section className="response" aria-live="polite">
        <div className="question-bubble">{askedQuestion}</div>
        {loading && <div className="solving"><ThinkingOrb state="solving" size={64} theme="dark" aria-label="Synthesizing evidence"/><span>Retrieving evidence</span></div>}
        {error && <p className="error">{error}</p>}
        {answer && <div className="generated">{typed}<span className={complete ? "cursor done" : "cursor"}>|</span></div>}
        {complete && result.answer_model && <div className="answer-model">Answered by {modelLabel(result.answer_model)}</div>}
        {complete && (result.answer_links || []).length > 0 && <div className="answer-links"><span>Download</span>{result.answer_links.map((source) => <a key={`${source.id}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">{source.title || source.id} ↗</a>)}</div>}
        {complete && <div className="sources"><span>Sources</span>{(result.answer_citations || []).map((source) => source.url ? <a key={`${source.id}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">{source.title || source.id} ↗</a> : <span className="source-label" key={source.id}>{source.title || source.id}</span>)}</div>}
        {complete && graph.nodes.length > 1 && <section className="graph-view"><div className="graph-caption"><span>Evidence map</span><small>Hover a dot for its source</small></div><div className="graph-stage"><EvidenceGraph graph={graph}/></div></section>}
      </section>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
