import { describe, expect, it } from "vitest";
import { toX, toZ } from "./geo.js";
import { dayExtent, dayTracks, smoothTrack } from "./WhaleLayer.js";

const day = { calls: [[-130.0, 45.95, 2, 300], [-129.99, 45.94, 0, 10], [-130.01, 45.96, 2, 100], [-129.98, 45.93, 1, 50]] };

describe("whale layer", () => {
  it("groups a day's calls into tracks in time order, untracked apart", () => {
    const { tracks, loose } = dayTracks(day);
    expect(Object.keys(tracks).sort()).toEqual(["1", "2"]);
    expect(tracks[2].map(c => c[2])).toEqual([100, 300]);
    expect(loose).toEqual([[-129.99, 45.94, 10]]);
  });

  it("frames a day's calls", () => {
    const e = dayExtent(day);
    expect(e.x).toBeCloseTo((toX(-130.01) + toX(-129.98)) / 2, 5);
    expect(e.z).toBeCloseTo((toZ(45.96) + toZ(45.93)) / 2, 5);
    expect(e.r).toBeGreaterThan(0);
  });

  it("draws a track as the running mean of its calls", () => {
    const zig = [[0, 0], [1, 1], [2, 0], [3, 1], [4, 0]];
    const s = smoothTrack(zig, 1);
    expect(s[0]).toEqual([0.5, 0.5]);                  // the first call and the next
    expect(s[2]).toEqual([2, 2 / 3]);
    expect(s).toHaveLength(5);
  });
});
