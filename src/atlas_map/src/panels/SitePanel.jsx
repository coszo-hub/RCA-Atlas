import { useEffect } from "react";
import DepthSection from "./DepthSection.jsx";
import Glyph from "../ui/Glyph.jsx";
import { fmtDepth, fmtRange, statusLabel } from "../data/format.js";
import "./panels.css";

export default function SitePanel({ site, bundle, elevAt, onClose, onBack, onSensor, children }) {
  const inDetail = children != null && children !== false;
  useEffect(() => {
    // Escape steps back from a sensor to the site, then closes. Inside a text field it belongs
    // to that field (the search box clears itself).
    const onKey = e => {
      if (e.key !== "Escape" || e.target?.closest?.("input, textarea")) return;
      if (inDetail && onBack) onBack(); else onClose();
    };
    addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
  }, [onClose, onBack, inDetail]);
  const sensors = site.sensorIds.map(id => bundle.sensorById[id]);
  const region = bundle.regions.find(r => r.key === site.region)?.label;
  // Site names repeat across sites; the label is unique, so show it whenever it adds information.
  const eyebrow = [region, site.label !== site.name ? site.label : null].filter(Boolean).join(" · ");
  return (
    <aside className="panel side-panel" aria-label={`${site.label} site`}>
      <div className="sp-head">
        <div><div className="eyebrow">{eyebrow}</div>
          <h2>{site.name}</h2>
          <div className="sub mono">{sensors.length} sensors · seafloor {fmtDepth(site.seafloor)}</div></div>
        <button className="close" aria-label="Close site panel" onClick={onClose}>×</button>
      </div>
      {children ?? (<>
        <DepthSection site={site} bundle={bundle} elevAt={elevAt} onSensor={onSensor} />
        {bundle.families.map(f => {
          const inFam = sensors.filter(s => s.family === f.key);
          if (!inFam.length) return null;
          return (
            <section key={f.key} className="sp-family">
              <h3><Glyph glyph={f.glyph} color={f.color} /> {f.label}</h3>
              {inFam.map(s => (
                <button key={s.id} className="sp-row" onClick={() => onSensor(s.id)} aria-label={`${s.name}, ${statusLabel(s.status)}`}>
                  <span className="nm">{s.name}</span>
                  <span className="mono d">{statusLabel(s.status)} · {s.depthRange ? fmtRange(...s.depthRange) : fmtDepth(s.depth)}</span>
                </button>
              ))}
            </section>
          );
        })}
        {site.unlocatedIds.length > 0 && (
          <section className="sp-family">
            <h3>Also at this site</h3>
            {site.unlocatedIds.map(id => (
              <div key={id} className="sp-row static"><span className="nm">{bundle.sensorById[id].name}</span>
                <span className="d">location not recorded</span></div>))}
          </section>
        )}
      </>)}
    </aside>
  );
}
