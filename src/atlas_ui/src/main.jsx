import React, { lazy, Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BorderBeam } from "border-beam";
import { ThinkingOrb } from "thinking-orbs";
import "./style.css";

const ForceGraph3D = lazy(() => import("react-force-graph-3d"));
const answer = "This is a live-data question. Atlas identifies Axial Seamount and the Axial earthquake query as the relevant evidence path. To return an exact count for yesterday, it must run the date-bounded live query, then cite the returned event records alongside the corpus context rather than inventing a count from the static snapshot.";
const sources = [
  ["Axial Seamount earthquake corpus", "https://axial.ocean.washington.edu/"],
  ["Axial earthquake date-query tool", "https://axial.ocean.washington.edu/"],
  ["OOI Regional Cabled Array · Axial Seamount", "https://oceanobservatories.org/"],
];
const graph = {
  nodes: ["Axial Seamount", "Yesterday", "Earthquake query", "Event records", "Axial earthquake corpus", "OOI RCA", "Date interval", "Citation package"].map((id) => ({ id })),
  links: [["Axial Seamount", "Earthquake query"], ["Yesterday", "Date interval"], ["Date interval", "Earthquake query"], ["Earthquake query", "Event records"], ["Axial Seamount", "Axial earthquake corpus"], ["Axial Seamount", "OOI RCA"], ["Event records", "Citation package"]].map(([source, target]) => ({ source, target })),
};

function App() {
  const [searched, setSearched] = useState(false);
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("How many earthquakes occurred at Axial Seamount yesterday?");
  useEffect(() => {
    if (!searched) return undefined;
    setTyped("");
    let index = 0;
    const timer = window.setInterval(() => {
      index += 2;
      setTyped(answer.slice(0, index));
      if (index >= answer.length) window.clearInterval(timer);
    }, 12);
    return () => window.clearInterval(timer);
  }, [searched]);
  const complete = typed.length === answer.length;
  return <div className={searched ? "app searched" : "app"} data-theme="dark">
    <div className="wordmark">Ask Atlas</div>
    <main className="atlas-main">
      <form className="query-form" onSubmit={(event) => { event.preventDefault(); setSearched(true); }}>
        <BorderBeam size="md" colorVariant="colorful" strength={0.7} active={!searched} theme="dark">
          <div className="search-box"><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Research question"/><button type="submit" aria-label="Search Ask Atlas">↵</button></div>
        </BorderBeam>
      </form>
      {searched && <section className="response" aria-live="polite">
        {!complete && <div className="solving"><ThinkingOrb state="solving" size={64} theme="dark" aria-label="Synthesizing evidence"/><span>Reading evidence</span></div>}
        <p className="generated">{typed}<span className={complete ? "cursor done" : "cursor"}>|</span></p>
        {complete && <div className="sources"><span>Sources</span>{sources.map(([title, href]) => <a key={href} href={href} target="_blank" rel="noreferrer">{title} ↗</a>)}</div>}
        {complete && <section className="graph-view"><div className="graph-caption"><span>Related nodes</span><small>Drag to orbit · select a node</small></div><div className="graph-stage"><Suspense fallback={<p className="graph-loading">Loading graph…</p>}><ForceGraph3D graphData={graph} backgroundColor="#000000" nodeLabel="id" nodeColor={() => "#ffffff"} nodeVal={() => 4} linkColor={() => "#191919"} linkWidth={0.65} linkOpacity={1}/></Suspense></div></section>}
      </section>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
