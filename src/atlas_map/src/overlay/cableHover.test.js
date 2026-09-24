import { describe, expect, it } from "vitest";
import { nearest } from "./cableHover.js";

describe("nearest", () => {
  const lines = [{ info: "A", pts: [[0, 0], [100, 0]] }, { info: "B", pts: [[0, 50], [100, 50]] }];
  it("finds the closest segment within range", () => {
    expect(nearest(50, 4, lines)).toBe("A");
    expect(nearest(50, 47, lines)).toBe("B");
    expect(nearest(50, 25, lines)).toBeNull();
  });
});
