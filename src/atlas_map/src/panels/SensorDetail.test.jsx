import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SensorDetail from "./SensorDetail.jsx";
import { bundleFixture } from "../test/fixtures.js";

// These tests cover status and access routes; the live views have their own tests (live/LiveData.test.jsx)
// and would otherwise share these single-reply fetch stubs.
vi.mock("./live/LiveData.jsx", () => ({ default: () => <section className="live-data" /> }));
const b = bundleFixture();
afterEach(() => vi.unstubAllGlobals());

describe("SensorDetail", () => {
  it("shows live status from the gateway", async () => {
    vi.stubGlobal("fetch", vi.fn(async url => ({ ok: true, status: 200, json: async () =>
      String(url).includes("/status/") ? { refdes: "R", status: "OPERATIONAL", data: { code: "OK", checkedAt: "2026-09-23T11:58:00Z" }, evidenceMode: "live", source: "Nereus" }
        : { variables: [], coverage: {} } })));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Operating · checked live/)).toBeInTheDocument());
  });
  it("falls back to the snapshot when the gateway is down", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText("Live data unavailable. Showing snapshot from Sep 19, 2026.")).toBeInTheDocument());
  });
  it("uses recent EarthScope waveform availability for station-based seismometers, not a Nereus status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ recording: true, station: "OO.AXCC1", channel: "HHZ" }) })));
    render(<SensorDetail sensor={b.sensorById["axcc1"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText("Waveform available · EarthScope checked live")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/waveform/OO.AXCC1/health"), expect.anything());
  });
  it("lists every access route with its how-to", () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) })));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    expect(screen.getByRole("link", { name: /OOI ERDDAP/ })).toHaveAttribute("href", expect.stringContaining("erddap"));
    expect(screen.getByText("Download CSV.")).toBeInTheDocument();
  });
  it("no live feed for planned sensors", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SensorDetail sensor={b.sensorById["shelf-bpr"]} bundle={b} onBack={() => {}} />);
    expect(screen.getByText(/No live feed/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("names the failed upstream source and retries", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(async () => (++calls === 1
      ? { ok: false, status: 504, json: async () => ({ error: { source: "Nereus", message: "Nereus did not answer in time." } }) }
      : { ok: true, status: 200, json: async () => ({ refdes: "R", status: "OPERATIONAL", data: null, evidenceMode: "live", source: "Nereus" }) })));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Nereus failed: Nereus did not answer in time\./)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText(/Operating · checked live/)).toBeInTheDocument());
  });
  const statusReply = (status, body) => vi.fn(async () => ({ ok: status < 400, status, json: async () => body }));
  it("404 from Nereus: not tracked live", async () => {
    vi.stubGlobal("fetch", statusReply(404, { error: { source: "Nereus", message: "Nereus has no record of this sensor." } }));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText(/not tracked live by Nereus/)).toBeInTheDocument());
  });
  it("404 from the atlas gateway: shows its message, not the Nereus wording", async () => {
    vi.stubGlobal("fetch", statusReply(404, { error: { source: "atlas", message: "unknown sensor" } }));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText(/atlas: unknown sensor/)).toBeInTheDocument());
    expect(screen.queryByText(/not tracked live by Nereus/)).toBeNull();
  });
  it("live status without a status word reads Status unknown", async () => {
    vi.stubGlobal("fetch", statusReply(200, { refdes: "R", status: null, data: null, evidenceMode: "live", source: "Nereus" }));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText(/^Status unknown · checked live/)).toBeInTheDocument());
  });
  it("a Nereus snapshot answer says so and does not claim a live check", async () => {
    vi.stubGlobal("fetch", statusReply(200, { refdes: "R", status: "OPERATIONAL", data: null, evidenceMode: "snapshot", source: "Nereus" }));
    render(<SensorDetail sensor={b.sensorById["base-ctd"]} bundle={b} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByText("Operating · from Nereus snapshot")).toBeInTheDocument());
    expect(screen.queryByText(/checked live/)).toBeNull();
  });
  it("works without a site: the back control names where it returns and calls back", () => {
    vi.stubGlobal("fetch", vi.fn());
    const onBack = vi.fn();
    render(<SensorDetail sensor={b.sensorById["pi-massp"]} bundle={b} onBack={onBack} backLabel="Unplaced sensors" />);
    fireEvent.click(screen.getByRole("button", { name: "← Unplaced sensors" }));
    expect(onBack).toHaveBeenCalled();
    expect(screen.getByText(/No live feed/)).toBeInTheDocument();
  });
  it("without a site or a back label, the back control reads Back", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SensorDetail sensor={b.sensorById["pi-massp"]} bundle={b} onBack={() => {}} />);
    expect(screen.getByRole("button", { name: "← Back" })).toBeInTheDocument();
  });
});
