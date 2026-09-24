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
  it("skips unlocated sensors and empty queries", () => {
    expect(searchAtlas(b, "tilt")).toEqual([]);
    expect(searchAtlas(b, " ")).toEqual([]);
  });
});
