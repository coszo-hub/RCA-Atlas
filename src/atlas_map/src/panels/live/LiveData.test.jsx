import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LiveData from "./LiveData.jsx";
import PlotGallery from "./PlotGallery.jsx";
import { bundleFixture } from "../../test/fixtures.js";

vi.mock("./Chart.jsx", () => ({ default: ({ points, unit }) => <div data-testid="chart">{points.length} points {unit}</div> }));
const b = bundleFixture();
afterEach(() => vi.unstubAllGlobals());

const routes = handlers => vi.fn(async url => {
  const u = String(url);
  for (const [prefix, body, status = 200] of handlers) if (u.startsWith(prefix)) return { ok: status < 400, status, json: async () => body };
  return { ok: false, status: 404, json: async () => ({ error: { source: "atlas", message: "no" } }) };
});

describe("LiveData", () => {
  it("series: variables, then 24h of points", async () => {
    vi.stubGlobal("fetch", routes([
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [{ name: "sea_water_temperature", units: "degree_Celsius", longName: "Water Temperature" }], coverage: { end: "2026-09-23T10:48:00Z" } }],
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [[1, 7.3], [2, 7.4]], units: "degree_Celsius", rawCount: 2, downloadUrl: "https://erddap.dataexplorer.oceanobservatories.org/x.csv", message: null }],
    ]));
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("2 points degree_Celsius"));
    expect(screen.getByRole("link", { name: /Download this range/ })).toHaveAttribute("href", "https://erddap.dataexplorer.oceanobservatories.org/x.csv");
  });
  it("empty range shows the message and the dataset coverage", async () => {
    vi.stubGlobal("fetch", routes([
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [{ name: "t", units: "C", longName: "T" }], coverage: { start: "2014-10-02T20:42:00Z", end: "2026-09-01T00:00:00Z" } }],
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [], units: null, rawCount: 0, downloadUrl: "x", message: "No readings in this range." }],
    ]));
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByText(/No readings in this range/)).toBeInTheDocument());
    expect(screen.getByText(/data runs to Sep 1, 2026/)).toBeInTheDocument();
  });
  it("an empty preset moves to the measurement's newest reading when it stopped before the dataset did", async () => {
    const fetchMock = vi.fn(async url => {
      const u = String(url);
      if (u.includes("/variables")) return { ok: true, status: 200, json: async () => ({ variables: [{ name: "t", units: "C", longName: "T" }], coverage: { end: "2026-09-23T10:48:00Z" } }) };
      const end = new URL(u, "http://x").searchParams.get("end");
      const body = end === "2026-09-18T06:41:00Z"
        ? { points: [[1, 7.3], [2, 7.4], [3, 7.5]], units: "C", rawCount: 3, downloadUrl: "x", latest: null, message: null }
        : { points: [], units: null, rawCount: 0, downloadUrl: "x", latest: "2026-09-18T06:41:00Z", message: "No readings in this range." };
      return { ok: true, status: 200, json: async () => body };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("3 points C"));
    expect(screen.getByText(/newest reading is from Sep 18, 2026; the 24h window ends there/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([u]) => !String(u).includes("/variables"))).toHaveLength(2);
  });
  it("custom range longer than 31 days is blocked without a request", async () => {
    const f = routes([["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [{ name: "t", units: "C" }], coverage: {} }],
                      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [], rawCount: 0, message: null }]]);
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => screen.getByRole("button", { name: "Custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-07-01T00:00" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-01T00:00" } });
    const before = f.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByText(/31 days/)).toBeInTheDocument();
    expect(f.mock.calls.length).toBe(before);
  });
  it("upstream failure names the source and retries", async () => {
    const f = routes([["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { error: { source: "ERDDAP", message: "ERDDAP returned HTTP 500" } }, 502]]);
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByText(/ERDDAP returned HTTP 500/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(f.mock.calls.length).toBeGreaterThan(1));
  });
  it("QA/QC plots under the series load only once the details is opened", async () => {
    const f = routes([
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [{ name: "t", units: "C" }], coverage: {} }],
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [[1, 7.3]], units: "C", rawCount: 1, downloadUrl: "x", message: null }],
      ["/api/plots/RS03AXBS-LJ03A-12-CTDPFB301", { refdes: "RS03AXBS-LJ03A-12-CTDPFB301", variables: [], plots: [], spans: [], total: 0 }],
    ]);
    vi.stubGlobal("fetch", f);
    const base = b.sensorById["base-ctd"];
    const sensor = { ...base, access: [...base.access, { kind: "qaqc", label: "RCA QA/QC plots", url: "https://qaqc.ooirsn.uw.edu/x", how: "" }] };
    const plotCalls = () => f.mock.calls.filter(([u]) => String(u).startsWith("/api/plots/")).length;
    const { container } = render(<LiveData sensor={sensor} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toBeInTheDocument());
    expect(plotCalls()).toBe(0);
    expect(screen.queryByText(/Loading recent plots/)).toBeNull();
    const details = container.querySelector("details");
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await waitFor(() => expect(screen.getByText(/no recent plots for this sensor/)).toBeInTheDocument());
    expect(plotCalls()).toBe(1);
  });
  it("a seismometer offers its OOI OBS QA/QC plots below the waveform", async () => {
    const obs = "RS03CCAL-MJ03F-06-OBSBBA301";
    const f = routes([
      ["/api/waveform/", { error: { source: "EarthScope", message: "down" } }, 502],
      [`/api/plots/${obs}`, { refdes: obs, variables: ["groundvel_accel"], variable: "groundvel_accel", spans: ["day"], span: "day", total: 3,
        plots: [{ variable: "groundvel_accel", timeSpan: "day", overlay: "none", dataRange: "full", depth: "", url: "https://q/o.png" }] }],
    ]);
    vi.stubGlobal("fetch", f);
    const base = b.sensorById["axcc1"];
    const sensor = { ...base, access: [...base.access, { kind: "qaqc", label: "RCA QA/QC plots", refdes: obs, url: "https://ec2.qaqc.ooi-rca.net/", how: "" }] };
    const { container } = render(<LiveData sensor={sensor} />);
    const details = container.querySelector("details");
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "https://q/o.png"));
    expect(f.mock.calls.some(([u]) => String(u).startsWith(`/api/plots/${obs}`))).toBe(true);
  });
  it("QA/QC plots: every variable is listed, and a span button asks for that span's plots", async () => {
    const body = (variable, span) => ({ refdes: "R", variables: ["beam1", "temperature"], variable, spans: ["day", "week"], span, total: 735,
      plots: [{ variable, timeSpan: span, overlay: "none", dataRange: "full", depth: "", url: `https://q/${variable}_${span}.png` }] });
    const f = vi.fn(async url => {
      const u = new URL(String(url), "http://x");
      return { ok: true, status: 200, json: async () => body(u.searchParams.get("variable") ?? "beam1", u.searchParams.get("span") ?? "day") };
    });
    vi.stubGlobal("fetch", f);
    render(<PlotGallery refdes="R" />);
    expect(await screen.findByRole("option", { name: "temperature" })).toBeInTheDocument();
    expect(screen.getByText("735 QA/QC plots for this sensor across 2 variables")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Week" }));
    await waitFor(() => expect(screen.getByRole("img")).toHaveAttribute("src", "https://q/beam1_week.png"));
    expect(f.mock.calls.some(([u]) => String(u).includes("span=week"))).toBe(true);
  });
  it("defaults to sea water temperature when the dataset has it", async () => {
    const f = routes([
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [
        { name: "sea_water_pressure", units: "dbar", longName: "Pressure" },
        { name: "sea_water_temperature", units: "degree_Celsius", longName: "Water Temperature" }], coverage: {} }],
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [[1, 7.3]], units: "degree_Celsius", rawCount: 1, downloadUrl: "x", message: null }],
    ]);
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toBeInTheDocument());
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("sea_water_temperature");
    const seriesUrl = f.mock.calls.map(([u]) => String(u)).find(u => u.startsWith("/api/series/RS03AXBS-LJ03A-12-CTDPFB301?"));
    expect(seriesUrl).toContain("var=sea_water_temperature");
  });
  it("otherwise defaults to the first variable", async () => {
    const f = routes([
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301/variables", { variables: [
        { name: "sea_water_pressure", units: "dbar", longName: "Pressure" }, { name: "salinity", units: "1", longName: "Salinity" }], coverage: {} }],
      ["/api/series/RS03AXBS-LJ03A-12-CTDPFB301?", { points: [[1, 7.3]], units: "dbar", rawCount: 1, downloadUrl: "x", message: null }],
    ]);
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={b.sensorById["base-ctd"]} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toBeInTheDocument());
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("sea_water_pressure");
  });
  it("seismic sensors get a waveform", async () => {
    vi.stubGlobal("fetch", routes([["/api/waveform/OO.AXCC1", { points: [[1, 5], [2, 6], [3, 4]], rate: 200, channel: "HHZ", message: null }]]));
    render(<LiveData sensor={b.sensorById.axcc1} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("3 points"));
    expect(screen.getByText(/HHZ · 200 samples\/s/)).toBeInTheDocument();
  });
  it("the earthquake filter asks the gateway for 3-20 Hz and shows the band, or why it could not apply it", async () => {
    const fetchMock = vi.fn(async url => {
      const filtered = String(url).includes("bandpass=3-20");
      return { ok: true, status: 200, json: async () => (filtered
        ? { points: [[1, 0.5], [2, -0.4]], rate: 200, channel: "HHZ", bandpass: { low: 3, high: 20 }, filterNote: null, message: null }
        : { points: [[1, 5], [2, 6], [3, 4]], rate: 200, channel: "HHZ", bandpass: null, filterNote: null, message: null }) };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveData sensor={b.sensorById.axcc1} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("3 points"));
    fireEvent.click(screen.getByRole("button", { name: "Earthquakes 3–20 Hz" }));
    await waitFor(() => expect(screen.getByText(/bandpass 3–20 Hz/)).toBeInTheDocument());
    expect(screen.getByTestId("chart")).toHaveTextContent("2 points counts (filtered)");
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("bandpass=3-20"))).toBe(true);
  });
  it("a channel too slow for the band says so", async () => {
    vi.stubGlobal("fetch", routes([["/api/waveform/OO.AXCC1", { points: [[1, 5], [2, 6]], rate: 8, channel: "MHZ", requestedChannel: "HHZ", bandpass: null,
      filterNote: "A 3–20 Hz bandpass needs 50 samples/s or more; MHZ has 8, so this is unfiltered.", message: null }]]));
    render(<LiveData sensor={b.sensorById.axcc1} />);
    fireEvent.click(await screen.findByRole("button", { name: "Earthquakes 3–20 Hz" }));
    await waitFor(() => expect(screen.getByText(/MHZ has 8, so this is unfiltered/)).toBeInTheDocument());
  });
});
