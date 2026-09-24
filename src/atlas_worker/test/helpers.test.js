import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { answerPrompt, evidencePackage, excerpt, parseHypo71Events, publicHit, sourceKey } from "../src/helpers.js";

const hypo71 = await readFile(new URL("./fixtures/hypo71_20260923.dat", import.meta.url), "utf8");

test("hypo71 events: one per catalog row, with UTC time, decimal degrees west, depth and magnitude", () => {
  const events = parseHypo71Events(hypo71, "20260923");
  assert.equal(events.length, 71);   // the header line is not an event
  assert.deepEqual(events[0], { time: "2026-09-23T00:08:50.930Z", lat: 45.940500, lon: -130.018833, depth_km: 0.63, mag: 0.2 });
  // "130  1.13" is 130° 1.13′ W; a negative magnitude survives
  const neg = events.find(e => e.time.startsWith("2026-09-23T02:02"));
  assert.equal(neg.mag, -0.02);
  assert.equal(neg.lon, -130.002333);
});

test("hypo71 events skip rows from another day and short lines, like the count does", () => {
  const text = `${hypo71.split("\n").slice(0, 3).join("\n")}\n20260922 2359 59.00 45 56.00 130  1.00   1.00   0.10 9 100 0.5 0.02 1.0 1.0 1 1e18 1e18\n20260923 0000 bad`;
  assert.equal(parseHypo71Events(text, "20260923").length, 2);
});

test("hypo71 seconds of 60.00 roll into the next minute", () => {
  const events = parseHypo71Events("20260923 1259 60.00 45 56.00 130  1.00   1.00   0.10 9 100 0.5 0.02 1.0 1.0 1 1e18 1e18", "20260923");
  assert.equal(events[0].time, "2026-09-23T13:00:00.000Z");
});

test("publicHit adds a whitespace-normalized excerpt of about 280 characters and keeps the old fields", () => {
  const text = `  Axial   Seamount\n\n inflation ${"is measured by bottom pressure tilt instruments ".repeat(10)}`;
  const hit = publicHit({ chunk_id: "C-1", collection_id: "c", collection_label: "C", title: "T", score: 0.5, text, citations: [{ source_id: "S" }], metadata: { a: 1 } });
  assert.equal(hit.chunk_id, "C-1");
  assert.deepEqual(hit.citations, [{ source_id: "S" }]);
  assert.deepEqual(hit.metadata, { a: 1 });
  assert.ok(hit.excerpt.startsWith("Axial Seamount inflation is measured"));
  assert.ok(hit.excerpt.length <= 281, hit.excerpt.length);
  assert.ok(hit.excerpt.endsWith("…"));
  assert.ok(!/\s{2}/.test(hit.excerpt));
  assert.equal("text" in hit, false);   // the full chunk text stays private
});

test("excerpt keeps short text whole and handles missing text", () => {
  assert.equal(excerpt("Short  text."), "Short text.");
  assert.equal(excerpt(undefined), "");
  assert.equal(publicHit({ chunk_id: "x" }).excerpt, "");
});

test("the answer prompt asks for bracketed source numbers after claims, and nothing else", () => {
  const sources = [{ id: "A", title: "First source" }, { id: "B", title: "Second source" }];
  const prompt = answerPrompt({ question: "What measures inflation?", evidence: "First source | sources: [1]\ntext", sources, mode: "research" });
  assert.match(prompt, /\[n\]/);
  assert.match(prompt, /\[1\] First source; \[2\] Second source/);
  assert.match(prompt, /after the claim/i);
  assert.doesNotMatch(prompt, /Do not include citations, bracketed numbers/);
  assert.match(prompt, /URLs/);   // still no ids or URLs in the text
  assert.match(prompt, /Question: What measures inflation\?/);
});

test("the compact prompt keeps its word limit and names the product", () => {
  const prompt = answerPrompt({ question: "How do I get the DAS data?", evidence: "e", sources: [], mode: "compact", product: "multidas" });
  assert.match(prompt, /under 120 words/);
  assert.match(prompt, /specifically named multidas/);
  assert.match(prompt, /\[n\]/);
});

test("the Axial count answer carries its events and keeps the count", async (t) => {
  const { default: worker } = await import("../src/index.js");
  t.mock.method(globalThis, "fetch", async (url) => {
    assert.equal(String(url), "http://axial.ocean.washington.edu/hypo71/hypo71_20260923.dat");
    return new Response(hypo71, { status: 200 });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "How many earthquakes at Axial on 2026-09-23?" }),
  }), {});
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.answer, "There were 71 Axial Seamount earthquakes in the live catalog for 2026-09-23 UTC.");
  assert.equal(data.events.length, 71);
  assert.deepEqual(Object.keys(data.events[0]), ["time", "lat", "lon", "depth_km", "mag"]);
  assert.equal(data.answer_citations[0].id, "axial-live-catalog");
});

test("evidence headers number sources that share an id by their URL", () => {
  const numbers = new Map([[sourceKey("PI", "http://p/das25/"), 1], [sourceKey("PI", "http://p/das24/"), 2], [sourceKey("C-3", ""), 3]]);
  const text = evidencePackage([
    { title: "DAS25", text: "a", citations: [{ source_id: "PI", url: "http://p/das25/" }] },
    { title: "DAS24", text: "b", citations: [{ source_id: "PI", url: "http://p/das24/" }] },
    { chunk_id: "C-3", title: "Guide", text: "c", citations: [{ url: null }] },
  ], numbers);
  assert.equal(text, "DAS25 | sources: [1]\na\n\nDAS24 | sources: [2]\nb\n\nGuide | sources: [3]\nc");
});
