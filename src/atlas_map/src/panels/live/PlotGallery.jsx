import { useState } from "react";
import { plots } from "../../api/gateway.js";
import Failure from "./Failure.jsx";
import { useLive } from "./useLive.js";

export default function PlotGallery({ refdes }) {
  const p = useLive(`plots:${refdes}`, o => plots(refdes, o));
  const [variable, setVariable] = useState(null);
  if (p.state === "loading") return <p className="muted">Loading recent plots…</p>;
  if (p.state === "error") return <Failure error={p.error} retry={p.retry} />;
  const vars = [...new Set(p.data.plots.map(x => x.variable))];
  if (!vars.length) return <p className="muted">The RCA QA/QC site has no recent plots for this sensor.</p>;
  const v = variable ?? vars[0];
  const shown = p.data.plots.filter(x => x.variable === v).slice(0, 4);
  return (
    <div className="plots">
      <select aria-label="Plotted variable" value={v} onChange={e => setVariable(e.target.value)}>{vars.map(x => <option key={x}>{x}</option>)}</select>
      {shown.map(x => <figure key={x.url}><img src={x.url} alt={`${v}, ${x.timeSpan}`} loading="lazy" /><figcaption>{x.timeSpan} · {x.dataRange}</figcaption></figure>)}
    </div>
  );
}
