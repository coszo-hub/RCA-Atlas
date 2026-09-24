import "./ui.css";

export default function Legend({ credit }) {
  return (
    <div className="panel legend">
      <div><div className="eyebrow">Site marker</div>
        <div className="row">One segment per sensor, colored by family</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" stroke="#d9d6cc" strokeWidth="3" /></svg>Operating</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" stroke="#d9d6cc" strokeWidth="3" opacity="0.28" /></svg>Not deployed / retired</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" stroke="#d9d6cc" strokeWidth="1.2" /></svg>Planned (COSZO)</div>
        <div className="row"><svg className="glyph"><path d="M1 6h10" stroke="#d9d6cc" strokeWidth="1.2" strokeDasharray="1.6 1.4" /></svg>Status unknown</div></div>
      <div><div className="eyebrow">Water column</div>
        <div className="row">Mooring above a seafloor site; solid where sensors sample</div></div>
      <div><div className="eyebrow">Cable</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ecebe6" strokeWidth="1.5" /></svg>Charted route</div>
        <div className="row"><svg className="glyph"><path d="M0 6h12" stroke="#ecebe6" strokeWidth="1.5" strokeDasharray="3 2" /></svg>Approximate (beyond US EEZ)</div>
        <div className="row"><svg className="glyph"><rect x="3" y="3" width="6" height="6" fill="#121211" stroke="#ecebe6" strokeWidth="1.5" /></svg>Primary node</div></div>
      <div><div className="eyebrow">Seafloor depth</div>
        <div className="ramp" /><div className="ramp-labels mono"><span>0 m</span><span>1,500</span><span>3,000</span><span>4,800</span></div></div>
      <div className="attribution">Bathymetry: {credit}. Cable: NOAA/BOEM Marine Cadastre, OOI mariner notices; west of the US EEZ approximate. Status: Nereus.</div>
    </div>
  );
}
