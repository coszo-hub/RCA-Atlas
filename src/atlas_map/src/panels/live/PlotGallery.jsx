import { useState } from "react";
import { plots } from "../../api/gateway.js";
import Failure from "./Failure.jsx";
import { useLive } from "./useLive.js";

// What the QA/QC filenames' overlay and range parts mean (rca-data-tools draws each plot at full, standard and
// local ranges, plain or with annotations, flags or climatology).
const OVERLAY = { none: "plain", anno: "annotations", flag: "QC flags", clim: "climatology", qartod: "QARTOD" };
const SPAN = { day: "Day", week: "Week", month: "Month", year: "Year", deploy: "Deployment" };
const MAX_SHOWN = 12;

export default function PlotGallery({ refdes }) {
  const [want, setWant] = useState({ variable: null, span: null });
  const p = useLive(`plots:${refdes}:${want.variable ?? ""}:${want.span ?? ""}`, o => plots(refdes, o, want));
  if (p.state === "loading") return <p className="muted">Loading recent plots…</p>;
  if (p.state === "error") return <Failure error={p.error} retry={p.retry} />;
  const d = p.data, vars = d.variables ?? [];
  if (!vars.length) return <p className="muted">The RCA QA/QC site has no recent plots for this sensor.</p>;
  const shown = d.plots.slice(0, MAX_SHOWN);
  return (
    <div className="plots">
      <select aria-label="Plotted variable" value={d.variable} onChange={e => setWant({ variable: e.target.value, span: d.span })}>
        {vars.map(x => <option key={x}>{x}</option>)}
      </select>
      <div className="seg" role="group" aria-label="Plot time span">
        {(d.spans ?? []).map(s => <button key={s} aria-pressed={d.span === s} onClick={() => setWant({ variable: d.variable, span: s })}>{SPAN[s] ?? s}</button>)}
      </div>
      {shown.map(x => (
        <figure key={x.url}><img src={x.url} alt={`${d.variable}, ${x.timeSpan}, ${OVERLAY[x.overlay] ?? x.overlay}, ${x.dataRange} range`} loading="lazy" />
          <figcaption>{[x.depth, OVERLAY[x.overlay] ?? x.overlay, `${x.dataRange} range`].filter(Boolean).join(" · ")}</figcaption></figure>
      ))}
      {d.plots.length > shown.length && <p className="muted">{d.plots.length - shown.length} more for this span on the RCA QA/QC site.</p>}
      <p className="chart-foot mono">{d.total} QA/QC plots for this sensor across {vars.length} variables</p>
    </div>
  );
}
