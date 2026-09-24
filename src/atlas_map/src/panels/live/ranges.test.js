import { describe, expect, it } from "vitest";
import { checkCustom, preset } from "./ranges.js";

describe("ranges", () => {
  const now = new Date("2026-09-23T12:34:56Z");
  it("presets end now (to the minute) and span the preset", () => {
    expect(preset("24h", now)).toEqual({ start: "2026-09-22T12:34:00Z", end: "2026-09-23T12:34:00Z" });
    expect(preset("30d", now).start).toBe("2026-08-24T12:34:00Z");
  });
  it("custom ranges are checked before any request", () => {
    expect(checkCustom("2026-09-20T00:00", "2026-09-19T00:00")).toEqual({ ok: false, message: "End must be after start." });
    expect(checkCustom("2026-08-01T00:00", "2026-09-02T00:00").ok).toBe(false);
    expect(checkCustom("2026-08-01T00:00", "2026-09-02T00:00").message).toMatch(/31 days/);
    expect(checkCustom("2026-09-01T00:00", "2026-09-02T00:00")).toEqual({ ok: true, start: "2026-09-01T00:00:00Z", end: "2026-09-02T00:00:00Z" });
  });
});
