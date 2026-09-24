import { describe, expect, it } from "vitest";
import { distanceKm, sitesNear } from "./nearby.js";
import { bundleFixture } from "../test/fixtures.js";

describe("nearby sites", () => {
  it("great-circle distance", () => {
    expect(distanceKm(-125, 45, -125, 46)).toBeCloseTo(111.2, 1);
    expect(distanceKm(-125, 45, -125, 45)).toBe(0);
  });
  it("lists sites within 30 km of a point, nearest first", () => {
    const b = bundleFixture();
    const near = sitesNear(b.sites, -129.7367, 45.8202);   // PN3A, beside Axial Base
    expect(near.map(n => n.site.id)).toEqual(["axial-seamount-base", "axial-seamount-central-caldera"]);
    expect(near[0].km).toBeLessThan(2);
    expect(near[1].km).toBeGreaterThan(20);
    expect(near[1].km).toBeLessThan(30);
    expect(sitesNear(b.sites, -127.278, 45.7556)).toEqual([]);   // PN5A: nothing within 30 km
  });
});
