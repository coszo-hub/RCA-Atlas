import { describe, expect, it } from "vitest";
import { place } from "./labels.js";

describe("place", () => {
  it("higher priority wins overlaps", () => {
    const shown = place([
      { id: "small", x: 100, y: 100, w: 80, h: 16, priority: 1 },
      { id: "big", x: 110, y: 104, w: 80, h: 16, priority: 33 },
      { id: "far", x: 400, y: 100, w: 80, h: 16, priority: 1 },
    ]);
    expect([...shown].sort()).toEqual(["big", "far"]);
  });
});
