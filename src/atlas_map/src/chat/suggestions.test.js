import { describe, expect, it } from "vitest";
import { suggest } from "./suggestions.js";
import { bundleFixture } from "../test/fixtures.js";

const b = bundleFixture();
describe("suggest", () => {
  it("site", () => { expect(suggest({ site: b.siteById["axial-seamount-base"] })[0]).toBe("What research has used data from Axial Seamount Base?"); });
  it("sensor", () => { expect(suggest({ sensor: b.sensorById["base-ctd"] })).toContain("What does a ctd measure?"); });
  it("nothing selected", () => { expect(suggest({})).toHaveLength(3); });
});
