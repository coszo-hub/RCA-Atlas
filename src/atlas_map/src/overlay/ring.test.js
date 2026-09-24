import { describe, expect, it } from "vitest";
import { ringSize, ringSvg } from "./ring.js";
import { bundleFixture } from "../test/fixtures.js";

describe("ring", () => {
  const b = bundleFixture();
  const site = b.siteById["axial-seamount-base"];
  it("one segment per located sensor, status by stroke", () => {
    const svg = ringSvg(site, b.sensorById, b.familyByKey, 24);
    const segs = [...svg.matchAll(/class="seg"[^>]*/g)].map(m => m[0]);
    expect(segs).toHaveLength(3);
    expect(segs.filter(s => s.includes('stroke-width="3.2"'))).toHaveLength(3);
    expect(segs.filter(s => s.includes('opacity="0.3"'))).toHaveLength(1);   // dp-ctd is offline
    expect(svg).toContain('class="halo"');
  });
  it("planned and unknown are thin; unknown is dashed; no halo without operating sensors", () => {
    const shelf = ringSvg(b.siteById["oregon-shelf"], b.sensorById, b.familyByKey, 18);
    expect(shelf).toContain('stroke-width="1.3"');
    expect(shelf).not.toContain("stroke-dasharray");
    expect(shelf).not.toContain('class="halo"');
    const caldera = ringSvg(b.siteById["axial-seamount-central-caldera"], b.sensorById, b.familyByKey, 18);
    expect(caldera).toContain("stroke-dasharray");
  });
  it("color is the family color", () => {
    expect(ringSvg(site, b.sensorById, b.familyByKey, 24)).toContain('stroke="#3987e5"');
  });
  it("sizes", () => { expect([ringSize(1), ringSize(3), ringSize(7)]).toEqual([18, 24, 30]); });
});
