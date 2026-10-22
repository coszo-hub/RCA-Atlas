import DepthSection from "./DepthSection.jsx";
import SidePanel from "./SidePanel.jsx";
import Glyph from "../ui/Glyph.jsx";
import { fmtDate, fmtDepth, fmtRange, statusLabel } from "../data/format.js";
import { status as fetchStatus } from "../api/gateway.js";
import { useLive } from "./live/useLive.js";

// A row's status. Sensors Nereus does not track have no snapshot status ("Status unknown"); for those with an ERDDAP
// dataset or QA/QC plots the gateway reports how recent their data are, as the sensor card does. Others make no request.
function RowStatus({ sensor }) {
  const dated = sensor.status === "UNKNOWN" && sensor.refdes && sensor.access.some(a => a.kind === "erddap" || a.kind === "qaqc");
  const live = useLive(dated ? `status:${sensor.refdes}` : null, o => fetchStatus(sensor.refdes, o));
  const d = live.state === "ok" && live.data.evidenceMode === "data_age" ? live.data : null;
  if (!d) return <>{statusLabel(sensor.status)}</>;
  if (d.status) return <>{statusLabel(d.status)}</>;   // recent ERDDAP readings: operating
  const stale = Date.now() - new Date(d.latestAt) > 3 * 864e5;
  return <span className={stale ? "stale" : undefined}>{d.basis === "erddap" ? "Data to" : "Plots"} {fmtDate(d.latestAt)}</span>;
}

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
                  <span className="mono d"><RowStatus sensor={s} /> · {s.depthRange ? fmtRange(...s.depthRange) : fmtDepth(s.depth)}</span>
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
