import { useEffect, useState } from "react";
import "./ui.css";

function Seg({ label, options, value, onChange }) {
  return (
    <div className="ctl-row">
      <span className="eyebrow">{label}</span>
      <div className="seg" role="group" aria-label={label}>
        {options.map(([v, text]) => (
          <button key={v} aria-pressed={value === v} onClick={() => { if (v !== value) onChange(v); }}>{text}</button>
        ))}
      </div>
    </div>
  );
}

export default function Controls({ scene }) {
  const [view, setView] = useState("3d"), [style, setStyle] = useState("relief"), [color, setColor] = useState("depth");
  const [exag, setExag] = useState(scene?.U?.exag?.value ?? 6);
  useEffect(() => { if (scene) scene.onExag = v => setExag(v); return () => { if (scene) scene.onExag = null; }; }, [scene]);
  return (
    <div className="panel controls">
      <Seg label="View" options={[["3d", "3D"], ["2d", "2D"]]} value={view} onChange={v => { setView(v); scene.setView(v); }} />
      <Seg label="Style" options={[["relief", "Relief"], ["contours", "Contours"]]} value={style} onChange={v => { setStyle(v); scene.setStyle(v); }} />
      <Seg label="Color" options={[["depth", "Depth"], ["mono", "Mono"]]} value={color} onChange={v => { setColor(v); scene.setColor(v); }} />
      <div className="ctl-row">
        <label className="eyebrow" htmlFor="exag">Vertical <span className="mono">×{Number(exag).toFixed(1)}</span></label>
        <input id="exag" type="range" min="1" max="12" step="0.1" value={exag} disabled={view === "2d"}
          aria-label="Vertical exaggeration" onChange={e => { const v = +e.target.value; setExag(v); scene.flight = null; scene.setExag(v); }} />
      </div>
      <div className="hint">Drag to move · <kbd>Ctrl</kbd>-drag to rotate · Scroll to zoom · <kbd>←</kbd><kbd>↑</kbd><kbd>↓</kbd><kbd>→</kbd> to move · Hover the cable or a node for details</div>
    </div>
  );
}
