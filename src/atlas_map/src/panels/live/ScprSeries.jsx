import { useMemo, useState } from "react";
import { fmtDate } from "../../data/format.js";
import Chart from "./Chart.jsx";
import Failure from "./Failure.jsx";
import { fetchScpr, MEASURES, RANGES, scprLines } from "./scpr.js";
import { useLive } from "./useLive.js";

// The cabled SCPR's two gauges from the hourly CSV on GitHub, fetched when the panel opens, so each day's
// regenerated file shows without rebuilding the atlas. Uplift by default: the caldera's inflation is the story.
export default function ScprSeries({ route }) {
  const live = useLive(`scpr:${route.csvUrl}`, o => fetchScpr(route.csvUrl, o));
  const [measure, setMeasure] = useState("uplift"), [range, setRange] = useState("All");
  const lines = useMemo(() => (live.data ? scprLines(live.data, measure, range) : null), [live.data, measure, range]);

  if (live.state === "loading") return <p className="muted">Loading the SCPR hourly record…</p>;
  if (live.state === "error") return <Failure error={live.error} retry={live.retry} />;
  if (!lines) return null;
  const { t, generated, provisionalAfter } = live.data;
  return (
    <div className="series">
      <div className="series-bar">
        <select aria-label="Measurement" value={measure} onChange={e => setMeasure(e.target.value)}>
          {MEASURES.map(m => <option key={m.key} value={m.key}>{m.label} ({m.unit})</option>)}
        </select>
        <div className="seg" role="group" aria-label="Time range">
          {Object.keys(RANGES).map(k => <button key={k} aria-pressed={range === k} onClick={() => setRange(k)}>{k}</button>)}
        </div>
      </div>
      {lines.readings
        ? <Chart lines={lines} unit={lines.measure.unit} />
        : <p className="muted">No {lines.measure.label.toLowerCase()} values in this range.
            {lines.lastValueAt ? ` The newest is from ${fmtDate(lines.lastValueAt)}.` : ""}</p>}
      <p className="chart-foot mono">
        {lines.count.toLocaleString("en-US")} hourly means to {fmtDate(t[t.length - 1])}
        {lines.lastValueAt && lines.lastValueAt < t[t.length - 1] ? `, ${lines.measure.label.toLowerCase()} to ${fmtDate(lines.lastValueAt)}` : ""}
        {generated ? ` · file regenerated ${fmtDate(generated)}` : ""} · drag to zoom, double-click to reset ·{" "}
        <a href={route.url} target="_blank" rel="noreferrer">CSV on GitHub</a>
      </p>
      <p className="chart-foot">
        {measure === "uplift" ? "Uplift is relative to the mean of 6 July to 4 August 2018, with tides filtered out; ocean pressure changes are not removed. " : ""}
        {measure !== "raw" && provisionalAfter ? `The drift after the last calibration (${fmtDate(provisionalAfter)}) is extrapolated, so recent values are provisional.` : ""}
      </p>
    </div>
  );
}
