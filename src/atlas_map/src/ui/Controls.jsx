import { useEffect, useMemo, useState } from "react";
import { unrestStrip, upliftAt } from "../scene/subsurface.js";
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

// Axial's unrest since 2015, when the real-time catalog and uplift are built: each month's earthquakes (bars, log
// scale) and the caldera's uplift against the eve of the 2015 eruption (lines; dashed, that level). A click or drag
// picks the month.
function UnrestStrip({ strip, month, last, onMonth }) {
  const W = 300, H = 64, n = strip.bars.length, bw = W / n;
  const pick = e => {
    const r = e.currentTarget.getBoundingClientRect();
    onMonth(Math.max(0, Math.min(last, Math.floor(((e.clientX - r.left) / r.width) * n))));
  };
  const path = segs => segs.map(seg => "M" + seg.map(([x, y]) => `${(x * W).toFixed(1)},${((1 - y) * (H - 4) + 2).toFixed(1)}`).join("L")).join("");
  return (
    <svg className="unrest" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true"
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); pick(e); }}
      onPointerMove={e => { if (e.buttons) pick(e); }}>
      {strip.bars.map((b, i) => b.count > 0 && (
        <rect key={i} x={i * bw} width={Math.max(bw - 0.4, 0.4)} y={H - b.h * H * 0.62} height={b.h * H * 0.62}
          className={i <= month ? "bar on" : "bar"} />
      ))}
      <line x1="0" x2={W} y1={(1 - strip.zero) * (H - 4) + 2} y2={(1 - strip.zero) * (H - 4) + 2} className="zero" vectorEffect="non-scaling-stroke" />
      {Object.entries(strip.lines).map(([site, segs]) => (
        <path key={site} d={path(segs)} className={`uplift ${site}`} vectorEffect="non-scaling-stroke" />
      ))}
      <line x1={(month + 1) * bw} x2={(month + 1) * bw} y1="0" y2={H} className="cursor" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// Fin whale calls a day (each month's calls over its days with data; square-root scale, so every season shows), on
// the strip's months: the same seismometers, so the calling season shows against the earthquakes.
function WhaleStrip({ calls, days, month, last, onMonth }) {
  const W = 300, H = 18, n = calls.length, bw = W / n;
  const rate = calls.map((c, i) => (days[i] ? c / days[i] : null)), top = Math.max(...rate.filter(r => r != null));
  const pick = e => {
    const r = e.currentTarget.getBoundingClientRect();
    onMonth(Math.max(0, Math.min(last, Math.floor(((e.clientX - r.left) / r.width) * n))));
  };
  return (
    <svg className="unrest whales" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true"
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); pick(e); }} onPointerMove={e => { if (e.buttons) pick(e); }}>
      {rate.map((r, i) => r > 0 && <rect key={i} x={i * bw} width={Math.max(bw - 0.4, 0.4)} y={H - Math.sqrt(r / top) * H}
        height={Math.sqrt(r / top) * H} className={i <= month ? "whale on" : "whale"} />)}
      <line x1={(month + 1) * bw} x2={(month + 1) * bw} y1="0" y2={H} className="cursor" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// The earthquake timeline beneath Axial: a month slider (cumulative through that month) with play/pause, and the
// unrest strip above it when it is built.
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
  const strip = useMemo(() => sub.unrest && unrestStrip(sub.unrest, sub.months, sub.day0), [sub]);
  const label = sub.months[month].label, n = sub.countThrough(month).toLocaleString("en-US");
  const up = sub.unrest && upliftAt(sub.unrest, "MJ03F", sub.months, month, sub.day0);
  const fmt = v => (v == null ? "no data" : `${v > 0 ? "+" : ""}${Math.round(v)} cm`);
  const wm = sub.unrest?.monthly, whaleShift = strip && wm?.whaleCalls ? strip.offset : null;
  const wCalls = whaleShift != null ? sub.months.map((_, i) => wm.whaleCalls[i - whaleShift] ?? 0) : null;
  const wDays = whaleShift != null ? sub.months.map((_, i) => wm.whaleDays[i - whaleShift] ?? 0) : null;
  const perDay = wCalls && wDays[month] ? Math.round(wCalls[month] / wDays[month]) : null;
  return (
    <div className="timeline">
      <div className="ctl-row"><span className="eyebrow">Earthquakes</span><span className="mono readout">to {label} · {n}</span></div>
      {strip && <>
        <UnrestStrip strip={strip} month={month} last={last} onMonth={m => { setPlaying(false); setMonth(m); }} />
        {wCalls && <WhaleStrip calls={wCalls} days={wDays} month={month} last={last} onMonth={m => { setPlaying(false); setMonth(m); }} />}
        <div className="unrest-readout mono" title="That month's earthquakes, the caldera-centre (MJ03F) depth change since 23 April 2015 (the eve of the eruption), and fin whale calls a day">
          {label}: {strip.bars[month].count.toLocaleString("en-US")} quakes · uplift {fmt(up)}{wCalls && ` · ${perDay == null ? "no" : perDay.toLocaleString("en-US")} whale calls/day`}
        </div>
        <div className="unrest-key">Bars: earthquakes a month (log). Line: caldera-centre uplift; dashed: its level on the eve of the 2015 eruption (gauge drift not corrected).{wCalls && " Blue: fin whale calls a day (square root), recorded by the same seismometers."}</div>
      </>}
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
          aria-valuetext={`Through ${label}: ${n} earthquakes${strip ? `; ${strip.bars[month].count} that month; caldera-centre uplift ${fmt(up)} against the eve of the 2015 eruption` : ""}`}
          onChange={e => { setPlaying(false); setMonth(+e.target.value); }} />
      </div>
    </div>
  );
}

// The terrain popover in the HUD dock. The dock keeps it mounted while closed, so the switches keep their state.
// deep: whether Axial's subsurface is shown (App owns it; the legend and credits follow it).
// whaleDay: the fin whale day shown, or null (HudDock owns it; the legend follows it).
// quakeColor: how the earthquakes are coloured, "time" or "fault" (by focal mechanism), likewise.
export default function Controls({ scene, deep = false, onDeep, whaleDay = null, onWhaleDay, quakeColor = "time", onQuakeColor }) {
  const sub = scene?.subsurface;
  const [view, setView] = useState("3d"), [style, setStyle] = useState("relief"), [color, setColor] = useState("depth");
  const [exag, setExag] = useState(scene?.U?.exag?.value ?? 6);
  useEffect(() => { if (scene) scene.onExag = v => setExag(v); return () => { if (scene) scene.onExag = null; }; }, [scene]);
  const [detail, setDetail] = useState("16 m");   // the finest Axial summit level on screen
  const [das, setDas] = useState(false), [faults, setFaults] = useState(true);
  const [dasKinds, setDasKinds] = useState({ conventional: true, multidas: true, optodas: true });
  useEffect(() => { const id = setInterval(() => scene?.auv && setDetail(scene.auv.finest()), 250); return () => clearInterval(id); }, [scene]);
  return (
    <div className="panel controls">
      <div className="panel-head"><span className="eyebrow">Terrain</span></div>
      <Seg label="View" options={[["3d", "3D"], ["2d", "2D"]]} value={view} onChange={v => { setView(v); scene.setView(v); }} />
      <Seg label="Style" options={[["relief", "Relief"], ["contours", "Contours"]]} value={style} onChange={v => { setStyle(v); scene.setStyle(v); }} />
      <Seg label="Color" options={[["depth", "Depth"], ["mono", "Mono"]]} value={color} onChange={v => { setColor(v); scene.setColor(v); }} />
      <div className="ctl-row">
        <label className="eyebrow" htmlFor="exag">Vertical <span className="mono">×{Number(exag).toFixed(1)}</span></label>
        <input id="exag" type="range" min="1" max="12" step="0.1" value={exag} disabled={view === "2d"}
          aria-label="Vertical exaggeration" onChange={e => { const v = +e.target.value; setExag(v); scene.flight = null; scene.setExag(v); }} />
      </div>
      {scene?.auv && <div className="ctl-row"><span className="eyebrow">Axial detail</span><span className="mono" aria-live="polite">{detail}</span></div>}
      {scene?.faultLines?.length > 0 && <Seg label="Faults" options={[["on", "On"], ["off", "Off"]]} value={faults ? "on" : "off"}
        onChange={v => { const on = v === "on"; setFaults(on); scene.setFaultsVisible(on); }} />}
      {scene?.dasLines?.length > 0 && <Seg label="DAS coverage" options={[["on", "On"], ["off", "Off"]]} value={das ? "on" : "off"}
        onChange={v => { const on = v === "on"; setDas(on); scene.setDasVisible(on); }} />}
      {scene?.dasLines?.length > 0 && das && (
        <>
          <Seg label="2021 conventional" options={[["on", "On"], ["off", "Off"]]} value={dasKinds.conventional ? "on" : "off"}
            onChange={v => { const on = v === "on"; setDasKinds(s => ({ ...s, conventional: on })); scene.setDasKindVisible("conventional", on); }} />
          <Seg label="2025–26 MultiDAS" options={[["on", "On"], ["off", "Off"]]} value={dasKinds.multidas ? "on" : "off"}
            onChange={v => { const on = v === "on"; setDasKinds(s => ({ ...s, multidas: on })); scene.setDasKindVisible("multidas", on); }} />
          <Seg label="2025–26 OptoDAS" options={[["on", "On"], ["off", "Off"]]} value={dasKinds.optodas ? "on" : "off"}
            onChange={v => { const on = v === "on"; setDasKinds(s => ({ ...s, optodas: on })); scene.setDasKindVisible("optodas", on); }} />
        </>
      )}
      {sub && <Seg label="Subsurface" options={[["off", "Off"], ["on", "On"]]} value={deep ? "on" : "off"}
        onChange={v => { onDeep?.(v === "on"); scene.setSubsurface(v === "on"); }} />}
      {sub && deep && <QuakeTimeline scene={scene} sub={sub} />}
      {sub?.hasFaults && deep && <Seg label="Quake colour" options={[["time", "Time"], ["fault", "Faulting"]]} value={quakeColor}
        onChange={v => { onQuakeColor?.(v); scene.setQuakeColor(v); }} />}
      {scene?.whales && <div className="ctl-row">
        <label className="eyebrow" htmlFor="whale-day">Fin whale tracks</label>
        <select id="whale-day" value={whaleDay ?? ""} onChange={e => { const d = e.target.value || null; onWhaleDay?.(d); scene.setWhaleDay(d); }}>
          <option value="">Off</option>
          {scene.whales.days.map(d => <option key={d} value={d}>{d} · {scene.whales.data.days[d].tracks.length} tracks</option>)}
        </select>
      </div>}
    </div>
  );
}
