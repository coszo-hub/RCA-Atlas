import { useState } from "react";
import { waveform } from "../../api/gateway.js";
import { fmtMinutes } from "../../data/format.js";
import Chart from "./Chart.jsx";
import Failure from "./Failure.jsx";
import { useLive } from "./useLive.js";

// EarthScope serves its newest archived window, which can be an hour or more old.
const ends = endMs => (endMs ? `ends ${new Date(endMs).toISOString().slice(11, 16)} UTC, ${fmtMinutes((Date.now() - endMs) / 60_000)} ago` : "newest EarthScope data");

export default function WaveformView({ route }) {
  const [minutes, setMinutes] = useState(10);
  const station = `${route.network}.${route.station}`;
  const w = useLive(`wave:${station}:${route.channel}:${minutes}`, o => waveform(station, minutes, route.channel, o));
  return (
    <div className="waveform">
      <div className="seg" role="group" aria-label="Window">
        {[1, 5, 10, 30, 60].map(m => <button key={m} aria-pressed={minutes === m} onClick={() => setMinutes(m)}>{m} min</button>)}
      </div>
      {w.state === "loading" && <p className="muted">Loading the recording…</p>}
      {w.state === "error" && <Failure error={w.error} retry={w.retry} />}
      {w.state === "ok" && (w.data.points.length
        ? (<><Chart points={w.data.points} unit="counts" label={`${station} ${w.data.channel}`} />
            <p className="chart-foot mono">{w.data.channel} · {w.data.rate} samples/s · {ends(w.data.endMs)} · drag to zoom, double-click to reset</p>
            {w.data.requestedChannel && w.data.requestedChannel !== w.data.channel &&
              <p className="muted">{w.data.requestedChannel} has no recent data at EarthScope, so this shows {w.data.channel}, the same sensor at a lower sample rate.</p>}</>)
        : <p className="muted">{w.data.message ?? "No recording in this window."}</p>)}
    </div>
  );
}
