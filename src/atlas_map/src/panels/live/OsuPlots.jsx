import { useState } from "react";

// Oregon State University's Axial plots of a BOTPT or seafloor CTD. The bundle lists the figures (OSU keeps fixed file
// names); the images load straight from OSU, which redraws them every 15 minutes, so the URL changes each 15 minutes.
const REDRAW_MS = 15 * 60 * 1000;

export default function OsuPlots({ route }) {
  const groups = [...new Set(route.figures.map(f => f.group))];
  const [want, setWant] = useState({ group: groups[0], span: null });
  const [stamp] = useState(() => Math.floor(Date.now() / REDRAW_MS));
  const [failed, setFailed] = useState({});
  const inGroup = route.figures.filter(f => f.group === want.group);
  const fig = inGroup.find(f => f.span === want.span) ?? inGroup[0];
  const src = `${fig.url}?t=${stamp}`;
  return (
    <div className="plots">
      <select aria-label="OSU plot" value={want.group} onChange={e => setWant({ group: e.target.value, span: null })}>
        {groups.map(g => <option key={g}>{g}</option>)}
      </select>
      <div className="seg" role="group" aria-label="OSU plot time span">
        {inGroup.map(f => <button key={f.url} aria-pressed={f === fig} onClick={() => setWant({ group: want.group, span: f.span })}>{f.span}</button>)}
      </div>
      <figure>
        {failed[src] ? <p className="muted">OSU's server did not return this plot.</p>
          : <img src={src} alt={fig.caption ?? `${fig.group}, ${fig.span}`} loading="lazy" onError={() => setFailed(x => ({ ...x, [src]: true }))} />}
        <figcaption>{fig.caption ?? `${fig.group}, ${fig.span}.`}</figcaption>
      </figure>
      <p className="chart-foot">Plots by Oregon State University (Bill Chadwick, Andy Lau), from <a href={route.url} target="_blank" rel="noreferrer">{route.url.replace(/^https:\/\//, "")}</a>. Redrawn every 15 minutes, spans past a week daily; the data are not quality-checked.</p>
    </div>
  );
}
