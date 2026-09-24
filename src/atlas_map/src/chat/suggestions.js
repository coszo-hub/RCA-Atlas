export function suggest({ site, sensor } = {}) {
  if (sensor) {
    const type = sensor.type.replaceAll("_", " ");
    return [`What does a ${type} measure?`, `What research has used ${sensor.name}?`, `How do I download data from ${sensor.name}?`];
  }
  if (site) {
    return [`What research has used data from ${site.name}?`, `What is measured at ${site.name}?`, `What happened at ${site.name} recently?`];
  }
  return ["What is COSZO?", "Which sites have the most sensors?", "Where can I download seismic data?"];
}
