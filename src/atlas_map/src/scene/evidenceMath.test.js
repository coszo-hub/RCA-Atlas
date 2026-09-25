import { describe, expect, it } from "vitest";
import { edgeChip, eventShown, frameView, groupSpikes, hypoMeters, quakePx, riseAt, sinkAt, spikeHeight } from "./evidenceMath.js";

describe("spikeHeight", () => {
  it("scales with camera distance so spikes read the same from region to close zoom, within limits", () => {
    expect(spikeHeight(60)).toBeCloseTo(60 * 0.085);
    expect(spikeHeight(600) / 600).toBeCloseTo(spikeHeight(60) / 60);
    expect(spikeHeight(0.5)).toBe(0.12);        // close in: never a stub
    expect(spikeHeight(5000)).toBe(70);         // far out: capped
  });
  it("the active spike grows 1.8×", () => {
    expect(spikeHeight(60, true)).toBeCloseTo(spikeHeight(60) * 1.8);
  });
});

describe("rise and sink timing", () => {
  it("spikes rise staggered 120 ms apart, 600 ms each, eased", () => {
    expect(riseAt(0, 0)).toBe(0);
    expect(riseAt(600, 0)).toBe(1);
    expect(riseAt(120, 1)).toBe(0);             // the second starts 120 ms later
    expect(riseAt(420, 1)).toBeGreaterThan(0.5); // ease-out: past half height at half time
    expect(riseAt(419, 2)).toBeLessThan(riseAt(419, 1));
  });
  it("they sink in 300 ms", () => {
    expect(sinkAt(0)).toBe(1); expect(sinkAt(150)).toBeGreaterThan(0); expect(sinkAt(300)).toBe(0);
  });
  it("reduced motion: no animation", () => {
    expect(riseAt(0, 3, true)).toBe(1); expect(sinkAt(0, true)).toBe(0);
  });
  it("events appear in time order over about 3 s", () => {
    expect(eventShown(0, 0)).toBe(true);
    expect(eventShown(0.5, 1400)).toBe(false);
    expect(eventShown(0.5, 1600)).toBe(true);
    expect(eventShown(1, 3000)).toBe(true);
    expect(eventShown(1, 0, true)).toBe(true);
  });
});

describe("edgeChip", () => {
  const rect = { left: 412, top: 80, right: 1584, bottom: 940 };
  it("none for a point inside the free area in front of the camera", () => {
    expect(edgeChip([900, 500, 0.9], rect)).toBeNull();
  });
  it("a point off to the right clamps to the right edge, pointing right", () => {
    const c = edgeChip([2400, 510, 0.9], rect, 18);
    expect(c.x).toBe(1584 - 18);
    expect(c.y).toBeGreaterThan(80); expect(c.y).toBeLessThan(940);
    expect(c.angle).toBeCloseTo(0, 1);
  });
  it("a point under the chat panel is off-screen too: it clamps to the panel's edge", () => {
    const c = edgeChip([200, 510, 0.9], rect, 18);
    expect(c.x).toBe(412 + 18);
    expect(Math.abs(c.angle)).toBeCloseTo(Math.PI, 1);
  });
  it("a point behind the camera points the other way", () => {
    const c = edgeChip([1000, 100, 1.2], rect, 18);
    expect(c.y).toBe(940 - 18);
  });
});


describe("groupSpikes", () => {
  it("one spike per location, numbers merged in order; cables stay separate", () => {
    const g = groupSpikes([
      { n: 1, kind: "sensor", lon: -130.0, lat: 45.95, color: "#c98500" },
      { n: 2, kind: "site", lon: -129.75, lat: 45.81, color: "#ecebe6" },
      { n: 3, kind: "sensor", lon: -130.0, lat: 45.95, color: "#d95926" },
      { n: 4, kind: "cable", lon: -125, lat: 45, color: "#ffbd59", layers: ["a"] },
    ]);
    expect(g.spikes.map(s => s.ns)).toEqual([[1, 3], [2]]);
    expect(g.spikes[0].color).toBe("#c98500");
    expect(g.cables.map(c => c.n)).toEqual([4]);
  });
});

describe("frameView", () => {
  it("frames the evidence around its centre, far enough for its spread, keeping the heading and exaggeration", () => {
    const v = frameView([[-130.0, 45.95], [-129.75, 45.82]], { az: 0.4, exag: 3 });
    expect(v.ll[0]).toBeCloseTo(-129.875); expect(v.ll[1]).toBeCloseTo(45.885);
    expect(v.az).toBe(0.4); expect(v.exag).toBe(3);
    expect(v.dist).toBeGreaterThan(30); expect(v.dist).toBeLessThan(90);
  });
  it("one point still gets a close, readable view", () => {
    expect(frameView([[-130, 45.95]], { az: 0, exag: 3 }).dist).toBe(9);
  });
});

it("hypocentres sit below the catalog datum", () => {
  expect(hypoMeters(0.63)).toBe(-2130);
  expect(hypoMeters(null, 1400)).toBe(-1400);
});

it("quakePx grows with magnitude and never vanishes", () => {
  expect(quakePx(null)).toBe(quakePx(-1));
  expect(quakePx(2)).toBeGreaterThan(quakePx(0.5));
  expect(quakePx(-1)).toBeGreaterThan(2);
});
