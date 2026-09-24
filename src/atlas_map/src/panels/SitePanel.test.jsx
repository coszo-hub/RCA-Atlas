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
    expect(mark.closest("g[stroke]").getAttribute("stroke")).toBe("#d95926");
  });
});
