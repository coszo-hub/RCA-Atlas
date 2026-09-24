import { describe, expect, it } from "vitest";
import { fmtDate, fmtDepth, fmtRange, statusGroup, statusLabel } from "./format.js";

describe("format", () => {
  it("depths and ranges", () => {
    expect(fmtDepth(2607)).toBe("2,607 m");
    expect(fmtDepth(null)).toBe("—");
    expect(fmtRange(5, 200)).toBe("5–200 m");
    expect(fmtRange(200, 200)).toBe("200 m");
  });
  it("status", () => {
    expect(statusLabel("NOT_DEPLOYED")).toBe("Not deployed");
    expect(statusGroup("PARTIALLY_FUNCTIONAL")).toBe("operating");
    expect(statusGroup("UNCABLED")).toBe("offline");
    expect(statusGroup("whatever")).toBe("unknown");
  });
  it("dates", () => {
    expect(fmtDate("2026-09-19T07:41:44+00:00")).toBe("Sep 19, 2026");
    expect(fmtDate(null)).toBe("unknown date");
  });
});
