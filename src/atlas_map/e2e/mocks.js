// Match on the path prefix: a "**/api/**" glob would also catch Vite's own /src/api/*.js modules.
export async function mockGateway(page, { down = false } = {}) {
  await page.route(u => u.pathname.startsWith("/api/"), async route => {
    const url = new URL(route.request().url()), p = url.pathname.replace(/^\/api/, "");
    if (down) return route.abort("connectionrefused");
    const json = body => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (p.startsWith("/status/")) return json({ refdes: p.split("/")[2], status: "OPERATIONAL", data: { code: "OK", checkedAt: new Date().toISOString(), delay: 30 }, evidenceMode: "live", source: "Nereus" });
    if (p.endsWith("/variables")) return json({ variables: [{ name: "sea_water_temperature", units: "degree_Celsius", longName: "Water Temperature" }], coverage: { start: "2014-10-02T20:42:00Z", end: new Date().toISOString() } });
    if (p.startsWith("/series/")) {
      const t0 = Date.now() - 864e5;
      return json({ points: Array.from({ length: 1440 }, (_, i) => [t0 + i * 60000, 7.3 + 0.05 * Math.sin(i / 90)]), units: "degree_Celsius", rawCount: 1440, downloadUrl: "https://erddap.dataexplorer.oceanobservatories.org/erddap/tabledap/x.csv", message: null });
    }
    if (p.startsWith("/waveform/")) return json({ points: Array.from({ length: 2000 }, (_, i) => [Date.now() - 6e5 + i * 300, Math.sin(i / 7) * 400]), rate: 200, channel: "HHZ", message: null });
    if (p.startsWith("/plots/")) return json({ refdes: "x", plots: [] });
    if (p === "/chat") return json({ answer: "Axial Base has a seafloor package and two profilers.", model: "m", citations: [{ id: "1", title: "OOI Axial Base", url: "https://oceanobservatories.org" }] });
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: { source: "atlas", message: "not mocked" } }) });
  });
}
