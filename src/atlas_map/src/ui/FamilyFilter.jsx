import Glyph from "./Glyph.jsx";
import "./ui.css";

export default function FamilyFilter({ families, sensors, focus, onChange }) {
  const located = sensors.filter(s => s.lat != null);
  const count = key => located.filter(s => s.family === key).length;
  const click = (key, shift) => {
    if (shift) { const next = new Set(focus); next.has(key) ? next.delete(key) : next.add(key); onChange(next); }
    else onChange(focus.size === 1 && focus.has(key) ? new Set() : new Set([key]));
  };
  return (
    <div className="panel families" role="group" aria-label="Sensor families">
      {families.filter(f => count(f.key) > 0).map(f => (   // a chip that filters nothing is noise (fiber is listed on the cable card)
        <button key={f.key} className={focus.size && !focus.has(f.key) ? "muted" : ""} aria-pressed={focus.has(f.key)}
          onClick={e => click(f.key, e.shiftKey)}>
          <Glyph glyph={f.glyph} color={f.color} /><span>{f.label}</span>
          <span className="n mono">{count(f.key)}</span>
        </button>
      ))}
    </div>
  );
}
