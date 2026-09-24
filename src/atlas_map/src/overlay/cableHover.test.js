import { describe, expect, it } from "vitest";
import { frontRuns, nearest } from "./cableHover.js";

describe("nearest", () => {
  const lines = [{ info: "A", pts: [[0, 0], [100, 0]] }, { info: "B", pts: [[0, 50], [100, 50]] }];
  it("finds the closest segment within range", () => {
    expect(nearest(50, 4, lines)).toBe("A");
    expect(nearest(50, 47, lines)).toBe("B");
    expect(nearest(50, 25, lines)).toBeNull();
  });
});

describe("frontRuns", () => {
  it("drops points behind the camera without bridging the gap", () => {
    const proj = [[0, 0, 0.5], [10, 0, 0.5], [20, 0, 1.2], [30, 0, 0.5], [40, 0, 0.5], [50, 0, 1.5], [60, 0, 0.5]];
    expect(frontRuns(proj)).toEqual([[[0, 0, 0.5], [10, 0, 0.5]], [[30, 0, 0.5], [40, 0, 0.5]]]);
  });
});
