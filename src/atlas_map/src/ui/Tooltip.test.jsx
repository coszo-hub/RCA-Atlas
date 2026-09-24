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
  it("node: PN5A description, no sites nearby, position accuracy and source", () => {
    render(<Tooltip bundle={b} hover={{ kind: "node", item: b.cable.nodes[0], x: 0, y: 0 }} />);
    expect(screen.getByText(/placeholder node/i)).toBeInTheDocument();
    expect(screen.getByText("Catalogued sites within 30 km")).toBeInTheDocument();
    expect(screen.getByText("None.")).toBeInTheDocument();
    expect(screen.getByText(/^Position charted\. Source: OOI mariner safety notices/)).toBeInTheDocument();
  });
  it("node: lists catalogued sites within 30 km with their sensor counts, nearest first", () => {
    const pn3a = { code: "PN3A", name: "PN3A (Axial Base)", accuracy: "approximate", note: "Expect PN3A within ~1-2 km of MJ03A.",
      lon: -129.7367, lat: 45.8202, description: "Primary node: a seafloor hub." };
    const { container } = render(<Tooltip bundle={b} hover={{ kind: "node", item: pn3a, x: 0, y: 0 }} />);
    const rows = [...container.querySelectorAll(".t-site")].map(r => r.textContent);
    expect(rows).toEqual([expect.stringMatching(/^Axial Base3 sensors · 1\.\d km$/), expect.stringMatching(/^Axial Central Caldera1 sensor · 2\d km$/)]);
    expect(screen.getByText(/^Position approximate\. Source: no published node coordinates.*Expect PN3A within ~1-2 km of MJ03A\.$/)).toBeInTheDocument();
    expect(screen.queryByText("Oregon Shelf")).toBeNull();
  });
  it("node: a source named in the bundle wins", () => {
    render(<Tooltip bundle={b} hover={{ kind: "node", item: { ...b.cable.nodes[0], source: "OOI safety flyer PN3B-PC03A-PN5A" }, x: 0, y: 0 }} />);
    expect(screen.getByText(/Source: OOI safety flyer PN3B-PC03A-PN5A\./)).toBeInTheDocument();
  });
  it("site: lists at most 14 sensors; platform headings do not count", () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ ...b.sensorById["base-ctd"], id: `m${i}`, name: `Sensor ${i}`,
      location: i < 9 ? "Platform A" : "Platform B" }));
    const site = { ...b.siteById["axial-seamount-base"], sensorIds: many.map(m => m.id), parts: ["Platform A", "Platform B"], unlocatedIds: [] };
    const b2 = { ...b, sensorById: { ...b.sensorById, ...Object.fromEntries(many.map(m => [m.id, m])) } };
    const { container } = render(<Tooltip bundle={b2} hover={{ kind: "site", item: site, x: 0, y: 0 }} />);
    expect(container.querySelectorAll(".t-item")).toHaveLength(14);
    expect(container.querySelectorAll(".t-head")).toHaveLength(2);
    expect(screen.getByText("+6 more. Click to open the depth section.")).toBeInTheDocument();
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
  it("moving from a tall, lifted card to a short one puts the short card back below the cursor", () => {
    let h = 400;
    const desc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get() { return h; } });
    try {
      const y = innerHeight - 100;
      const { container, rerender } = render(<Tooltip bundle={b} hover={{ kind: "site", item: b.siteById["axial-seamount-base"], x: 10, y }} />);
      expect(container.querySelector(".tip").style.top).toBe(`${y - 18 - 400}px`);
      h = 50;
      rerender(<Tooltip bundle={b} hover={{ kind: "node", item: b.cable.nodes[0], x: 10, y }} />);
      expect(container.querySelector(".tip").style.top).toBe(`${Math.min(y + 18, innerHeight - 240)}px`);
    } finally {
      if (desc) Object.defineProperty(HTMLElement.prototype, "offsetHeight", desc); else delete HTMLElement.prototype.offsetHeight;
    }
  });
  it("site: singular sensor count", () => {
    const { container } = render(<Tooltip bundle={b} hover={{ kind: "site", item: b.siteById["oregon-shelf"], x: 0, y: 0 }} />);
    expect(container.querySelector(".t-sub").textContent).toMatch(/^1 sensor ·/);
  });
  it("renders nothing without hover", () => {
    const { container } = render(<Tooltip bundle={b} hover={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
