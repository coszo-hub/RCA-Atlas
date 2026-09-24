import { describe, expect, it, vi } from "vitest";
import { OverlayLayer } from "./OverlayLayer.js";
import { bundleFixture } from "../test/fixtures.js";

// A stand-in for AtlasScene with just what the overlay reads: flat ground at `ground` metres, camera 10 km west of Axial Base.
function fakeScene(ground = -9000) {
  const sc = {
    renderer: { domElement: document.createElement("canvas") },
    frame: { dist: 10, regionMode: false, e: 0.003, flat: 0 },
    camera: { position: { toArray: () => [-210, -7, -74] } },
    elevAt: () => ground, yFor: () => 0, project: () => [100, 100, 0.5], cableLines: [],
  };
  return sc;
}

function setup(ground) {
  const b = bundleFixture();
  const twin = { ...b.sites[0], id: "axial-seamount-base-2", label: "Axial Base · AXBA1", sensorIds: ["base-ctd"], column: [] };
  const bundle = { ...b, sites: [...b.sites, twin] };
  const container = document.createElement("div"), scene = fakeScene(ground);
  const h = { onSiteHover: vi.fn(), onSiteClick: vi.fn(), onCableHover: vi.fn() };
  const layer = new OverlayLayer(container, bundle, scene, h);
  return { container, scene, h, layer };
}

describe("OverlayLayer", () => {
  it("sites that share a name get distinct button names from their labels", () => {
    const { container } = setup();
    const names = [...container.querySelectorAll('[role="button"]')].map(d => d.getAttribute("aria-label"));
    expect(names).toContain("Axial Base, 3 sensors");
    expect(names).toContain("Axial Base · AXBA1, 1 sensor");
    expect(new Set(names).size).toBe(names.length);
  });
  it("Enter and Space open a site; Space does not scroll the page", () => {
    const { container, h } = setup();
    const btn = container.querySelector('[aria-label="Axial Base, 3 sensors"]');
    const space = new KeyboardEvent("keydown", { key: " ", cancelable: true });
    btn.dispatchEvent(space);
    btn.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", cancelable: true }));
    expect(h.onSiteClick).toHaveBeenCalledTimes(2);
    expect(space.defaultPrevented).toBe(true);
  });
  it("the cable card clears when the pointer leaves the map or a drag starts", () => {
    const { scene, h } = setup();
    scene.renderer.domElement.dispatchEvent(new Event("pointerleave"));
    scene.renderer.domElement.dispatchEvent(new Event("pointerdown"));
    expect(h.onCableHover.mock.calls).toEqual([[null, null], [null, null]]);
  });
  it("a hovered site that becomes hidden behind terrain drops its hover card", () => {
    const { container, scene, h, layer } = setup(-9000);
    const btn = container.querySelector('[aria-label="Axial Base, 3 sensors"]');
    btn.dispatchEvent(new MouseEvent("mouseenter"));
    layer.update();
    expect(h.onSiteHover).toHaveBeenCalledTimes(1);
    scene.elevAt = () => 0;   // the ground rises above the sight line
    layer.update();
    expect(h.onSiteHover).toHaveBeenLastCalledWith(expect.objectContaining({ id: "axial-seamount-base" }), null);
  });
});
