import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RegionNav from "./RegionNav.jsx";
import { bundleFixture } from "../test/fixtures.js";

describe("RegionNav", () => {
  it("lists regions with located sensor counts and selects", () => {
    const b = bundleFixture(), onSelect = vi.fn();
    render(<RegionNav regions={b.regions} sensors={b.sensors} active="overview" onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: /Full array\s*5/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: /Axial Seamount\s*4/ }));
    expect(onSelect).toHaveBeenCalledWith("axial");
    expect(screen.queryByRole("button", { name: /Unplaced/ })).toBeNull();   // no handler, no entry
  });
  it("has an Unplaced sensors entry with its count that opens the list", () => {
    const b = bundleFixture(), onUnplaced = vi.fn();
    const { rerender } = render(<RegionNav regions={b.regions} sensors={b.sensors} active="overview" onSelect={() => {}}
      unplaced={b.unplaced.length} onUnplaced={onUnplaced} />);
    const entry = screen.getByRole("button", { name: /^Unplaced sensors\s*1$/ });
    expect(entry).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(entry);
    expect(onUnplaced).toHaveBeenCalled();
    rerender(<RegionNav regions={b.regions} sensors={b.sensors} active="overview" onSelect={() => {}} unplaced={0} onUnplaced={onUnplaced} />);
    expect(screen.queryByRole("button", { name: /Unplaced/ })).toBeNull();
  });
});
