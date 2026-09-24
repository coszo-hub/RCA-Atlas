import { useLayoutEffect, useRef } from "react";
import Glyph from "./Glyph.jsx";
import { fmtDepth, fmtRange, statusLabel } from "../data/format.js";
import "./ui.css";

const CABLE_TEXT = {
  charted: "Charted route, traced from the NOAA/BOEM Marine Cadastre cable protection zone (public domain, not for navigation).",
  approximate: "Approximate route. No public chart exists beyond the US Exclusive Economic Zone, so this is drawn straight between known points and could be off by a few km.",
};

function SiteCard({ site, bundle }) {
  const f = bundle.familyByKey, sensors = site.sensorIds.map(id => bundle.sensorById[id]);
  const counts = bundle.families.map(fam => [fam, sensors.filter(s => s.family === fam.key).length]).filter(([, n]) => n);
  const rows = [];
  for (const part of site.parts) {
    const inPart = sensors.filter(s => (s.location ?? site.name) === part);
    if (site.parts.length > 1 && inPart.length) rows.push(<div key={`h-${part}`} className="t-head">{part}</div>);
    for (const s of inPart) rows.push(
      <div key={s.id} className="t-item"><Glyph glyph={f[s.family].glyph} color={f[s.family].color} />
        <span title={s.name}>{s.name}</span>
        <span className="d mono">{statusLabel(s.status)} · {s.depthRange ? fmtRange(...s.depthRange) : fmtDepth(s.depth)}</span></div>);
  }
  const extra = site.unlocatedIds.length;
  return (<>
    <div className="t-name">{site.name}</div>
    <div className="t-sub">{sensors.length} sensor{sensors.length === 1 ? "" : "s"} · seafloor {fmtDepth(site.seafloor)} · {counts.map(([fam, n]) => `${n} ${fam.label.toLowerCase()}`).join(", ")}</div>
    {site.column.length > 0 && <div className="t-col">{site.column.map(c => <span key={c.kind}><b>{c.kind}</b> {fmtRange(c.a, c.b)} </span>)}</div>}
    <div className="t-list">{rows.slice(0, 16)}</div>
    {rows.length > 16 && <div className="t-more">+{rows.length - 16} more. Click to open the depth section.</div>}
    {extra > 0 && <div className="t-more">{extra} more sensor{extra > 1 ? "s have" : " has"} no recorded position.</div>}
  </>);
}

export default function Tooltip({ hover, bundle }) {
  const ref = useRef(null);
  // A long site card is taller than the fixed clamp allows: measure it and open it above the cursor when it
  // would run off the bottom of the window. Always set top, so a short card never inherits a tall card's lift.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !hover) return;
    const h = el.offsetHeight, fits = hover.y + 18 + h <= innerHeight - 8;
    el.style.top = `${fits ? Math.min(hover.y + 18, innerHeight - 240) : Math.max(8, hover.y - 18 - h)}px`;
  });
  if (!hover) return null;
  const { kind, item, x, y } = hover;
  const style = { left: Math.min(x + 18, innerWidth - 400), top: Math.min(y + 18, innerHeight - 240) };
  return (
    <div ref={ref} className="tip" style={style} role="tooltip">
      {kind === "site" && <SiteCard site={item} bundle={bundle} />}
      {kind === "node" && (<>
        <div className="t-name">{item.name}</div>
        <div className="t-sub">{item.description}</div>
        <div className="t-more">Position {item.accuracy}{item.note ? `. ${item.note}` : ""}</div>
      </>)}
      {kind === "cable" && (<>
        <div className="t-name">{item.kind}</div>
        <div className="t-sub">{item.route}{item.lengthKm ? ` · ${Math.round(item.lengthKm)} km` : ""}</div>
        <div className="t-col">{CABLE_TEXT[item.accuracy]}</div>
        {bundle.sensors.some(s => s.family === "fiber" && s.lat == null) && (
          <div className="t-col">Fiber-optic sensing experiments on the cable (exact positions not recorded): {bundle.sensors.filter(s => s.family === "fiber" && s.lat == null).map(s => s.name).join("; ")}.</div>
        )}
        <div className="t-more">Two backbone cables run from the Pacific City shore station: the south line to Hydrate Ridge and the Oregon shelf, the north line past the Mid-Plate node to Axial Seamount.</div>
      </>)}
    </div>
  );
}
