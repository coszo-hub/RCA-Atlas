import SidePanel from "./SidePanel.jsx";
import Glyph from "../ui/Glyph.jsx";
import { statusLabel } from "../data/format.js";

// Sensors with no usable position that name no catalogued site. They are not drawn on the map;
// this list is where they are found, and each opens its detail here.
export default function UnplacedPanel({ bundle, onClose, onBack, onSensor, minimized, onMinimize, children }) {
  const inDetail = children != null && children !== false;
  const sensors = bundle.unplaced.map(id => bundle.sensorById[id]).filter(Boolean);
  return (
    <SidePanel label="Unplaced sensors" eyebrow="Not on the map" title="Unplaced sensors" closeLabel="Close unplaced sensors"
      sub={`${sensors.length} sensor${sensors.length === 1 ? "" : "s"} · no recorded position`} onClose={onClose} onBack={onBack} inDetail={inDetail}
      minimized={minimized} onMinimize={onMinimize}>
      {inDetail ? children : (<>
        <p className="sp-note">These sensors have no usable position and name no catalogued site, so the map cannot draw them.</p>
        {bundle.families.map(f => {
          const inFam = sensors.filter(s => s.family === f.key);
          if (!inFam.length) return null;
          return (
            <section key={f.key} className="sp-family">
              <h3><Glyph glyph={f.glyph} color={f.color} /> {f.label}</h3>
              {inFam.map(s => (
                <button key={s.id} className="sp-row" onClick={() => onSensor(s.id)} aria-label={`${s.name}, ${statusLabel(s.status)}, no recorded position`}>
                  <span className="nm">{s.name}</span>
                  <span className="mono d">{statusLabel(s.status)}</span>
                </button>
              ))}
            </section>
          );
        })}
      </>)}
    </SidePanel>
  );
}
