import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LiveData from "./LiveData.jsx";
import { SCPR_CSV } from "../../test/fixtures/scpr.js";

vi.mock("./Chart.jsx", () => ({
  default: ({ lines, unit }) => <div data-testid="chart">{lines.series.map(s => s.label).join("+")} {lines.count} rows {unit}</div>,
}));
afterEach(() => vi.unstubAllGlobals());

const CSV_URL = "https://raw.githubusercontent.com/Axial-Seamount/self-calibrating-pressure/main/SCPR-data-collection/timeseries/scpr_pressure_hourly.csv";
const scpr = {
  id: "SCPRAAA301", refdes: "RS03CCAL-MJ03F-09-SCPRAA301", access: [
    { kind: "scpr_hourly", label: "SCPR hourly pressure and uplift (GitHub)", csvUrl: CSV_URL, how: "",
      url: "https://github.com/Axial-Seamount/self-calibrating-pressure/blob/main/SCPR-data-collection/timeseries/scpr_pressure_hourly.csv" },
    { kind: "ooi_explorer", label: "OOI Data Explorer", url: "https://dataexplorer.oceanobservatories.org/", how: "" },
  ],
};

describe("SCPR hourly series", () => {
  it("fetches the CSV from GitHub and plots both gauges' uplift over the full record", async () => {
    const f = vi.fn(async () => ({ ok: true, status: 200, text: async () => SCPR_CSV }));
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={scpr} />);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("PARO1+PARO2 4 rows m"));
    expect(f).toHaveBeenCalledWith(CSV_URL, expect.anything());
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("uplift");
    expect(screen.getByText(/hourly means to Nov 13, 2026, seafloor uplift to Dec 1, 2025 · file regenerated Nov 14, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/after the last calibration \(Feb 5, 2026\) is extrapolated/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CSV on GitHub" })).toHaveAttribute("href", scpr.access[0].url);
  });
  it("switches measurement and range without fetching again", async () => {
    const f = vi.fn(async () => ({ ok: true, status: 200, text: async () => SCPR_CSV }));
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={scpr} />);
    await screen.findByTestId("chart");
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "raw" } });
    expect(screen.getByTestId("chart")).toHaveTextContent("4 rows kPa");
    fireEvent.click(screen.getByRole("button", { name: "30d" }));
    expect(screen.getByTestId("chart")).toHaveTextContent("2 rows kPa");
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "uplift" } });
    expect(screen.getByText("No seafloor uplift values in this range. The newest is from Dec 1, 2025.")).toBeInTheDocument();
    expect(f).toHaveBeenCalledTimes(1);
  });
  it("a GitHub failure says so and retries", async () => {
    const f = vi.fn(async () => ({ ok: false, status: 503 }));
    vi.stubGlobal("fetch", f);
    render(<LiveData sensor={scpr} />);
    await waitFor(() => expect(screen.getByText(/GitHub: the SCPR file returned HTTP 503/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(f).toHaveBeenCalledTimes(2));
  });
});
