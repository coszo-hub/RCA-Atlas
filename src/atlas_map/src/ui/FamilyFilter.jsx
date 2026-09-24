import Glyph from "./Glyph.jsx";
import { MinButton, useMinimized } from "./Minimize.jsx";
import "./ui.css";

export default function FamilyFilter({ families, sensors, focus, onChange }) {
  const located = sensors.filter(s => s.lat != null);
  const count = key => located.filter(s => s.family === key).length;
  const click = (key, shift) => {
    if (shift) { const next = new Set(focus); next.has(key) ? next.delete(key) : next.add(key); onChange(next); }
    else onChange(focus.size === 1 && focus.has(key) ? new Set() : new Set([key]));
  };
  const [min, setMin] = useMinimized("families");
  // Minimized in place (same element), so the map's framing, which measures the strip, keeps following it.
  // A filter stays on while the strip is minimized; the tab says so.
  return (
    <div className={`panel families${min ? " minimized" : ""}`} role="group" aria-label="Sensor families">
      {min ? <button className="families-tab" aria-expanded="false" onClick={() => setMin(false)}>
        Sensor families{focus.size ? <span className="n mono">{focus.size} selected</span> : null}</button> : <>
      {families.filter(f => count(f.key) > 0).map(f => (   // a chip that filters nothing is noise (fiber is listed on the cable card)
        <button key={f.key} className={focus.size && !focus.has(f.key) ? "muted" : ""} aria-pressed={focus.has(f.key)}
          onClick={e => click(f.key, e.shiftKey)}>
          <Glyph glyph={f.glyph} color={f.color} /><span>{f.label}</span>
          <span className="n mono">{count(f.key)}</span>
        </button>
      ))}
      <MinButton label="sensor families" onClick={() => setMin(true)} /></>}
    </div>
  );
}
