import { describe, expect, it, vi } from "vitest";
import { ASK_URL, MODELS, askAtlas, modelLabel } from "./askApi.js";

const respond = (status, body) => vi.fn(async () => ({ ok: status < 400, status, json: async () => body }));

describe("askAtlas", () => {
  it("posts the question and model to the dev proxy and times the answer", async () => {
    const fetchImpl = respond(200, { answer: "A.", answer_citations: [] });
    let t = 1000;
    const r = await askAtlas("What is at Axial?", { model: "gemini-2.5-flash", tz: "America/Los_Angeles", fetchImpl, now: () => (t += 900) });
    expect(ASK_URL).toBe("/api/ask");
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/ask");
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body)).toEqual({ query: "What is at Axial?", answer_mode: "evidence", model: "gemini-2.5-flash", tz: "America/Los_Angeles" });
    expect(r).toEqual({ ok: true, data: { answer: "A.", answer_citations: [] }, ms: 900 });
  });
  it("the Worker's error is stated plainly", async () => {
    const r = await askAtlas("q?", { fetchImpl: respond(503, { error: "answer temporarily unavailable" }) });
    expect(r).toEqual({ ok: false, message: "Answer temporarily unavailable (HTTP 503)." });
  });
  it("unreachable and empty answers", async () => {
    expect(await askAtlas("q?", { fetchImpl: async () => { throw new TypeError("Failed to fetch"); } }))
      .toEqual({ ok: false, message: "The Atlas answer service could not be reached." });
    expect(await askAtlas("q?", { fetchImpl: respond(200, { hits: [] }) })).toEqual({ ok: false, message: "The Atlas returned no answer." });
    expect(await askAtlas("q?", { fetchImpl: async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("x"); } }) }))
      .toEqual({ ok: false, message: "The Atlas answer service did not respond (HTTP 502)." });
  });
  it("abort propagates", async () => {
    const err = Object.assign(new Error("aborted"), { name: "AbortError" });
    await expect(askAtlas("q?", { fetchImpl: async () => { throw err; } })).rejects.toBe(err);
  });
  it("offers the models the Worker accepts, Auto first", () => {
    expect(MODELS.map(m => m[0])).toEqual(["auto", "gemini-2.5-flash", "gemini-3.5-flash-lite", "groq-gpt-oss-120b", "groq-gpt-oss-20b", "groq-qwen3-8-27b", "gpt-5.4-mini"]);
  });
  it("labels answer models briefly", () => {
    expect(modelLabel("gemini-2.5-flash")).toBe("gemini-2.5-flash");
    expect(modelLabel("axial_count_events (live catalog)")).toBe("live catalog");
    expect(modelLabel("RCA Atlas graph route")).toBe("graph route");
    expect(modelLabel(undefined)).toBe("");
  });
});
