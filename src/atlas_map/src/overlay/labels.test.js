import { describe, expect, it } from "vitest";
import { place, stems } from "./labels.js";

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

describe("stems", () => {
  it("a lower-priority region card that would overlap rises above the one in front", () => {
    const s = stems([
      { id: "slope", x: 1238, y: 588, w: 150, h: 26, priority: 37 },
      { id: "hydrate", x: 1291, y: 575, w: 125, h: 26, priority: 34 },
      { id: "shelf", x: 1400, y: 527, w: 120, h: 26, priority: 15 },
      { id: "axial", x: 510, y: 367, w: 130, h: 26, priority: 66 },
    ], 26, 6);
    expect(s.get("axial")).toBe(26);
    expect(s.get("slope")).toBe(26);
    expect(s.get("hydrate")).toBe(26 + 32);   // one step clears slope's card
    expect(s.get("shelf")).toBe(26 + 32);     // then clears hydrate's raised card
  });
  it("cards that do not touch keep the base stem", () => {
    const s = stems([{ id: "a", x: 0, y: 100, w: 50, h: 20, priority: 2 }, { id: "b", x: 300, y: 100, w: 50, h: 20, priority: 1 }], 26, 6);
    expect([...s.values()]).toEqual([26, 26]);
  });
});
