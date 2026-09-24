import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Tooltip from "./Tooltip.jsx";
import { bundleFixture } from "../test/fixtures.js";

describe("Tooltip", () => {
  const b = bundleFixture();
  it("site: platforms, water column, sensors with depth ranges", () => {
    const { container } = render(<Tooltip bundle={b} hover={{ kind: "site", item: b.siteById["axial-seamount-base"], x: 10, y: 10 }} />);
    expect(container.querySelector(".t-name")).toHaveTextContent("Axial Seamount Base");
    expect(container.querySelector(".t-col")).toHaveTextContent("Shallow profiler 5–200 m");
    expect(screen.getByText("Axial Seamount Profiler")).toHaveClass("t-head");
    expect(screen.getByText(/1 more sensor has no recorded position/)).toBeInTheDocument();
  });
  it("node: PN5A description", () => {
    render(<Tooltip bundle={b} hover={{ kind: "node", item: b.cable.nodes[0], x: 0, y: 0 }} />);
    expect(screen.getByText(/placeholder node/i)).toBeInTheDocument();
  });
  it("cable: route and accuracy", () => {
    render(<Tooltip bundle={b} hover={{ kind: "cable", item: b.cable.lines[0], x: 0, y: 0 }} />);
    expect(screen.getByText("North backbone")).toBeInTheDocument();
    expect(screen.getByText(/Charted route/)).toBeInTheDocument();
  });
  it("cable: lists fiber-optic experiments that have no recorded position", () => {
    const b2 = { ...b, sensors: [...b.sensors, { ...b.sensors[0], id: "das", name: "2024 DAS experiment", family: "fiber", lat: null, lon: null }] };
    render(<Tooltip bundle={b2} hover={{ kind: "cable", item: b.cable.lines[0], x: 0, y: 0 }} />);
    expect(screen.getByText(/2024 DAS experiment/)).toBeInTheDocument();
  });
  it("opens above the cursor when the card would run off the bottom", () => {
    const desc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get() { return 400; } });
    try {
      const y = innerHeight - 100;
      const { container } = render(<Tooltip bundle={b} hover={{ kind: "site", item: b.siteById["axial-seamount-base"], x: 10, y }} />);
      expect(container.querySelector(".tip").style.top).toBe(`${y - 18 - 400}px`);
    } finally {
      if (desc) Object.defineProperty(HTMLElement.prototype, "offsetHeight", desc); else delete HTMLElement.prototype.offsetHeight;
    }
  });
  it("renders nothing without hover", () => {
    const { container } = render(<Tooltip bundle={b} hover={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
