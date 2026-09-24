import { describe, expect, it } from "vitest";
import { depthScale, layout, profile, profileDepthAt } from "./crossSection.js";
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

describe("layout on a sloped floor", () => {
  it("snaps seafloor sensors (no depth, or within 25 m of the floor) to the profile at their x", () => {
    const site = b.siteById["oregon-shelf"];
    const slope = lon => -(80 + (lon - site.lon) * 2000);   // floor deepens eastward, ~±25 m across 2 km
    const prof = profile(site, slope);
    const sensors = ["a", "b", "c", "d"].map(id => ({ ...b.sensorById["shelf-bpr"], id }))
      .concat([{ ...b.sensorById["shelf-bpr"], id: "e", depth: 70 }]);   // within 25 m: snaps too
    const pts = layout(site, sensors, order, 400, 300, prof);
    const s = depthScale(site, 300);
    const floorAt = fx => {   // piecewise-linear floor line in viewBox units
      const i = Math.min(prof.length - 2, Math.floor(fx * (prof.length - 1)));
      const t = fx * (prof.length - 1) - i;
      return s.y(Math.max(0, prof[i].depth + (prof[i + 1].depth - prof[i].depth) * t));
    };
    expect(new Set(pts.map(p => Math.round(p.y))).size).toBeGreaterThan(1);   // not all at the center depth
    for (const p of pts) expect(Math.abs(p.y - floorAt(p.x / 400))).toBeLessThan(1);
  });
  it("a recorded depth 33 m below the site floor (MJ03C-like) still snaps to the line", () => {
    const site = b.siteById["oregon-shelf"];
    const prof = profile(site, lon => -(80 + (lon - site.lon) * 2000));
    const deep = [{ ...b.sensorById["shelf-bpr"], id: "vent", depth: site.seafloor + 33 }];
    const [p] = layout(site, deep, order, 400, 300, prof);
    const s = depthScale(site, 300);
    expect(p.y).toBeCloseTo(s.y(profileDepthAt(prof, p.x / 400)), 5);
    expect(Math.abs(p.y - s.y(site.seafloor + 33))).toBeGreaterThan(1);   // not left at its recorded depth
  });
  it("a single depth shallower than seafloor - 60 m is in the water column and keeps it", () => {
    const site = b.siteById["axial-seamount-base"];
    const prof = profile(site, lon => -(2614 + (lon - site.lon) * 4000));
    const [p] = layout(site, [{ ...b.sensorById["base-ctd"], id: "moored", depth: 2614 - 61 }], order, 400, 300, prof);
    expect(p.y).toBeCloseTo(depthScale(site, 300).y(2614 - 61));
  });
  it("water-column sensors keep their true depth", () => {
    const site = b.siteById["axial-seamount-base"];
    const prof = profile(site, lon => -(2614 + (lon - site.lon) * 4000));
    const pts = layout(site, site.sensorIds.map(id => b.sensorById[id]), order, 400, 300, prof);
    const s = depthScale(site, 300), sp = pts.find(p => p.id === "sp-ctd"), dp = pts.find(p => p.id === "dp-ctd");
    expect(sp.y).toBeCloseTo(s.y(5)); expect(sp.y2).toBeCloseTo(s.y(200));
    expect(dp.y).toBeCloseTo(s.y(250)); expect(dp.y2).toBeCloseTo(s.y(2457));
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
