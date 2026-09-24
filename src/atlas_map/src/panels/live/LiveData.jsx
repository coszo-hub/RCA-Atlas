import FileBrowser from "./FileBrowser.jsx";
import PlotGallery from "./PlotGallery.jsx";
import SeriesView from "./SeriesView.jsx";
import WaveformView from "./WaveformView.jsx";

// One primary view, in this order: ERDDAP series, else EarthScope waveform, else QA/QC plots; plus PI file browsing.
export default function LiveData({ sensor }) {
  const by = k => sensor.access.find(a => a.kind === k);
  const erddap = by("erddap"), es = by("earthscope"), qaqc = by("qaqc"), pi = sensor.access.filter(a => a.kind === "pi_portal");
  return (
    <section className="live-data"><h3>Live data</h3>
      {erddap ? <SeriesView refdes={sensor.refdes} /> : es ? <WaveformView route={es} /> : qaqc ? <PlotGallery refdes={sensor.refdes} /> : null}
      {erddap && qaqc && <details><summary>Recent QA/QC plots</summary><PlotGallery refdes={sensor.refdes} /></details>}
      {pi.map(r => <FileBrowser key={r.endpointId ?? r.url} route={r} />)}
    </section>
  );
}
