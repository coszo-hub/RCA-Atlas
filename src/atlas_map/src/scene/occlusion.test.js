import { describe, expect, it } from "vitest";
import { occluded } from "./occlusion.js";

describe("occluded", () => {
  const ridge = (x, z) => (Math.abs(x) < 1 ? 5 : 0);   // a 5-unit wall at x≈0
  it("hidden behind the ridge", () => { expect(occluded([-10, 2, 0], [10, 0.1, 0], ridge)).toBe(true); });
  it("visible from above", () => { expect(occluded([-10, 50, 0], [10, 0.1, 0], ridge)).toBe(false); });
  it("visible with nothing between", () => { expect(occluded([5, 2, 0], [10, 0.1, 0], ridge)).toBe(false); });
});
