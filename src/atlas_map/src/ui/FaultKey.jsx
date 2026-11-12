import { FAULT_COLORS, FAULT_NAMES } from "../scene/subsurface.js";
import "./ui.css";

// In place of the sensor families while Axial's earthquakes are coloured by faulting: what each colour means, and how
// many earthquakes have it (counts: { N, R, S, U, none }).
export default function FaultKey({ counts }) {
  const n = v => (v ?? 0).toLocaleString("en-US");
  return (
    <div className="panel families fault-key" role="group" aria-label="Earthquake colours: faulting type">
      {Object.entries(FAULT_NAMES).map(([k, name]) => (
        <span key={k} className="fault-item">
          <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4" fill={FAULT_COLORS[k]} /></svg>
          <span>{name}</span><span className="n mono">{n(counts[k])}</span>
        </span>
      ))}
      <span className="fault-item">
        <svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="3.5" fill="#80807a" opacity="0.45" /></svg>
        <span>No focal mechanism</span><span className="n mono">{n(counts.none)}</span>
      </span>
    </div>
  );
}
