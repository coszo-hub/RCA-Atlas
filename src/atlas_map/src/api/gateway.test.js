import { describe, expect, it } from "vitest";
import { api, chat, series } from "./gateway.js";

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

describe("chat", () => {
  it("uses the gateway's /chat without a Worker URL", async () => {
    let seen;
    const r = await chat("hi there", { chatUrl: null, fetchImpl: async (url, init) => { seen = [url, JSON.parse(init.body)]; return { ok: true, status: 200, json: async () => ({ answer: "a", citations: [] }) }; } });
    expect(seen).toEqual(["/api/chat", { question: "hi there" }]);
    expect(r).toEqual({ ok: true, data: { answer: "a", citations: [] } });
  });
  it("asks the Worker and maps its answer to the gateway's shape", async () => {
    let seen;
    const r = await chat("What is Axial?", { chatUrl: "https://w.example/", fetchImpl: async (url, init) => {
      seen = [url, JSON.parse(init.body)];
      return { ok: true, status: 200, json: async () => ({ answer: "A volcano.", answer_model: "gemini-2.5-flash",
        answer_citations: [{ id: "c1", title: "Axial", url: "https://x" }, { id: "c2" }] }) };
    } });
    expect(seen).toEqual(["https://w.example/v1/answer", { query: "What is Axial?", model: "auto", answer_mode: "evidence" }]);
    expect(r).toEqual({ ok: true, data: { answer: "A volcano.", model: "gemini-2.5-flash",
      citations: [{ id: "c1", title: "Axial", url: "https://x" }, { id: "c2", title: "c2", url: "" }] } });
  });
  it("reports the Worker's error, or that it could not be reached", async () => {
    const busy = await chat("q?", { chatUrl: "https://w", fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({ error: "Atlas is temporarily unavailable" }) }) });
    expect(busy).toEqual({ ok: false, kind: "busy", source: "Atlas chat", message: "Atlas is temporarily unavailable" });
    const down = await chat("q?", { chatUrl: "https://w", fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
    expect(down).toMatchObject({ ok: false, kind: "unreachable", source: "Atlas chat" });
  });
});
