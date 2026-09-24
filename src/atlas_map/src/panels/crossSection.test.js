import { describe, expect, it } from "vitest";
import { depthScale, layout, profile } from "./crossSection.js";
import { bundleFixture } from "../test/fixtures.js";

const b = bundleFixture();
const order = { seismic: 0, chemistry: 1 };

describe("depthScale", () => {
  it("piecewise for deep sites with a water column, with a break", () => {
    const s = depthScale(b.siteById["axial-seamount-base"], 300);
    expect(s.y(0)).toBe(0);
    expect(s.y(300)).toBeCloseTo(90);
    expect(s.y(2614 + 50)).toBeCloseTo(300, 0);
    expect(s.breakAt).not.toBeNull();
  });
  it("linear for a shallow site", () => {
    const s = depthScale(b.siteById["oregon-shelf"], 300);
    expect(s.breakAt).toBeNull();
    expect(s.y(65)).toBeCloseTo(150, 0);   // seafloor 80 + 50 margin = 130 m over 300 px
  });
  it("monotonic", () => {
    const s = depthScale(b.siteById["axial-seamount-base"], 300);
    let prev = -1;
    for (let d = 0; d <= 2664; d += 7) { const y = s.y(d); expect(y).toBeGreaterThanOrEqual(prev); prev = y; }
  });
});

describe("layout", () => {
  it("moving sensors get a range, seafloor sensors sit at depth, fanned in family order", () => {
    const site = b.siteById["axial-seamount-base"];
    const pts = layout(site, site.sensorIds.map(id => b.sensorById[id]), order, 400, 300);
    const sp = pts.find(p => p.id === "sp-ctd"), base = pts.find(p => p.id === "base-ctd");
    const s = depthScale(site, 300);
    expect(sp.y).toBeCloseTo(s.y(5)); expect(sp.y2).toBeCloseTo(s.y(200));
    expect(base.y).toBeCloseTo(s.y(2607)); expect(base.y2).toBeUndefined();
    expect(Math.min(...pts.map(p => p.x))).toBeGreaterThanOrEqual(80);
    expect(Math.max(...pts.map(p => p.x))).toBeLessThanOrEqual(320);
  });
  it("sensor without depth sits on the seafloor", () => {
    const site = b.siteById["oregon-shelf"];
    const [p] = layout(site, [b.sensorById["shelf-bpr"]], order, 400, 300);
    expect(p.y).toBeCloseTo(depthScale(site, 300).y(80));
  });
});

describe("profile", () => {
  it("samples 2 km east-west, depth positive", () => {
    const pts = profile(b.siteById["oregon-shelf"], () => -80, 5);
    expect(pts).toHaveLength(5);
    expect(pts[0]).toEqual({ x: 0, depth: 80 });
    expect(pts[4].x).toBe(1);
  });
});
