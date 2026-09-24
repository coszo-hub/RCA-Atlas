export function snippetFor(route, sensor, now = new Date()) {
  if (route.kind === "erddap") {
    return { label: "Python (erddapy)", code:
`from erddapy import ERDDAP

e = ERDDAP(server="https://erddap.dataexplorer.oceanobservatories.org/erddap", protocol="tabledap")
e.dataset_id = "${route.datasetId}"
e.constraints = {"time>=": "now-7days"}
df = e.to_pandas()   # ${sensor.name}` };
  }
  if (route.kind === "earthscope") {
    const cha = route.channel ?? "HHZ";
    // Literal UTC times for the hour before the snippet was shown: portable, no shell date arithmetic.
    const iso = d => d.toISOString().slice(0, 19), end = new Date(Math.floor(now.getTime() / 1000) * 1000);
    return { label: "FDSN dataselect (MiniSEED, the last hour, UTC)", code:
`curl -o ${route.network}.${route.station}.mseed "https://service.earthscope.org/fdsnws/dataselect/1/query?net=${route.network}&sta=${route.station}&cha=${cha}&loc=--&starttime=${iso(new Date(end.getTime() - 3600e3))}&endtime=${iso(end)}"` };
  }
  if (route.kind === "pi_portal") return { label: "List files", code: `curl -s "${route.url}"` };
  return null;
}
