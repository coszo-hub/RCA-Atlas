import { useState } from "react";
import { snippetFor } from "./snippets.js";

export default function GetThisData({ sensor }) {
  const [copied, setCopied] = useState(null);
  if (!sensor.access.length) return <section className="gtd"><h3>Get this data</h3><p className="muted">No access route is documented for this sensor yet.</p></section>;
  return (
    <section className="gtd"><h3>Get this data</h3>
      {sensor.access.map((a, i) => {
        const snip = snippetFor(a, sensor);
        return (
          <div key={i} className="route">
            <a href={a.url} target="_blank" rel="noreferrer">{a.label}</a>
            <p>{a.how}</p>
            {snip && (<div className="snippet"><div className="snip-head"><span>{snip.label}</span>
              <button onClick={() => { navigator.clipboard?.writeText(snip.code); setCopied(i); }}>{copied === i ? "Copied" : "Copy"}</button></div>
              <pre className="mono">{snip.code}</pre></div>)}
          </div>
        );
      })}
    </section>
  );
}
