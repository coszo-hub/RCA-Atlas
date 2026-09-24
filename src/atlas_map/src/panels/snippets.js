export function snippetFor(route, sensor) {
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
    return { label: "FDSN dataselect (MiniSEED, last hour)", code:
`curl -o ${route.network}.${route.station}.mseed "https://service.earthscope.org/fdsnws/dataselect/1/query?net=${route.network}&sta=${route.station}&cha=${cha}&loc=--&starttime=$(date -u -v-1H +%Y-%m-%dT%H:%M:%S)&endtime=$(date -u +%Y-%m-%dT%H:%M:%S)"` };
  }
  if (route.kind === "pi_portal") return { label: "List files", code: `curl -s "${route.url}"` };
  return null;
}
