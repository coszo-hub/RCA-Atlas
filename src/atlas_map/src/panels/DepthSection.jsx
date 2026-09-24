import { useMemo, useState } from "react";
import { depthScale, layout, profile } from "./crossSection.js";
import { fmtDepth, fmtRange, statusGroup, statusLabel } from "../data/format.js";
import { SHAPES } from "../ui/Glyph.jsx";

const W = 408, H = 320, PAD = 36;   // viewBox starts at y = -10 so the 0 m label and 5 m dots are not clipped

export default function DepthSection({ site, bundle, elevAt, onSensor }) {
  const [hover, setHover] = useState(null);
  const order = useMemo(() => Object.fromEntries(bundle.families.map((f, i) => [f.key, i])), [bundle]);
  const sensors = site.sensorIds.map(id => bundle.sensorById[id]);
  const prof = profile(site, elevAt);
  const scale = depthScale(site, H), pts = layout(site, sensors, order, W - PAD, H, prof);
  const floorPath = "M " + prof.map(p => `${PAD + p.x * (W - PAD)} ${scale.y(Math.max(0, p.depth))}`).join(" L ") + ` L ${W} ${H} L ${PAD} ${H} Z`;
  return (
    <figure className="depth-section" aria-label={`Depth cross-section of ${site.name}`}>
      <svg viewBox={`0 -10 ${W} ${H + 18}`} width="100%">
        <line x1={PAD} x2={W} y1="0" y2="0" className="surface-line" />
        {scale.ticks.map(t => <g key={t.depth}><line x1={PAD - 4} x2={PAD} y1={t.y} y2={t.y} className="tick" />
          <text x={PAD - 7} y={t.y + 3} className="tick-label mono">{t.depth.toLocaleString("en-US")}</text></g>)}
        {scale.breakAt != null && <path d={`M ${PAD - 8} ${scale.breakAt - 3} l 8 -3 M ${PAD - 8} ${scale.breakAt + 3} l 8 -3`} className="axis-break" />}
        <path d={floorPath} className="seafloor" pathLength="1" />
        {pts.map(p => {
          const s = bundle.sensorById[p.id], fam = bundle.familyByKey[s.family], g = statusGroup(s.status);
          const style = { "--delay": `${500 + order[s.family] * 60}ms` };
          // Position via coordinates, not a transform attribute: the settle animation's CSS transform would override it.
          const x = PAD + p.x;
          return (
            <g key={p.id} className={`sensor ${g}`} style={style}
               onMouseEnter={() => setHover(p.id)} onMouseLeave={() => setHover(null)} onClick={() => onSensor(p.id)}>
              {p.y2 != null && <line x1={x} x2={x} y1={p.y} y2={p.y2} stroke={fam.color} strokeWidth="3" opacity={g === "offline" ? 0.3 : 0.9} />}
              {/* The family glyph (not just its color) marks the sensor; status shows as fill, dash and fade. */}
              <svg className="mark" x={x - 5.5} y={p.y - 5.5} width="11" height="11" viewBox="0 0 12 12" overflow="visible" opacity={g === "offline" ? 0.3 : 1}>
                <g stroke={fam.color} strokeWidth="1.6" strokeDasharray={g === "unknown" ? "2 1.5" : undefined}>
                  {SHAPES[fam.glyph](g === "planned" || g === "unknown" ? "none" : fam.color)}</g>
              </svg>
            </g>
          );
        })}
      </svg>
      {hover && (() => { const s = bundle.sensorById[hover]; return (
        <figcaption className="ds-tip">
          <b>{s.name}</b> · {s.type.replaceAll("_", " ")} · {s.depthRange ? fmtRange(...s.depthRange) : fmtDepth(s.depth)} · {statusLabel(s.status)}
          {s.access.some(a => ["erddap", "earthscope", "qaqc", "pi_portal"].includes(a.kind)) ? " · live data" : ""}
        </figcaption>); })()}
    </figure>
  );
}
