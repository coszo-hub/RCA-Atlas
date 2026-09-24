import DepthSection from "./DepthSection.jsx";
import SidePanel from "./SidePanel.jsx";
import Glyph from "../ui/Glyph.jsx";
import { fmtDepth, fmtRange, statusLabel } from "../data/format.js";

export default function SitePanel({ site, bundle, elevAt, onClose, onBack, onSensor, minimized, onMinimize, children }) {
  const inDetail = children != null && children !== false;
  const sensors = site.sensorIds.map(id => bundle.sensorById[id]);
  const region = bundle.regions.find(r => r.key === site.region)?.label;
  // Site names repeat across sites; the label is unique, so show it whenever it adds information.
  const eyebrow = [region, site.label !== site.name ? site.label : null].filter(Boolean).join(" · ");
  return (
    <SidePanel label={`${site.label} site`} eyebrow={eyebrow} title={site.name} closeLabel="Close site panel"
      sub={`${sensors.length} sensors · seafloor ${fmtDepth(site.seafloor)}`} onClose={onClose} onBack={onBack} inDetail={inDetail}
      minimized={minimized} onMinimize={onMinimize}>
      {inDetail ? children : (<>
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
            {site.unlocatedIds.map(id => bundle.sensorById[id]).filter(Boolean).map(s => (
              <button key={s.id} className="sp-row" onClick={() => onSensor(s.id)} aria-label={`${s.name}, location not recorded`}>
                <span className="nm">{s.name}</span>
                <span className="d">location not recorded</span>
              </button>))}
          </section>
        )}
      </>)}
    </SidePanel>
  );
}
