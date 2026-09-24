import { describe, expect, it } from "vitest";
import { api, series } from "./gateway.js";

const respond = (status, body) => async () => ({ ok: status < 400, status, json: async () => body });

describe("api", () => {
  it("ok", async () => {
    expect(await api("/status/X", { fetchImpl: respond(200, { a: 1 }) })).toEqual({ ok: true, data: { a: 1 } });
  });
  it("maps statuses to kinds with the named source", async () => {
    const cases = [[404, "notfound"], [422, "bad"], [502, "upstream"], [503, "busy"], [504, "timeout"]];
    for (const [status, kind] of cases) {
      const r = await api("/x", { fetchImpl: respond(status, { error: { source: "ERDDAP", message: "m" } }) });
      expect(r).toEqual({ ok: false, kind, source: "ERDDAP", message: "m" });
    }
  });
  it("network failure is unreachable", async () => {
    const r = await api("/x", { fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
    expect(r).toMatchObject({ ok: false, kind: "unreachable", source: "gateway" });
  });
  it("vite proxy error (gateway down) is unreachable", async () => {
    const r = await api("/x", { fetchImpl: async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("x"); } }) });
    expect(r.kind).toBe("unreachable");
  });
  it("abort propagates", async () => {
    const err = Object.assign(new Error("aborted"), { name: "AbortError" });
    await expect(api("/x", { fetchImpl: async () => { throw err; } })).rejects.toBe(err);
  });
  it("series builds the query", async () => {
    let seen;
    await series("R", { var: "t", start: "2026-09-20T00:00:00Z", end: "2026-09-21T00:00:00Z" },
      { fetchImpl: async url => { seen = url; return { ok: true, status: 200, json: async () => ({}) }; } });
    expect(seen).toBe("/api/series/R?var=t&start=2026-09-20T00%3A00%3A00Z&end=2026-09-21T00%3A00%3A00Z");
  });
});
