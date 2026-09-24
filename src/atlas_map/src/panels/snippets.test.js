import { describe, expect, it } from "vitest";
import { snippetFor } from "./snippets.js";
import { bundleFixture } from "../test/fixtures.js";

const b = bundleFixture();
describe("snippetFor", () => {
  it("erddap: python + dataset id", () => {
    const s = snippetFor(b.sensorById["base-ctd"].access[0], b.sensorById["base-ctd"]);
    expect(s.code).toContain("from erddapy import ERDDAP");
    expect(s.code).toContain('dataset_id = "ooi-rs03axbs-lj03a-12-ctdpfb301"');
  });
  it("earthscope: dataselect url", () => {
    const s = snippetFor(b.sensorById.axcc1.access[0], b.sensorById.axcc1);
    expect(s.code).toContain("service.earthscope.org/fdsnws/dataselect/1/query?net=OO&sta=AXCC1&cha=HHZ");
  });
  it("earthscope: literal UTC start and end, one hour apart, no shell date", () => {
    const s = snippetFor(b.sensorById.axcc1.access[0], b.sensorById.axcc1, new Date("2026-09-24T07:05:09.750Z"));
    expect(s.code).toContain("&starttime=2026-09-24T06:05:09&endtime=2026-09-24T07:05:09");
    expect(s.code).not.toContain("$(");
    expect(s.code).not.toContain("date ");
  });
  it("documentation has no snippet", () => {
    expect(snippetFor(b.sensorById["shelf-bpr"].access[0], b.sensorById["shelf-bpr"])).toBeNull();
  });
});
