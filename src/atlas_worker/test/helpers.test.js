import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { answerPrompt, axialDayWindow, evidencePackage, eventsInWindow, excerpt, isInstrumentInventoryQuestion, namedDas, parseHypo71Events, publicHit, searchText, sourceKey, sourceKind, withRouteCitations } from "../src/helpers.js";

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

test("the compact prompt keeps a word limit, lists every route, and names the product", () => {
  const prompt = answerPrompt({ question: "How do I get the DAS data?", evidence: "e", sources: [], mode: "compact", product: "multidas" });
  assert.match(prompt, /under 230 words/);
  assert.match(prompt, /Include every numbered download source; never drop one/);
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

test("evidence headers mark papers and websites, and the prompt prefers the paper where they disagree", () => {
  assert.equal(sourceKind({ collection_id: "literature" }), "scientific literature");
  assert.equal(sourceKind({ collection_id: "arcada", metadata: { source_row_type: "paper" } }), "scientific literature");
  assert.equal(sourceKind({ collection_id: "websites" }), "website");
  assert.equal(sourceKind({ collection_id: "instruments" }), null);
  const numbers = new Map([[sourceKey("L", ""), 1], [sourceKey("W", ""), 2], [sourceKey("I", ""), 3]]);
  const text = evidencePackage([
    { chunk_id: "L", collection_id: "literature", title: "Stacked sills", text: "300–450 m", citations: [{ source_id: "L" }] },
    { chunk_id: "W", collection_id: "websites", title: "Roots of Axial", text: "400-500 m", citations: [{ source_id: "W" }] },
    { chunk_id: "I", collection_id: "instruments", title: "BOTPT", text: "x", citations: [{ source_id: "I" }] },
  ], numbers);
  assert.equal(text, "Stacked sills (scientific literature) | sources: [1]\n300–450 m\n\nRoots of Axial (website) | sources: [2]\n400-500 m\n\nBOTPT | sources: [3]\nx");
  assert.match(answerPrompt({ question: "q", evidence: text, sources: [], mode: "research" }), /disagree about a fact or number, give the scientific literature's value/);
});

const day24 = await readFile(new URL("./fixtures/hypo71_20260924.dat", import.meta.url), "utf8");
const day25 = await readFile(new URL("./fixtures/hypo71_20260925.dat", import.meta.url), "utf8");
const evening = new Date("2026-09-25T02:18:00Z");   // 7:18 pm on Thursday 24 September in Seattle

test("today is the asker's calendar day: in Seattle that evening it spans two UTC catalog files", () => {
  const w = axialDayWindow("How many earthquakes at Axial today?", { tz: "America/Los_Angeles", now: evening });
  assert.equal(w.day, "2026-09-24");
  assert.equal(w.today, true);
  assert.equal(w.start.toISOString(), "2026-09-24T07:00:00.000Z");
  assert.equal(w.end.toISOString(), "2026-09-25T07:00:00.000Z");
  assert.deepEqual(w.stamps, ["20260924", "20260925"]);
  assert.equal(w.label, "Thursday, September 24");
});

test("without a time zone the day stays the UTC day, as the published page expects", () => {
  const w = axialDayWindow("How many earthquakes at Axial today?", { now: evening });
  assert.equal(w.day, "2026-09-25");
  assert.equal(w.tz, "UTC");
  assert.deepEqual(w.stamps, ["20260925"]);
  assert.equal(axialDayWindow("How many earthquakes at Axial today?", { tz: "Not/AZone", now: evening }).tz, "UTC");
});

test("yesterday and explicit dates are the asker's days too; other questions are not catalog counts", () => {
  assert.equal(axialDayWindow("How many earthquakes at Axial yesterday?", { tz: "America/Los_Angeles", now: evening }).day, "2026-09-23");
  const d = axialDayWindow("Count earthquakes at Axial on 2026-09-20", { tz: "America/Los_Angeles", now: evening });
  assert.equal(d.day, "2026-09-20");
  assert.equal(d.today, false);
  assert.equal(axialDayWindow("What instruments are at Axial?", { now: evening }), null);
});

test("events in the window: the Seattle day so far counts rows from both files and no others", () => {
  const w = axialDayWindow("How many earthquakes at Axial today?", { tz: "America/Los_Angeles", now: evening });
  const events = eventsInWindow([[day24, "20260924"], [day25, "20260925"]], w);
  assert.equal(events.length, 65);
  assert.ok(events.every(e => e.time >= "2026-09-24T07:00:00Z" && e.time < "2026-09-25T07:00:00Z"));
  assert.ok(events[0].time < events[events.length - 1].time);
});

test("inventory questions name an instrument type or a generic word, with a place", () => {
  for (const q of ["what seismometers are available at axial seamount", "Which hydrophones are at the ASHES vent field?",
    "what sensors are at the southern hydrate ridge site", "list the instruments deployed at the Oregon Shelf",
    "which seismic stations are in the caldera"]) assert.equal(isInstrumentInventoryQuestion(q), true, q);
  for (const q of ["what is axial seamount?", "how do seismometers work?", "when did axial seamount last erupt?",
    "what instruments does COSZO use?"]) assert.equal(isInstrumentInventoryQuestion(q), false, q);
});

test("a PI portal record's download routes become sources: DAS routes as their dataset, other routes each under its own name", () => {
  const hit = {
    chunk_id: "PI-CHUNK-1",
    text: "Data for 2021 RCA Distributed Acoustic and Temperature Sensing experiment are available to download from OptaSense north cable receive fiber (http://piweb.ooirsn.uw.edu/das/data/Optasense/NorthCable/ReceiveFiber/); Silixa DAS (http://piweb.ooirsn.uw.edu/das/data/Silixa/DAS/); Silixa DTS (http://piweb.ooirsn.uw.edu/das/data/Silixa/DTS/). Physical site: RCA north and south backbone cables. Official OOI context: https://oceanobservatories.org/pi-instrument/x/",
    citations: [{ source_id: "SRC-1", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/das/data/Optasense/NorthCable/ReceiveFiber/" }],
  };
  const out = withRouteCitations(hit);
  // The 2021 dataset's sub-folders are one dataset with one link: its parent folder.
  assert.deepEqual(out.citations.map((c) => [c.source_id, c.title, c.url]), [
    ["SRC-1", "2021 conventional DAS (OptaSense and Silixa)", "http://piweb.ooirsn.uw.edu/das/data/"],
  ]);
  const covis = withRouteCitations({ chunk_id: "C", citations: [{ source_id: "S", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/covis/data/COVIS/" }],
    text: "Data for COVIS are available to download from COVIS raw survey archives (http://piweb.ooirsn.uw.edu/covis/data/COVIS/); COVIS browse products (http://piweb.ooirsn.uw.edu/covis/data/BROWSE/). Physical site: ASHES." });
  assert.deepEqual(covis.citations.map((c) => c.title), ["COVIS raw survey archives", "COVIS browse products"]);
  // Other hits pass through untouched.
  const paper = { chunk_id: "P", text: "DAS denoising without clean data", citations: [{ source_id: "D", url: "https://doi.org/x" }] };
  assert.equal(withRouteCitations(paper), paper);
});

test("a download question puts every routing record in front of the model, even ranked last by retrieval", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const paper = (i) => ({ chunk_id: `P${i}`, collection_id: "arcada", title: `DAS paper ${i}`, text: "Distributed acoustic sensing (DAS) on the Regional Cabled Array: methods.",
    citations: [{ source_id: `P${i}`, title: `DAS paper ${i}`, url: `https://doi.org/${i}` }] });
  const routing = { chunk_id: "R21", collection_id: "pi_portal", title: "2021 RCA DAS experiment data availability and routing",
    text: "Data for the 2021 RCA Distributed Acoustic and Temperature Sensing experiment (DAS) are available to download from Silixa DAS (http://piweb.ooirsn.uw.edu/das/data/Silixa/DAS/); Silixa DTS (http://piweb.ooirsn.uw.edu/das/data/Silixa/DTS/). Physical site: RCA north and south backbone cables.",
    citations: [{ source_id: "PI", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/das/data/Silixa/DAS/" }] };
  let prompt = "";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const covis = { chunk_id: "RC", collection_id: "pi_portal", title: "COVIS data availability and routing",
      text: "Data for COVIS are available to download from COVIS raw survey archives (http://piweb.ooirsn.uw.edu/covis/data/COVIS/). Physical site: ASHES.",
      citations: [{ source_id: "PI", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/covis/data/COVIS/" }] };
    if (String(url).endsWith("/v1/context")) return Response.json({ hits: [covis, ...Array.from({ length: 9 }, (_, i) => paper(i)), routing], neighbors: [], tool_hints: [] });
    prompt = JSON.parse(init.body).contents[0].parts[0].text;
    return Response.json({ candidates: [{ content: { parts: [{ text: "2021 experiment\n- Silixa DAS [1]\n- Silixa DTS [2]" }] } }] });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "How do I get the DAS data?" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" });
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.match(prompt, /Silixa DTS \(http:\/\/piweb\.ooirsn\.uw\.edu\/das\/data\/Silixa\/DTS\/\)/);
  assert.match(prompt, /\[\d+\] 2021 conventional DAS \(OptaSense and Silixa\)/);   // the dataset is one numbered source
  assert.deepEqual(data.answer_citations.filter((c) => c.url.includes("/das/data/")).map((c) => [c.title, c.url]),
    [["2021 conventional DAS (OptaSense and Silixa)", "http://piweb.ooirsn.uw.edu/das/data/"]]);
  assert.doesNotMatch(prompt, /COVIS/);   // another instrument's downloads stay out of a DAS answer
  assert.ok(!data.answer_citations.some((c) => c.url.includes("/covis/")));
});

test("DAS experiments are recognised by the map's labels, their years, and their interrogators", () => {
  const key = (q) => namedDas(q)?.key ?? null;
  assert.equal(key("where can i download DAS21 data"), "das21");
  assert.equal(key("where can i download DAS data from 2021"), "das21");
  assert.equal(key("Silixa DTS files?"), "das21");
  assert.equal(key("where can I get DAS24 data"), "das24");
  assert.equal(key("RAPID DAS download"), "das24");
  assert.equal(key("2025 DAS data"), "das25");
  assert.equal(key("DAS-25 routes"), "das25");
  assert.equal(key("MultiDAS 2025 files"), "multidas");   // a route before its experiment
  assert.equal(key("where is the OptoDAS data"), "optodas");
  assert.equal(key("what das data is available for download"), null);   // all experiments, not one
  assert.match(namedDas("DAS21").search, /2021 RCA Distributed Acoustic and Temperature Sensing experiment/);
  assert.ok(namedDas("DAS21").record.test("Data for 2021 RCA Distributed Acoustic and Temperature Sensing experiment are available"));
});

test("a DAS experiment named by the map's label (DAS21) reaches the model, cited as its one dataset", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const paper = (i) => ({ chunk_id: `A${i}`, collection_id: "arcada", title: `RCA Distributed Acoustic Sensing paper ${i}`, text: "The Regional Cabled Array DAS deployment.",
    citations: [{ source_id: `A${i}`, title: `paper ${i}`, url: `https://doi.org/${i}` }] });
  const r21 = { chunk_id: "R21", collection_id: "pi_portal", title: "2021 RCA Distributed Acoustic and Temperature Sensing experiment data availability and routing",
    text: "Data for 2021 RCA Distributed Acoustic and Temperature Sensing experiment are available to download from OptaSense south cable receive fiber (http://piweb.ooirsn.uw.edu/das/data/Optasense/SouthCable/ReceiveFiber/); Silixa DTS (http://piweb.ooirsn.uw.edu/das/data/Silixa/DTS/). Physical site: RCA north and south backbone cables.",
    citations: [{ source_id: "PI", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/das/data/Optasense/SouthCable/ReceiveFiber/" }] };
  const r25 = { ...r21, chunk_id: "R25", title: "2025–2026 RCA Distributed Acoustic Sensing experiment data availability and routing",
    text: "Data for 2025–2026 RCA Distributed Acoustic Sensing experiment are available to download from DAS25 MultiDAS (http://piweb.ooirsn.uw.edu/das25/data/MultiDAS/). Physical site: RCA.",
    citations: [{ source_id: "PI", title: "Shared RCA and COSZO Instruments corpus", url: "http://piweb.ooirsn.uw.edu/das25/data/MultiDAS/" }] };
  let query = "", prompt = "";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    if (String(url).endsWith("/v1/context")) { query = JSON.parse(init.body).query; return Response.json({ hits: [r21, r25, ...Array.from({ length: 8 }, (_, i) => paper(i))], neighbors: [], tool_hints: [] }); }
    prompt = JSON.parse(init.body).contents[0].parts[0].text;
    return Response.json({ candidates: [{ content: { parts: [{ text: "2021\n- OptaSense south cable receive fiber [1]\n- Silixa DTS [2]" }] } }] });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "where can i download DAS21 data" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" });
  const data = await res.json();
  assert.match(query, /2021 RCA Distributed Acoustic and Temperature Sensing experiment/);   // the search names it as the corpus does
  assert.match(prompt, /Silixa DTS \(http/);
  assert.match(prompt, /named DAS21, the 2021 conventional DAS experiment/);
  assert.doesNotMatch(prompt, /MultiDAS/);   // the named experiment only
  assert.deepEqual(data.answer_citations.map((c) => c.title), ["2021 conventional DAS (OptaSense and Silixa)"]);
});

test("shorthand and DAS labels are searched with the corpus's own words", () => {
  assert.match(searchText("which paper showcased the dv/v for cascadia subduction zone"), /seismic velocity change .*ambient seismic noise interferometry/);
  assert.match(searchText("δv/v at Slope Base"), /seismic velocity change/);
  assert.match(searchText("dv / v trends"), /seismic velocity change/);
  assert.match(searchText("where can i download DAS21 data"), /2021 RCA Distributed Acoustic and Temperature Sensing experiment/);
  assert.equal(searchText("what is axial seamount"), "what is axial seamount");
  assert.equal(searchText("the dvd archive"), "the dvd archive");
  assert.match(searchText("how deep is the AMC at axial"), /axial magma chamber/);
  assert.match(searchText("what instruments are at OSB"), /Oregon Slope Base/);
  assert.match(searchText("which study used CI OBS data"), /Cascadia Initiative .*ocean bottom seismometer|ocean bottom seismometer .*Cascadia Initiative/);
  assert.equal(searchText("the ci of the estimate"), "the ci of the estimate");   // lower-case ci is not the Cascadia Initiative
  assert.match(searchText("VLFEs offshore"), /very low frequency earthquakes/);
  assert.equal(searchText("which paper used DAS for seismic ocean thermometry"), "which paper used distributed acoustic sensing for seismic ocean thermometry");
  assert.equal(searchText("How do I get the DAS data?"), "How do I get the DAS data?");   // its download records match "DAS" itself
});

test("one long paper does not crowd out the others: at most two of its sections reach the model", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const section = (title, i) => ({ chunk_id: `${title}-${i}`, collection_id: "arcada", title, text: `Distributed acoustic sensing on the Regional Cabled Array, part ${i}.`,
    citations: [{ source_id: title, title, url: `https://doi.org/${encodeURIComponent(title)}` }] });
  const hits = [...[1, 2, 3, 4, 5].map((i) => section("DAS-N2N denoising", i)), section("Seismic ocean thermometry with DAS", 1), section("DAS early warning", 1)];
  let prompt = "";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    if (String(url).endsWith("/v1/context")) return Response.json({ hits, neighbors: [], tool_hints: [] });
    prompt = JSON.parse(init.body).contents[0].parts[0].text;
    return Response.json({ candidates: [{ content: { parts: [{ text: "Thermometry [2]." }] } }] });
  });
  await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "which paper used DAS for seismic ocean thermometry" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" });
  assert.equal((prompt.match(/^DAS-N2N denoising/gm) || []).length, 2);
  assert.match(prompt, /^Seismic ocean thermometry with DAS/m);
  assert.match(prompt, /^DAS early warning/m);
});
