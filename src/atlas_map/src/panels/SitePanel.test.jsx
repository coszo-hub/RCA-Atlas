import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SitePanel from "./SitePanel.jsx";
import { bundleFixture } from "../test/fixtures.js";

describe("SitePanel", () => {
  const b = bundleFixture();
  it("lists sensors by family, flags unlocated ones, and opens a sensor", () => {
    const onSensor = vi.fn();
    render(<SitePanel site={b.siteById["axial-seamount-base"]} bundle={b} elevAt={() => -2614} onClose={() => {}} onSensor={onSensor} />);
    expect(screen.getByRole("heading", { name: "Axial Seamount Base" })).toBeInTheDocument();
    expect(screen.getByText("Axial Base bottom pressure and tilt")).toBeInTheDocument();
    expect(screen.getByText(/location not recorded/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /sp-ctd/ }));
    expect(onSensor).toHaveBeenCalledWith("sp-ctd");
  });
  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<SitePanel site={b.siteById["oregon-shelf"]} bundle={b} elevAt={() => -80} onClose={onClose} onSensor={() => {}} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("Escape in sensor detail goes back to the site; a second Escape closes", () => {
    const onClose = vi.fn(), onBack = vi.fn();
    const site = b.siteById["oregon-shelf"];
    const { rerender } = render(<SitePanel site={site} bundle={b} elevAt={() => -80} onClose={onClose} onBack={onBack} onSensor={() => {}}><p>detail</p></SitePanel>);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onBack).toHaveBeenCalledTimes(1); expect(onClose).not.toHaveBeenCalled();
    rerender(<SitePanel site={site} bundle={b} elevAt={() => -80} onClose={onClose} onBack={onBack} onSensor={() => {}} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1); expect(onBack).toHaveBeenCalledTimes(1);
  });
  it("Escape in a text field does not close the panel", () => {
    const onClose = vi.fn();
    const { container } = render(<SitePanel site={b.siteById["oregon-shelf"]} bundle={b} elevAt={() => -80} onClose={onClose} onSensor={() => {}}><input aria-label="q" /></SitePanel>);
    fireEvent.keyDown(container.querySelector("input"), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
  it("shows the unique site label so same-named sites are distinguishable", () => {
    render(<SitePanel site={b.siteById["axial-seamount-base"]} bundle={b} elevAt={() => -2614} onClose={() => {}} onSensor={() => {}} />);
    expect(screen.getByText("Axial Seamount · Axial Base")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Axial Base site" })).toBeInTheDocument();
  });
});

describe("DepthSection marks", () => {
  const b = bundleFixture();
  it("draw the family glyph, hollow for planned sensors", () => {
    const { container } = render(<SitePanel site={b.siteById["oregon-shelf"]} bundle={b} elevAt={() => -80} onClose={() => {}} onSensor={() => {}} />);
    const mark = container.querySelector(".depth-section .sensor polygon");   // seismic = triangle
    expect(mark).not.toBeNull();
    expect(mark.getAttribute("fill")).toBe("none");
    expect(mark.closest("g[stroke]").getAttribute("stroke")).toBe(b.familyByKey.seismic.color);
  });
});
