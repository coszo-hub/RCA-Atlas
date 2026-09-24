import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FamilyFilter from "./FamilyFilter.jsx";
import { bundleFixture } from "../test/fixtures.js";

beforeEach(() => localStorage.clear());

describe("FamilyFilter", () => {
  const b = bundleFixture();
  it("click focuses one, shift-click adds, click again clears", () => {
    const onChange = vi.fn();
    const { rerender } = render(<FamilyFilter families={b.families} sensors={b.sensors} focus={new Set()} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Seismic/ }));
    expect([...onChange.mock.calls[0][0]]).toEqual(["seismic"]);
    rerender(<FamilyFilter families={b.families} sensors={b.sensors} focus={new Set(["seismic"])} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Water properties/ }), { shiftKey: true });
    expect([...onChange.mock.calls[1][0]].sort()).toEqual(["chemistry", "seismic"]);
    fireEvent.click(screen.getByRole("button", { name: /Seismic/ }));
    expect([...onChange.mock.calls[2][0]]).toEqual([]);
  });
  it("counts located sensors per family", () => {
    render(<FamilyFilter families={b.families} sensors={b.sensors} focus={new Set()} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /Seismic\s*2/ })).toBeInTheDocument();
  });
  it("hides families with no located sensors", () => {
    const families = [...b.families, { key: "fiber", label: "Fiber-optic", color: "#d9d6cc", glyph: "bar" }];
    const sensors = [...b.sensors, { ...b.sensors[0], id: "das", family: "fiber", lat: null, lon: null }];
    render(<FamilyFilter families={families} sensors={sensors} focus={new Set()} onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /Fiber-optic/ })).toBeNull();
    expect(screen.getAllByRole("button").filter(el => el.hasAttribute("aria-pressed"))).toHaveLength(2);
  });
  it("minimizes to a tab that keeps saying a filter is on, and restores", () => {
    const { unmount } = render(<FamilyFilter families={b.families} sensors={b.sensors} focus={new Set(["seismic"])} onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Minimize sensor families" }));
    expect(screen.queryByRole("button", { name: /Seismic/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Sensor families\s*1 selected/ })).toHaveAttribute("aria-expanded", "false");
    unmount();   // remembered across visits
    render(<FamilyFilter families={b.families} sensors={b.sensors} focus={new Set()} onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Sensor families" }));
    expect(screen.getByRole("button", { name: /Seismic/ })).toBeInTheDocument();
  });
});
