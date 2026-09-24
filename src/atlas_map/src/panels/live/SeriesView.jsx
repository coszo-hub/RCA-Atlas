import { useMemo, useState } from "react";
import { series, variables } from "../../api/gateway.js";
import { fmtDate } from "../../data/format.js";
import Chart from "./Chart.jsx";
import Failure from "./Failure.jsx";
import { defaultMeasurement } from "./measurement.js";
import { checkCustom, preset } from "./ranges.js";
import { useLive } from "./useLive.js";

export default function SeriesView({ refdes }) {
  const vars = useLive(`vars:${refdes}`, o => variables(refdes, o));
  const [varName, setVar] = useState(null), [range, setRange] = useState("24h"), [custom, setCustom] = useState(null);
  const [draft, setDraft] = useState({ from: "", to: "" }), [draftErr, setDraftErr] = useState(null);
  const listed = vars.data?.variables ?? [];
  const chosen = varName ?? defaultMeasurement(refdes, listed.map(v => v.name));
  // A preset is fixed when chosen, so re-renders do not refetch as the clock ticks. It ends at the newest reading.
  const dataEnd = vars.data?.coverage?.end ?? null;
  const presetWin = useMemo(() => (range === "custom" ? null : preset(range, new Date(), dataEnd)), [range, dataEnd]);
  const behind = presetWin && Date.now() - Date.parse(presetWin.end) > 3 * 3600e3;
  const win = range === "custom" ? custom : presetWin;
  const key = chosen && win ? `series:${refdes}:${chosen}:${win.start}:${win.end}` : null;
  const data = useLive(key, o => series(refdes, { var: chosen, start: win.start, end: win.end }, o));

  if (vars.state === "loading") return <p className="muted">Loading variables…</p>;
  if (vars.state === "error") return <Failure error={vars.error} retry={vars.retry} />;
  const list = vars.data?.variables ?? [];
  if (!list.length) return <p className="muted">This dataset lists no plottable measurements.</p>;
  const meta = list.find(v => v.name === chosen);
  const apply = () => {
    const r = checkCustom(draft.from, draft.to);   // checked here, before any request
    if (r.ok) { setCustom(r); setDraftErr(null); } else setDraftErr(r.message);
  };
  return (
    <div className="series">
      <div className="series-bar">
        <select aria-label="Measurement" value={chosen} onChange={e => setVar(e.target.value)}>
          {list.map(v => <option key={v.name} value={v.name}>{v.longName ?? v.name}{v.units ? ` (${v.units})` : ""}</option>)}
        </select>
        <div className="seg" role="group" aria-label="Time range">
          {["24h", "7d", "30d"].map(k => <button key={k} aria-pressed={range === k} onClick={() => setRange(k)}>{k}</button>)}
          <button aria-pressed={range === "custom"} onClick={() => setRange("custom")}>Custom</button>
        </div>
      </div>
      {range === "custom" && (
        <div className="custom-range">
          <label>From <input type="datetime-local" aria-label="From" value={draft.from} onChange={e => setDraft({ ...draft, from: e.target.value })} /></label>
          <label>To <input type="datetime-local" aria-label="To" value={draft.to} onChange={e => setDraft({ ...draft, to: e.target.value })} /></label>
          <button onClick={apply}>Apply</button>
          <span className="muted">Times in UTC.</span>
          {draftErr && <p className="degraded">{draftErr}</p>}
        </div>
      )}
      {behind && <p className="muted">The newest reading is from {fmtDate(dataEnd)}; the {range} window ends there.</p>}
      {data.state === "loading" && <p className="muted">Loading readings…</p>}
      {data.state === "error" && <Failure error={data.error} retry={data.retry} />}
      {data.state === "ok" && (data.data.points.length
        ? (<><Chart points={data.data.points} unit={data.data.units} label={meta?.longName ?? chosen} />
            <p className="chart-foot mono">{data.data.rawCount.toLocaleString("en-US")} readings{data.data.rawCount > data.data.points.length ? `, shown as ${data.data.points.length.toLocaleString("en-US")}` : ""} · drag to zoom, double-click to reset · <a href={data.data.downloadUrl} target="_blank" rel="noreferrer">Download this range (CSV)</a></p></>)
        : <p className="muted">No readings in this range.{vars.data?.coverage?.end ? ` The data runs to ${fmtDate(vars.data.coverage.end)}.` : ""}</p>)}
    </div>
  );
}
