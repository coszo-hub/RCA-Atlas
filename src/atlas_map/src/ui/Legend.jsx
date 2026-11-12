import { useLayoutEffect, useRef } from "react";
import { FAULT_COLORS, FAULT_NAMES } from "../scene/subsurface.js";
import "./ui.css";

// The legend popover in the HUD dock, mounted while it is open. The map credits stay visible either way (Credit.jsx).
// subsurface: its credit while Axial's subsurface is shown, else null; realtime: whether the real-time catalog after 2021 is in.
// whales: the fin whale day on the map ({ day, tracks, detected, tracked, credit }) or null.
// byFault: whether the earthquakes are coloured by their focal mechanisms' faulting type.
export default function Legend({ credit, auv = false, subsurface = null, realtime = false, whales = null, byFault = false }) {
  const ref = useRef(null);
  // The legend is taller than a short window: measured from its top under the dock, it ends 16 px above the bottom
  // edge, or 8 px above the family strip when the strip reaches under it, and scrolls. The strip changes width with
  // the panels, so refit when it changes size, when a panel stacked above it in the dock opens or closes, and once
  // the popover's entrance ends (it starts 4 px higher).
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      const box = el.getBoundingClientRect(), strip = document.querySelector(".families")?.getBoundingClientRect();
      const under = strip && strip.width && strip.right > box.left && strip.left < box.right;
      el.style.maxHeight = `${Math.max(120, (under ? strip.top - 8 : innerHeight - 16) - box.top)}px`;
    };
    fit();
    addEventListener("resize", fit); addEventListener("animationend", fit);
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(fit) : null, strip = document.querySelector(".families");
    const stacked = [...(el.closest(".dock-pops")?.children ?? [])].filter(c => !c.contains(el));
    if (ro) for (const c of [strip, ...stacked].filter(Boolean)) ro.observe(c);
    return () => { removeEventListener("resize", fit); removeEventListener("animationend", fit); ro?.disconnect(); };
  }, []);
  return (
    <div className="panel legend" ref={ref}>
      <div className="panel-head"><span className="eyebrow">Legend</span></div>
      <div><div className="eyebrow">Site marker</div>
        <div className="row">One segment per sensor, colored by family</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" style={{ stroke: "var(--text-secondary)" }} strokeWidth="3" /></svg>Operating</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" style={{ stroke: "var(--text-secondary)" }} strokeWidth="3" opacity="0.28" /></svg>Not deployed / retired</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" style={{ stroke: "var(--text-secondary)" }} strokeWidth="1.2" /></svg>Planned (COSZO)</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" style={{ stroke: "var(--text-secondary)" }} strokeWidth="1.2" strokeDasharray="1.6 1.4" /></svg>Status unknown</div></div>
      <div><div className="eyebrow">Water column</div>
        <div className="row">Mooring above a seafloor site; solid where sensors sample</div></div>
      <div><div className="eyebrow">Cable</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ecebe6" strokeWidth="1.5" /></svg>Charted or mapped route</div>
        <div className="row"><svg className="glyph"><rect x="3" y="3" width="6" height="6" fill="#121211" stroke="#ecebe6" strokeWidth="1.5" /></svg>Primary node</div></div>
      <div><div className="eyebrow">Faults</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ff7a5c" strokeWidth="2.8" /></svg>Cascadia megathrust (deformation front)</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ff7a5c" strokeWidth="1.5" /></svg>Offshore Quaternary fault</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ff7a5c" strokeWidth="1.5" strokeDasharray="2 1.4" /></svg>Moderately constrained or inferred</div></div>
      <div><div className="eyebrow">DAS coverage</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#a98cff" strokeWidth="2.5" /></svg>2021 conventional OptaSense geometry</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ffbd59" strokeWidth="4" /></svg>2025–2026 MultiDAS unmasked span</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#62d7d2" strokeWidth="2.5" strokeDasharray="2 1.4" /></svg>2025–2026 OptoDAS first south span</div>
        <div className="row">Gold and cyan extents are schematic where their exact channel coordinates are unpublished.</div></div>
      {subsurface && <div><div className="eyebrow">Beneath Axial</div>
        {realtime ? <>
          <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="2.2" fill="#a8a69d" /></svg>Earthquake: relocated to 2021, real-time after</div>
          <div className="row"><svg className="glyph"><circle cx="4" cy="6" r="1.5" fill="#a8a69d" /><circle cx="10" cy="6" r="3" fill="#a8a69d" /></svg>Real-time: larger is a higher magnitude</div>
        </> : <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="2.2" fill="#a8a69d" /></svg>Earthquake, 2015–2021</div>}
        <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="3" fill="#ffcc85" /></svg>Within 60 days of the slider month</div>
        <div className="row"><svg className="glyph"><rect x="1" y="2" width="14" height="8" rx="1" fill="#cc6340" opacity="0.75" /></svg>Magma chamber (AMC) top</div>
        <div className="row"><svg className="glyph"><rect x="1.5" y="2.5" width="13" height="7" rx="1" fill="#edebe0" fillOpacity="0.12" stroke="#edebe0" strokeOpacity="0.5" /></svg>Caldera-wall faults</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ecebe6" strokeWidth="1.2" strokeDasharray="2 1.6" /></svg>Caldera rim</div>
        <div className="row">Lines every 100 m of depth; the seafloor above turns to glass</div></div>}
      <div><div className="eyebrow">Seafloor depth</div>
        <div className="ramp" /><div className="ramp-labels mono"><span>0 m</span><span>1,500</span><span>3,000</span><span>4,800</span></div></div>
      {byFault && <div><div className="eyebrow">Earthquakes by faulting</div>
        {Object.entries(FAULT_NAMES).map(([k, name]) => (
          <div className="row" key={k}><svg className="glyph"><circle cx="6" cy="6" r="2.6" fill={FAULT_COLORS[k]} /></svg>{name}</div>))}
        <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="2.2" fill="#80807a" opacity="0.4" /></svg>No focal mechanism</div>
        <div className="row">Each earthquake's own focal mechanism, quality A and B: 2015–2021 from cross-correlated polarities, 2022 to March 2025 from machine-learned ones. The 2026 real-time mechanisms are left out: they are copies of 27 earlier ones.</div></div>}
      {whales && <div><div className="eyebrow">Fin whales, {whales.day}</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#7fb2ff" strokeWidth="2" /><circle cx="6" cy="6" r="2" fill="#7fb2ff" /></svg>A whale's track, one colour each ({whales.tracks.length})</div>
        <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="2" fill="#9a988f" /></svg>Call in no track</div>
        <div className="row">{whales.tracked.toLocaleString("en-US")} of {whales.detected.toLocaleString("en-US")} calls detected that day were located in a track. Calls are located 20 m below the sea surface, where the whales were; the faint dashed lines are the tracks' shadows on the seafloor.</div></div>}
      <div className="attribution">Bathymetry: {credit}.{auv && " Axial summit: MBARI AUV survey (cruise V2506), 1 m."} Cable: NOAA/BOEM Marine Cadastre, OOI mariner notices; west of the US EEZ and at Axial, ooi_cables.csv (M. Kidiwela). Faults: USGS Quaternary Fault and Fold Database. Status: Nereus.{subsurface && ` ${subsurface}.`}{whales && ` ${whales.credit}.`}</div>
    </div>
  );
}
