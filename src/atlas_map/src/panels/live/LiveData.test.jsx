import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LiveData from "./LiveData.jsx";
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
  it("seismic sensors get a waveform", async () => {
    vi.stubGlobal("fetch", routes([["/api/waveform/OO.AXCC1", { points: [[1, 5], [2, 6], [3, 4]], rate: 200, channel: "HHZ", message: null }]]));
    render(<LiveData sensor={b.sensorById.axcc1} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("3 points"));
    expect(screen.getByText(/HHZ · 200 samples\/s/)).toBeInTheDocument();
  });
});
