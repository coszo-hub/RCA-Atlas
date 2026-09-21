import React, { lazy, Suspense, useState } from "react";
import { createRoot } from "react-dom/client";
import { BorderBeam } from "border-beam";
import { ThinkingOrb } from "thinking-orbs";
import "./style.css";
import "./graph.css";

const ForceGraph3D = lazy(() => import("react-force-graph-3d"));

const evidence = [
  ["RCA PI DATA PORTAL", "Cabled Observatory Vent Imaging Sonar data availability and routing", "COVIS survey archives, browse products, engineering data, and processed products are identified alongside the ASHES site and OOI context."],
  ["RCA INFORMATION", "Acoustic and in-situ observations at ASHES", "COVIS observations connect hydrothermal discharge, deployment context, and the cited ASHES vent-field publication."],
];

const collectionGraph = {
  nodes: [["RCA Information",1132,"#6ce5d5"],["Instruments",438,"#a8e7ff"],["PI Portal",84,"#ffd38b"],["Websites",10981,"#83b9ff"],["Literature",942,"#d0a6ff"],["Figures",63,"#f4a8bc"],["Datasheets",1269,"#e8bb86"],["Station metadata",427,"#91dbc0"],["QA/QC",33,"#f3be82"],["Nereus",1728,"#80b8e8"],["Axial earthquakes",189,"#ff987f"],["COSZO documents",2516,"#8fdfd6"],["COSZO Hub",2136,"#b4beff"]].map(([id,count,color]) => ({id,count,color})),
  links: [["RCA Information","Instruments"],["RCA Information","Literature"],["RCA Information","PI Portal"],["Instruments","PI Portal"],["Instruments","Station metadata"],["Instruments","Datasheets"],["PI Portal","Websites"],["Literature","Figures"],["Literature","Websites"],["Axial earthquakes","Station metadata"],["Axial earthquakes","Websites"],["Nereus","Instruments"],["QA/QC","Instruments"],["COSZO documents","COSZO Hub"],["COSZO documents","Instruments"],["COSZO Hub","Websites"],["Figures","Datasheets"]].map(([source,target]) => ({source,target})),
};

function App() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(collectionGraph.nodes[0]);
  return <div className="app" data-theme="dark">
    <header><div className="brand"><span className="brand-dot">R</span><span><strong>RCA Atlas</strong><small>Evidence workspace</small></span></div><span className="preview">PUBLIC PREVIEW · PRIVATE DATA</span></header>
    <main>
      <section className="main-panel">
        <div className="eyebrow">REGIONAL CABLED ARRAY / COSZO</div>
        <h1>Follow the <span>evidence.</span></h1>
        <p className="lede">A Graph-RAG workspace that makes sources, entities, relationships, and data routes inspectable—not hidden behind an answer.</p>
        <BorderBeam size="line" colorVariant="ocean" strength={0.82} duration={3.1} className="search-beam">
          <div className="search-box"><div><label>RESEARCH QUESTION</label><p>Where can I get COVIS data?</p></div><button onClick={() => setOpen(true)}>Inspect evidence <b>→</b></button></div>
        </BorderBeam>
        <div className="live-note"><ThinkingOrb state="searching" size={20} theme="dark" aria-label="Evidence retrieval preview"/><span>Interactive preview — connect a private runtime to search the corpus.</span></div>
        {open && <section className="answer"><div className="answer-title"><div><div className="eyebrow">EVIDENCE PACKAGE</div><h2>COVIS data access</h2></div><span>2 sources · 5 graph links</span></div>
          <div className="evidence-grid">{evidence.map(([collection, title, text]) => <BorderBeam key={title} size="pulse-inner" colorVariant="ocean" strength={0.38} duration={2.8}><article><div className="card-meta"><span>{collection}</span><small>cited corpus chunk</small></div><h3>{title}</h3><p>{text}</p><a href="https://oceanobservatories.org/pi-instrument/cabled-array-vent-imaging-sonar-covis/" target="_blank" rel="noreferrer">Open source ↗</a></article></BorderBeam>)}</div>
        </section>}
        <section className="graph-view"><div className="answer-title"><div><div className="eyebrow">3D INFORMATION MAP</div><h2>Current corpus topology</h2></div><span>13 collections · 21,938 logical nodes</span></div><p className="graph-note">Drag to orbit, scroll to zoom, and select a collection. This overview is intentionally aggregated; private query views will show only evidence neighborhoods and their typed edges.</p><div className="graph-stage"><Suspense fallback={<p className="graph-loading">Loading 3D graph…</p>}><ForceGraph3D graphData={collectionGraph} backgroundColor="#091216" nodeLabel={(node) => `${node.id}: ${node.count.toLocaleString()} logical nodes`} nodeColor={(node) => node.color} nodeVal={(node) => Math.max(4, Math.log10(node.count) * 4)} linkColor={() => "rgba(126, 218, 215, 0.32)"} linkOpacity={0.55} linkWidth={0.6} onNodeClick={setSelected}/></Suspense><div className="graph-readout"><div className="eyebrow">SELECTED COLLECTION</div><strong>{selected.id}</strong><span>{selected.count.toLocaleString()} logical nodes</span></div></div></section>
      </section>
      <aside><div className="aside-top"><ThinkingOrb state="connecting" size={64} theme="dark" aria-label="Graph connections"/><div><div className="eyebrow">GRAPH CONTEXT</div><strong>Evidence is connected.</strong></div></div>
        <ol><li><b>Instrument</b><span>COVIS</span></li><li><b>Located at</b><span>ASHES Hydrothermal Field</span></li><li><b>Downloadable from</b><span>PI Portal</span></li><li><b>Documented by</b><span>OOI + RCA Information</span></li></ol>
        <div className="tool"><div className="eyebrow">LIVE TOOL POLICY</div><p>No tool is required to answer availability. Retrieval tools become relevant only for current holdings, download, analysis, or plotting.</p></div>
      </aside>
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
