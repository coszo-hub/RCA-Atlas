import { describe, expect, it } from "vitest";
import { searchAtlas } from "./search.js";
import { bundleFixture } from "../test/fixtures.js";

describe("searchAtlas", () => {
  const b = bundleFixture();
  it("finds sites and sensors, prefix first", () => {
    const r = searchAtlas(b, "axial");
    expect(r[0]).toMatchObject({ kind: "site" });
    expect(r.map(x => x.id)).toContain("axial-seamount-base");
    expect(r.find(x => x.id === "axial-seamount-base").sub).toBe("Axial Base");
  });
  it("matches refdes and type", () => {
    expect(searchAtlas(b, "ctdpfb301").map(x => x.id)).toEqual(["base-ctd"]);
    expect(searchAtlas(b, "seismometer").map(x => x.id)).toContain("axcc1");
  });
  it("finds sensors with no recorded position and marks them", () => {
    expect(searchAtlas(b, "tilt")).toEqual([{ kind: "sensor", id: "unlocated-bpt", title: "Axial Base bottom pressure and tilt",
      sub: "Axial Base · no recorded position", located: false }]);
    expect(searchAtlas(b, "mass spec")).toEqual([{ kind: "sensor", id: "pi-massp", title: "ASHES PI mass spectrometer",
      sub: "no recorded position", located: false }]);
  });
  it("ranks a located match ahead of an equally good unlocated one", () => {
    const r = searchAtlas(b, "ctd");   // every fixture CTD is a type match
    expect(r.filter(x => x.kind === "sensor").at(-1).located).toBe(false);
    expect(r[0].located).toBe(true);
  });
  it("ignores empty queries", () => {
    expect(searchAtlas(b, " ")).toEqual([]);
  });
});
