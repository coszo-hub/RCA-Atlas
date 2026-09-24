import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import UnplacedPanel from "./UnplacedPanel.jsx";
import SensorDetail from "./SensorDetail.jsx";
import { bundleFixture } from "../test/fixtures.js";

vi.mock("./live/LiveData.jsx", () => ({ default: () => <section className="live-data" /> }));
const b = bundleFixture();

describe("UnplacedPanel", () => {
  it("lists the unplaced sensors and opens one", () => {
    const onSensor = vi.fn();
    render(<UnplacedPanel bundle={b} onClose={() => {}} onSensor={onSensor} />);
    expect(screen.getByRole("complementary", { name: "Unplaced sensors" })).toBeInTheDocument();
    expect(screen.getByText("1 sensor · no recorded position")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^ASHES PI mass spectrometer, Status unknown, no recorded position$/ }));
    expect(onSensor).toHaveBeenCalledWith("pi-massp");
  });
  it("shows a sensor's detail without a site; back and Escape return to the list, a second Escape closes", () => {
    const onClose = vi.fn(), onBack = vi.fn();
    const detail = <SensorDetail sensor={b.sensorById["pi-massp"]} bundle={b} onBack={onBack} backLabel="Unplaced sensors" />;
    const { rerender } = render(<UnplacedPanel bundle={b} onClose={onClose} onBack={onBack} onSensor={() => {}}>{detail}</UnplacedPanel>);
    expect(screen.getByRole("heading", { name: "ASHES PI mass spectrometer" })).toBeInTheDocument();
    expect(screen.getByText(/No recorded position, so it is not drawn on the map/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← Unplaced sensors" }));
    expect(onBack).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onBack).toHaveBeenCalledTimes(2); expect(onClose).not.toHaveBeenCalled();
    rerender(<UnplacedPanel bundle={b} onClose={onClose} onBack={onBack} onSensor={() => {}} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
