import { useEffect, useState } from "react";
import "./ui.css";

// Collapsed to a small toggle while the right-hand panel is open or the top row wraps, expanded otherwise
// (the chat alone does not collapse it); the user can flip it either way until that changes. The map
// credits stay visible either way (Credit.jsx).
// subsurface: its credit while Axial's subsurface is shown, else null.
export default function Legend({ credit, compact = false, auv = false, subsurface = null }) {
  const [override, setOverride] = useState(null);
  useEffect(() => setOverride(null), [compact]);
  const expanded = override ?? !compact;
  if (!expanded) {
    return <button className="panel hud-toggle legend-toggle" aria-expanded="false" onClick={() => setOverride(true)}>Legend</button>;
  }
  return (
    <div className="panel legend">
      <div className="legend-head"><span className="eyebrow">Legend</span>
        <button aria-label="Collapse legend" aria-expanded="true" onClick={() => setOverride(false)}>–</button></div>
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
      {subsurface && <div><div className="eyebrow">Beneath Axial</div>
        <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="2.2" fill="#a8a69d" /></svg>Earthquake, 2015–2021</div>
        <div className="row"><svg className="glyph"><circle cx="6" cy="6" r="3" fill="#ffcc85" /></svg>Within 60 days of the slider month</div>
        <div className="row"><svg className="glyph"><rect x="1" y="2" width="14" height="8" rx="1" fill="#cc6340" opacity="0.75" /></svg>Magma chamber (AMC) top</div>
        <div className="row"><svg className="glyph"><rect x="1.5" y="2.5" width="13" height="7" rx="1" fill="#edebe0" fillOpacity="0.12" stroke="#edebe0" strokeOpacity="0.5" /></svg>Caldera-wall faults</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ecebe6" strokeWidth="1.2" strokeDasharray="2 1.6" /></svg>Caldera rim</div>
        <div className="row">Lines every 100 m of depth; the seafloor above turns to glass</div></div>}
      <div><div className="eyebrow">Seafloor depth</div>
        <div className="ramp" /><div className="ramp-labels mono"><span>0 m</span><span>1,500</span><span>3,000</span><span>4,800</span></div></div>
      <div className="attribution">Bathymetry: {credit}.{auv && " Axial summit: MBARI AUV survey (cruise V2506), 1 m."} Cable: NOAA/BOEM Marine Cadastre, OOI mariner notices; west of the US EEZ and at Axial, ooi_cables.csv (M. Kidiwela). Status: Nereus.{subsurface && ` ${subsurface}.`}</div>
    </div>
  );
}
