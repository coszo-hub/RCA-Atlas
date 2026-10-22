import { useState } from "react";
import FileBrowser from "./FileBrowser.jsx";
import OsuPlots from "./OsuPlots.jsx";
import PlotGallery from "./PlotGallery.jsx";
import SeriesView from "./SeriesView.jsx";
import WaveformView from "./WaveformView.jsx";

// One primary view, in this order: ERDDAP series, else EarthScope waveform, else QA/QC plots; then OSU's Axial plots
// and PI file browsing. QA/QC plots are filed under the route's refdes: a seismometer's is its OOI OBS.
export default function LiveData({ sensor }) {
  const by = k => sensor.access.find(a => a.kind === k);
  const erddap = by("erddap"), es = by("earthscope"), qaqc = by("qaqc"), osu = by("osu_axial"), pi = sensor.access.filter(a => a.kind === "pi_portal");
  const plotsRef = qaqc?.refdes ?? sensor.refdes;
  return (
    <section className="live-data"><h3>Live data</h3>
      {erddap ? <SeriesView refdes={sensor.refdes} /> : es ? <WaveformView route={es} /> : qaqc ? <PlotGallery refdes={plotsRef} /> : null}
      {(erddap || es) && qaqc && <Lazy summary="Recent QA/QC plots">{() => <PlotGallery refdes={plotsRef} />}</Lazy>}
      {osu && <Lazy summary="OSU Axial monitoring plots">{() => <OsuPlots route={osu} />}</Lazy>}
      {pi.map(r => <FileBrowser key={r.endpointId ?? r.url} route={r} />)}
    </section>
  );
}

// A gallery (and its requests) waits until the reader first opens the section; it stays mounted after that.
function Lazy({ summary, children }) {
  const [opened, setOpened] = useState(false);
  return (
    <details onToggle={e => e.currentTarget.open && setOpened(true)}>
      <summary>{summary}</summary>
      {opened && children()}
    </details>
  );
}
