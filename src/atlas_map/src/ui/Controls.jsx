import { useEffect, useState } from "react";
import { MinButton, MinTab } from "./Minimize.jsx";
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

// The earthquake timeline beneath Axial: a month slider (cumulative through that month) with play/pause.
function QuakeTimeline({ scene, sub }) {
  const last = sub.months.length - 1;
  const [month, setMonth] = useState(last), [playing, setPlaying] = useState(false);
  useEffect(() => { scene.setQuakesThrough(month); }, [scene, month]);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setMonth(m => Math.min(last, m + 1)), 140);
    return () => clearInterval(id);
  }, [playing, last]);
  useEffect(() => { if (month === last) setPlaying(false); }, [month, last]);
  const label = sub.months[month].label, n = sub.countThrough(month).toLocaleString("en-US");
  return (
    <div className="timeline">
      <div className="ctl-row"><span className="eyebrow">Earthquakes</span><span className="mono readout">to {label} · {n}</span></div>
      <div className="ctl-row">
        <button className="play" aria-label={playing ? "Pause" : "Play month by month"} onClick={() => {
          if (!playing && month === last) setMonth(0);
          setPlaying(!playing);
        }}>
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            {playing ? <path d="M2 1h2v8H2zM6 1h2v8H6z" fill="currentColor" /> : <path d="M2 1l7 4-7 4z" fill="currentColor" />}
          </svg>
        </button>
        <input type="range" min="0" max={last} step="1" value={month} aria-label="Earthquakes through month"
          aria-valuetext={`Through ${label}: ${n} earthquakes`} onChange={e => { setPlaying(false); setMonth(+e.target.value); }} />
      </div>
    </div>
  );
}

// Collapsed to a small tab while the top row wraps (it would otherwise sit over the middle of the map), and minimizable
// at any width; the user can flip it either way until the layout changes. The switches keep their state while collapsed.
// deep: whether Axial's subsurface is shown (App owns it; the legend and credits follow it).
export default function Controls({ scene, compact = false, deep = false, onDeep }) {
  const sub = scene?.subsurface;
  const [override, setOverride] = useState(null);
  useEffect(() => setOverride(null), [compact]);
  const expanded = override ?? !compact;
  const [view, setView] = useState("3d"), [style, setStyle] = useState("relief"), [color, setColor] = useState("depth");
  const [exag, setExag] = useState(scene?.U?.exag?.value ?? 6);
  useEffect(() => { if (scene) scene.onExag = v => setExag(v); return () => { if (scene) scene.onExag = null; }; }, [scene]);
  const [detail, setDetail] = useState("16 m");   // the finest Axial summit level on screen
  const [das, setDas] = useState(true);
  useEffect(() => { const id = setInterval(() => scene?.auv && setDetail(scene.auv.finest()), 250); return () => clearInterval(id); }, [scene]);
  if (!expanded) return <MinTab className="controls-toggle" onClick={() => setOverride(true)}>Terrain controls</MinTab>;
  return (
    <div className="panel controls">
      <div className="panel-head"><span className="eyebrow">Terrain</span><MinButton label="terrain controls" onClick={() => setOverride(false)} /></div>
      <Seg label="View" options={[["3d", "3D"], ["2d", "2D"]]} value={view} onChange={v => { setView(v); scene.setView(v); }} />
      <Seg label="Style" options={[["relief", "Relief"], ["contours", "Contours"]]} value={style} onChange={v => { setStyle(v); scene.setStyle(v); }} />
      <Seg label="Color" options={[["depth", "Depth"], ["mono", "Mono"]]} value={color} onChange={v => { setColor(v); scene.setColor(v); }} />
      <div className="ctl-row">
        <label className="eyebrow" htmlFor="exag">Vertical <span className="mono">×{Number(exag).toFixed(1)}</span></label>
        <input id="exag" type="range" min="1" max="12" step="0.1" value={exag} disabled={view === "2d"}
          aria-label="Vertical exaggeration" onChange={e => { const v = +e.target.value; setExag(v); scene.flight = null; scene.setExag(v); }} />
      </div>
      {scene?.auv && <div className="ctl-row"><span className="eyebrow">Axial detail</span><span className="mono" aria-live="polite">{detail}</span></div>}
      {scene?.dasLines?.length > 0 && <Seg label="DAS coverage" options={[["on", "On"], ["off", "Off"]]} value={das ? "on" : "off"}
        onChange={v => { const on = v === "on"; setDas(on); scene.setDasVisible(on); }} />}
      {sub && <Seg label="Subsurface" options={[["off", "Off"], ["on", "On"]]} value={deep ? "on" : "off"}
        onChange={v => { onDeep?.(v === "on"); scene.setSubsurface(v === "on"); }} />}
      {sub && deep && <QuakeTimeline scene={scene} sub={sub} />}
      <div className="hint">Drag to move · <kbd>Ctrl</kbd>-drag to rotate · Scroll to zoom · <kbd>←</kbd><kbd>↑</kbd><kbd>↓</kbd><kbd>→</kbd> to move · Hover the cable or a node for details</div>
    </div>
  );
}
