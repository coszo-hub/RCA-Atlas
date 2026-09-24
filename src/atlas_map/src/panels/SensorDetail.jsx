import Glyph from "../ui/Glyph.jsx";
import GetThisData from "./GetThisData.jsx";
import LiveStatus from "./live/LiveStatus.jsx";
import LiveData from "./live/LiveData.jsx";
import { fmtDepth, fmtRange } from "../data/format.js";

// `backLabel` names where the back control returns (a site, or the unplaced list); it defaults to the sensor's site.
export default function SensorDetail({ sensor, bundle, onBack, backLabel }) {
  const fam = bundle.familyByKey[sensor.family];
  const hasLive = sensor.access.some(a => ["erddap", "earthscope", "qaqc", "pi_portal"].includes(a.kind));
  return (
    <div className="sensor-detail">
      <button className="back" onClick={onBack}>← {backLabel ?? bundle.siteById[sensor.site]?.label ?? "Back"}</button>
      <h2><Glyph glyph={fam.glyph} color={fam.color} size={13} /> {sensor.name}</h2>
      <div className="meta mono">{sensor.type.replaceAll("_", " ")} · {sensor.depthRange ? fmtRange(...sensor.depthRange) : fmtDepth(sensor.depth)}
        {sensor.manufacturer ? ` · ${sensor.manufacturer}${sensor.model ? " " + sensor.model : ""}` : ""}</div>
      {sensor.lat == null && <div className="meta">No recorded position, so it is not drawn on the map.</div>}
      <LiveStatus sensor={sensor} manifest={bundle.manifest} />
      {hasLive ? <LiveData sensor={sensor} /> :
        <section className="no-feed"><h3>Live data</h3><p>No live feed. {sensor.statusGroup === "planned" ? "This sensor is planned for COSZO; its data will appear here once it is deployed and publishing." : "No public data service is known for this sensor."}</p></section>}
      <GetThisData sensor={sensor} />
      {(sensor.sources.length > 0 || sensor.corrections.length > 0) && (
        <section className="sources"><h3>Sources</h3>
          {sensor.sources.map(u => <a key={u} href={u} target="_blank" rel="noreferrer">{u}</a>)}
          {sensor.corrections.map(c => <p key={c} className="correction">Corrected in the atlas: {c}</p>)}
        </section>
      )}
    </div>
  );
}
