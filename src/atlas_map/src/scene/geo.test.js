import { describe, expect, it } from "vitest";
import { fromX, fromZ, LAT0, LON0, toX, toZ } from "./geo.js";

describe("geo", () => {
  it("origin and round trip", () => {
    expect(toX(LON0)).toBe(0);
    expect(toZ(LAT0)).toBe(-0);
    expect(fromX(toX(-129.754))).toBeCloseTo(-129.754, 9);
    expect(fromZ(toZ(45.8168))).toBeCloseTo(45.8168, 9);
  });
  it("north is -z and 1 unit is 1 km", () => {
    expect(toZ(LAT0 + 1)).toBeCloseTo(-111.13, 2);
    expect(toX(LON0 + 1)).toBeCloseTo(78.6, 0);
  });
});
