import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BorderBeam } from "border-beam";
import { ThinkingOrb } from "thinking-orbs";
import "./style.css";

const evidence = [
  ["RCA PI DATA PORTAL", "Cabled Observatory Vent Imaging Sonar data availability and routing", "COVIS survey archives, browse products, engineering data, and processed products are identified alongside the ASHES site and OOI context."],
  ["RCA INFORMATION", "Acoustic and in-situ observations at ASHES", "COVIS observations connect hydrothermal discharge, deployment context, and the cited ASHES vent-field publication."],
];

function App() {
  const [open, setOpen] = useState(false);
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
      </section>
      <aside><div className="aside-top"><ThinkingOrb state="connecting" size={64} theme="dark" aria-label="Graph connections"/><div><div className="eyebrow">GRAPH CONTEXT</div><strong>Evidence is connected.</strong></div></div>
        <ol><li><b>Instrument</b><span>COVIS</span></li><li><b>Located at</b><span>ASHES Hydrothermal Field</span></li><li><b>Downloadable from</b><span>PI Portal</span></li><li><b>Documented by</b><span>OOI + RCA Information</span></li></ol>
        <div className="tool"><div className="eyebrow">LIVE TOOL POLICY</div><p>No tool is required to answer availability. Retrieval tools become relevant only for current holdings, download, analysis, or plotting.</p></div>
      </aside>
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
