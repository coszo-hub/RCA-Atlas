import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { assetChunkIds, isAssetQuestion, questionCodes, askedPlace, isPaperUsageQuestion, instrumentSearch, instrumentCodes, typeInventory, statusSearch, askedType, liveTargetOf, isStatusQuestion, refdesOf, liveStatusHit, locatedUntil, magnitudeFloor, isDasOverview, DAS_EXPERIMENTS, answerPrompt, axialDayWindow, evidencePackage, eventsInWindow, excerpt, isInstrumentInventoryQuestion, namedDas, parseHypo71Events, publicHit, searchText, sourceKey, sourceKind, fullTextFor, paperKeys, withPlaces, withRouteCitations, questionParts, interleave } from "../src/helpers.js";

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
    if (String(url) === "http://axial.ocean.washington.edu") return new Response("with locations up to 24-Sep-2026 21:00:00 UTC");
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
  assert.match(answerPrompt({ question: "q", evidence: text, sources: [], mode: "research" }), /do not substitute a related finding/);
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

test("full text joins only papers already in the evidence, four passages a paper, eight in all, and is never excerpted", () => {
  const paper = (doi, n, collection = "literature_fulltext") => ({ chunk_id: `${doi}-${n}`, collection_id: collection, title: doi, text: `p${n}`,
    citations: [{ source_id: `REF-${doi}`, url: `https://doi.org/${doi}` }] });
  const evidence = [paper("10.1/a", 0, "literature"), { chunk_id: "W", collection_id: "websites", title: "W", citations: [{ source_id: "W", url: "https://x" }] },
    paper("10.1/b", 0, "arcada")];
  const passages = [paper("10.1/a", 1), paper("10.1/c", 1), paper("10.1/a", 2), paper("10.1/a", 3), paper("10.1/a", 4),
    paper("10.1/a", 5), paper("10.1/b", 1), paper("10.1/b", 2), paper("10.1/b", 3)];
  assert.deepEqual(fullTextFor(evidence, passages).map((p) => p.chunk_id), ["10.1/a-1", "10.1/a-2", "10.1/a-3", "10.1/a-4", "10.1/b-1", "10.1/b-2", "10.1/b-3"]);
  // A passage that mostly repeats the evidence (a first page restating the abstract) is skipped.
  const abstract = "seafloor pressure gauges monitor vertical deformation with time but inherent instrumental drift complicates and biases geodetic interpretation";
  const withAbstract = [{ ...evidence[0], text: abstract }];
  const page1 = { ...paper("10.1/a", 1), text: `Key points. ${abstract}. Introduction follows.` };
  assert.deepEqual(fullTextFor(withAbstract, [page1, paper("10.1/a", 2)]).map((p) => p.chunk_id), ["10.1/a-2"]);
  // A passage the search marks as layer counts whatever its collection (RCA Information's papers beyond their first chunk).
  assert.deepEqual(fullTextFor(evidence, [{ ...paper("10.1/b", 9, "arcada"), layer: true }]).map((p) => p.chunk_id), ["10.1/b-9"]);
  assert.deepEqual(fullTextFor(evidence, [paper("10.1/b", 9, "arcada")]), []);
  assert.deepEqual(paperKeys(evidence), ["10.1/a", "REF-10.1/a", "10.1/b", "REF-10.1/b"]);
  const placed = withPlaces(evidence, [{ ...paper("10.1/a", 1), metadata: { places: ["Oregon Slope Base"] } }]);
  assert.deepEqual(placed[0].metadata.places, ["Oregon Slope Base"]);
  assert.equal(placed[1].metadata, undefined);            // the website hit is left alone
  assert.deepEqual(fullTextFor([evidence[1]], passages), []);                   // no paper in the evidence, no full text
  assert.equal(sourceKey("REF-a", "https://doi.org/10.1/A"), sourceKey("ARCADA-PAPER-1", "http://doi.org/10.1/a"));
  assert.equal(publicHit(passages[0]).excerpt, "");
  assert.equal(publicHit(evidence[0]).excerpt, "");
  const numbers = new Map([[sourceKey("REF-10.1/a", "https://doi.org/10.1/a"), 1]]);
  assert.equal(evidencePackage([evidence[0], passages[0]], numbers),
    "10.1/a (scientific literature) | sources: [1]\np0\n\n10.1/a (scientific literature, full text) | sources: [1]\np1");
});

test("the Worker asks the paper's passages, and places the paper", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const text = "Acoustic water column surveys were conducted using the hull-mounted Kongsberg EM302 multibeam echosounder operating around a center frequency of 30 kHz with 288 beams per swath.";
  const abstract = { chunk_id: "LIT-1", collection_id: "literature", title: "Bubble plumes above Southern Hydrate Ridge", text: "Time-series acoustic images of methane bubble plumes.",
    citations: [{ source_id: "COSZO-REF-145", title: "Bubble plumes", url: "https://doi.org/10.1002/2016gc006250" }] };
  const passage = { chunk_id: "FT-1", collection_id: "literature_fulltext", title: abstract.title, text,
    citations: abstract.citations, metadata: { node_local_id: "FT-1", places: ["Southern Hydrate Ridge"] } };
  const calls = [];
  const answer = "Surveys were conducted using the hull-mounted Kongsberg EM302 multibeam echosounder operating around a center frequency of 30 kHz [1].";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = String(url); calls.push(u);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [abstract], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) {
      assert.deepEqual(JSON.parse(init.body).paper_keys, ["10.1002/2016gc006250", "COSZO-REF-145"]);
      return Response.json({ hits: [passage] });
    }
    return Response.json({ candidates: [{ content: { parts: [{ text: answer }] } }] });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "which multibeam echosounder mapped bubble plumes above southern hydrate ridge" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" });
  const data = await res.json();
  assert.equal(data.answer, answer);                                                     // a cited answer may use the paper's words
  assert.equal(calls.filter((u) => u.includes("generativelanguage")).length, 1);
  assert.deepEqual(data.hits[0].metadata.places, ["Southern Hydrate Ridge"]);
  assert.equal(data.hits[0].excerpt, "");
  assert.ok(!JSON.stringify(data).includes("288 beams per swath"));                       // no passage text reaches the reader
  assert.equal(data.answer_citations.length, 1);                                         // abstract and passage: one source
});

test("a two-part question is searched part by part, and a summary's DOI brings in its paper", () => {
  assert.deepEqual(questionParts("How fast did the dike propagate during the 2015 eruption, and how many earthquakes were relocated before it?"),
    ["How fast did the dike propagate during the 2015 eruption", "how many earthquakes were relocated before it"]);
  assert.deepEqual(questionParts("What is the BOTPT and where is it?"), ["What is the BOTPT and where is it?"]);
  const a = [{ chunk_id: "1" }, { chunk_id: "2" }, { chunk_id: "3" }], b = [{ chunk_id: "9" }, { chunk_id: "2" }];
  assert.deepEqual(interleave([a, b]).map((h) => h.chunk_id), ["1", "9", "2", "3"]);
  const site = { chunk_id: "W", collection_id: "websites", title: "Pythias Oasis", text: "Adapted by OOI from Philip, et al., 2023, doi: 10.1126/sciadv.add6688.",
    citations: [{ source_id: "W", url: "https://oceanobservatories.org/x" }] };
  assert.deepEqual(paperKeys([site]), ["10.1126/sciadv.add6688"]);
  const passage = { chunk_id: "P1", collection_id: "literature_fulltext", title: "Fluid sources", text: "flow sustained for about 1500 years",
    citations: [{ source_id: "COSZO-REF-143", url: "https://doi.org/10.1126/sciadv.add6688" }] };
  assert.deepEqual(fullTextFor([site], [passage]).map((p) => p.chunk_id), ["P1"]);
});

test("long main evidence leaves the full-text passages their own room", () => {
  const main = Array.from({ length: 12 }, (_, i) => ({ chunk_id: `W${i}`, collection_id: "websites", title: `Page ${i}`, text: "w ".repeat(1500) }));
  const passage = { chunk_id: "P", collection_id: "literature_fulltext", title: "Paper", text: "the stated fact" };
  const evidence = evidencePackage([...main, passage], new Map());
  assert.ok(evidence.endsWith("Paper (scientific literature, full text)\nthe stated fact"));
  assert.ok(evidence.length < 12_000 + 200);                                            // with passages, 12,000 of main evidence
  assert.ok(evidencePackage(main, new Map()).length > 17_000);                           // without, 18,000
});

test("a question about the DAS experiments in general is given each experiment's record", async (t) => {
  assert.ok(isDasOverview("what DAS experiments were done here"));
  assert.ok(!isDasOverview("what did the 2021 DAS experiment record"));                   // names one
  assert.ok(!isDasOverview("How does DAS detect whales?"));
  assert.ok(!isDasOverview("From the 4-day OOI ocean-bottom DAS experiment, how many oceanic earthquakes per year could the DAS detect?"));
  assert.ok(isDasOverview("Which DAS datasets are available?"));
  assert.deepEqual(DAS_EXPERIMENTS.map((e) => e.key), ["das21", "das24", "das25"]);
  const { default: worker } = await import("../src/index.js");
  const record = (year) => ({ chunk_id: `PI-${year}`, collection_id: "pi_portal", title: `${year} RCA Distributed Acoustic Sensing experiment data availability and routing`,
    text: `${year} RCA Distributed Acoustic Sensing experiment`, citations: [{ source_id: `PI-${year}`, url: `http://piweb.ooirsn.uw.edu/${year}/` }] });
  const searched = [];
  let prompt = "";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "W", collection_id: "websites", title: "DAS on the RCA", text: "DAS page" }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/search")) {
      const query = JSON.parse(init.body).query; searched.push(query);
      return Response.json({ hits: [record(query.startsWith("2021") ? "2021" : query.startsWith("2024") ? "2024" : "2025–2026")] });
    }
    if (u.endsWith("/v1/passages")) throw new Error("an overview asks no full text");
    prompt = JSON.parse(init.body).contents[0].parts[0].text;
    return Response.json({ candidates: [{ content: { parts: [{ text: "Three [1, 2, 3]." }] } }] });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "what DAS experiments were done here" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" });
  assert.equal(res.status, 200);
  assert.equal(searched.length, 3);
  for (const year of ["2021", "2024", "2025–2026"]) assert.ok(prompt.includes(`${year} RCA Distributed Acoustic Sensing experiment data availability`));
});

test("an overview of the DAS experiments counts the 2025–26 datasets as one experiment", () => {
  const prompt = answerPrompt({ question: "what DAS experiments were done here", evidence: "e", sources: [], mode: "research" });
  assert.match(prompt, /DAS21, the 2021[\s\S]*DAS24, the 2024[\s\S]*DAS25, the 2025–2026[\s\S]*not an experiment of its own/);
  assert.doesNotMatch(answerPrompt({ question: "How does DAS detect whales?", evidence: "e", sources: [], mode: "research" }), /DAS experiments are/);
});

test("an Axial count understands a day as people write it", () => {
  const now = new Date("2026-10-22T18:00:00Z");
  for (const q of ["how many earthquakes occurs at axial seamount on October 1sr 2026", "How many earthquakes at Axial on Oct 1?",
    "number of earthquakes at Axial on 1 October 2026", "how many earthquakes at axial on 10/1/2026", "Count earthquakes at Axial on 2026-10-01"]) {
    assert.equal(axialDayWindow(q, { now }).day, "2026-10-01", q);
  }
  assert.equal(axialDayWindow("How many earthquakes at Axial on Nov 3?", { now }).day, "2025-11-03");   // the latest Nov 3 so far
  assert.equal(axialDayWindow("How many earthquakes at Axial on February 30 2026?", { now }), null);
  assert.equal(axialDayWindow("How many earthquakes at Axial since 2015?", { now }), null);
  assert.ok(axialDayWindow("How many earthquakes at Axial on December 1 2026?", { now }).future);
});

test("an Axial count says when the catalog has not located the day yet, or only part of it, and applies a magnitude floor", async (t) => {
  assert.equal(locatedUntil("Catalog last updated at 22-Oct-2026 22:32:06 UTC with locations up to 08-Oct-2026 11:00:00 UTC").toISOString(), "2026-10-08T11:00:00.000Z");
  assert.equal(locatedUntil("no such line"), null);
  assert.deepEqual(magnitudeFloor("How many earthquakes above magnitude 2 at Axial yesterday?"), { value: 2, inclusive: false });
  assert.deepEqual(magnitudeFloor("Axial earthquakes M2.5+ on 2026-09-23"), { value: 2.5, inclusive: true });
  assert.equal(magnitudeFloor("How many earthquakes at Axial yesterday?"), null);
  const { default: worker } = await import("../src/index.js");
  let reach = "08-Oct-2026 11:00:00";
  t.mock.method(globalThis, "fetch", async (url) => String(url) === "http://axial.ocean.washington.edu"
    ? new Response(`Catalog last updated at 22-Oct-2026 22:32:06 UTC with locations up to ${reach} UTC`)
    : new Response(hypo71, { status: 200 }));
  const ask = async (query) => (await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" }, body: JSON.stringify({ query }),
  }), {})).json();
  const notYet = await ask("How many earthquakes at Axial on 2026-10-21?");
  assert.match(notYet.answer, /cannot count .* yet: its earthquake locations reach only 2026-10-08 11:00 UTC/);
  assert.equal(notYet.events.length, 0);
  reach = "23-Sep-2026 12:00:00";                                                         // the day only half located
  const partial = await ask("How many earthquakes at Axial on 2026-09-23?");
  assert.match(partial.answer, /^There were \d+ Axial Seamount earthquakes .* reach only 2026-09-23 12:00 UTC so far, so this counts the day only up to then\.$/);
  reach = "24-Sep-2026 21:00:00";
  const all = (await ask("How many earthquakes at Axial on 2026-09-23?")).events;
  const big = await ask("How many earthquakes above magnitude 1 at Axial on 2026-09-23?");
  assert.equal(big.events.length, all.filter((e) => e.mag > 1).length);
  assert.ok(big.events.length < all.length);
  assert.match(big.answer, new RegExp(`^There were ${big.events.length} Axial Seamount earthquakes of magnitude above 1 \\(of ${all.length} in all\\)`));
});

test("a status question is answered from the instrument's live check, cited as the instrument", async (t) => {
  assert.ok(isStatusQuestion("is the pressure gauge at slope base operational"));
  assert.ok(!isStatusQuestion("What does the pressure gauge at Slope Base measure?"));
  const record = { chunk_id: "I-1", collection_id: "instruments", title: "Oregon Slope Base Seafloor Pressure Sensor",
    text: "Reference designator RS01SLBS-MJ01A-06-PRESTA101.", citations: [{ source_id: "I-1", url: "https://ooinet.oceanobservatories.org/x" }] };
  assert.equal(refdesOf(record), "RS01SLBS-MJ01A-06-PRESTA101");
  assert.match(liveStatusHit(record, "RS01SLBS-MJ01A-06-PRESTA101", { untracked: true }).text, /does not track it/);
  const { default: worker } = await import("../src/index.js");
  let prompt = "";
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [record], neighbors: [], tool_hints: [] });
    if (u === "https://gw.example/status/RS01SLBS-MJ01A-06-PRESTA101") {
      return Response.json({ refdes: "RS01SLBS-MJ01A-06-PRESTA101", status: "OPERATIONAL", data: { code: "GOOD", checkedAt: "2026-10-22T23:00:10Z" }, evidenceMode: "live" });
    }
    prompt = JSON.parse(init.body).contents[0].parts[0].text;
    return Response.json({ candidates: [{ content: { parts: [{ text: "Yes, it is operating [1]." }] } }] });
  });
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "is the pressure gauge at slope base operational" }),
  }), { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g", ATLAS_MAP_GATEWAY_ORIGIN: "https://gw.example" });
  const data = await res.json();
  assert.match(prompt, /^Live status: Oregon Slope Base Seafloor Pressure Sensor \| sources: \[1\]\n.*is operating, checked live by Nereus.*2026-10-22 23:00 UTC\) is GOOD\./m);
  assert.match(prompt, /checked against the live monitor moments ago/);
  assert.equal(data.answer_citations.length, 1);                                       // the live check cites the instrument
});

test("a status question is searched for its instrument, and only that type's records are checked live", () => {
  assert.equal(searchText(statusSearch("Are the CTDs at Southern Hydrate Ridge online?")), "the CTD at Southern Hydrate Ridge");
  assert.equal(searchText("Where are the ADCPs?"), "Where are the ADCP?");
  assert.equal(searchText("What does DAS record?"), "What does distributed acoustic sensing record?");   // DAS is no plural
  const ctd = askedType("Is the CTD at Southern Hydrate Ridge online?");
  assert.ok(ctd.some((t) => t.test("MARUM CTD-DO instrument")) && !ctd.some((t) => t.test("Southern Hydrate Ridge Summit ADCP")));
  assert.deepEqual(liveTargetOf({ title: "Axial Seamount Eastern Caldera Seismic Station AXEC1 (description)" }), { kind: "waveform", id: "OO.AXEC1" });
  assert.deepEqual(liveTargetOf({ text: "CTD RS01SBPS-PC01A-4A-CTDPFA103" }), { kind: "status", id: "RS01SBPS-PC01A-4A-CTDPFA103" });
  assert.equal(liveTargetOf({ title: "AXIAL SEAMOUNT" }), null);
  const wave = liveStatusHit({ title: "Station AXEC1 (description)" }, "OO.AXEC1",
    { kind: "waveform", recording: true, channel: "EHZ", rate: 200, latestMs: Date.UTC(2026, 9, 22, 23, 12), delayMinutes: 2 });
  assert.equal(wave.text, "Station AXEC1 (OO.AXEC1) is recording, checked live at EarthScope: its newest waveform (EHZ, 200 samples/s) is from 2026-10-22 23:12 UTC, 2 min behind real time.");
});

test("Auto answers on the paid fallback only after Gemini and Groq refuse, and never asks OpenRouter", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const asked = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "I", collection_id: "instruments", title: "Gauge", text: "A gauge." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    asked.push(new URL(u).hostname);
    if (u.startsWith("https://api.openai.com/")) return Response.json({ output_text: "A gauge [1]." });
    return Response.json({ error: "rate limited" }, { status: 429 });
  });
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g", GROQ_API_KEY: "q",
    OPENROUTER_API_KEY: "o", OPENAI_API_KEY: "p", AUTO_FALLBACK_OPENAI_MODEL: "gpt-5.4-mini" };
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" }, body: JSON.stringify({ query: "What does the gauge measure?" }),
  }), env);
  const data = await res.json();
  assert.equal(data.answer_model, "OpenAI gpt-5.4-mini");
  assert.equal(asked.at(-1), "api.openai.com");
  assert.ok(asked.includes("generativelanguage.googleapis.com") && asked.includes("api.groq.com"));
  assert.ok(!asked.includes("openrouter.ai"));          // OpenRouter is no longer a route, even with a key
});

test("the OOI model answers through its relay with the relay token, picked or first in Auto", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const asked = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "I", collection_id: "instruments", title: "Gauge", text: "A gauge." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    asked.push(new URL(u).hostname);
    if (u === "https://relay.example/v1/chat/completions") {
      assert.equal(init.headers.authorization, "Bearer r");
      return Response.json({ choices: [{ message: { content: "A gauge [1]." } }] });
    }
    return Response.json({ error: "rate limited" }, { status: 429 });
  });
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g", GROQ_API_KEY: "q",
    OPENROUTER_API_KEY: "o", OOI_RELAY_ORIGIN: "https://relay.example/", OOI_RELAY_TOKEN: "r" };
  const ask = (model) => worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "What does the gauge measure?", model }),
  }), env).then((res) => res.json());
  assert.equal((await ask("ooi-gemma-4-26b")).answer_model, "OOI Gemma 4 26B-A4B");
  assert.deepEqual(asked, ["relay.example"]);
  asked.length = 0;
  assert.equal((await ask("auto")).answer_model, "OOI Gemma 4 26B-A4B");
  assert.deepEqual(asked, ["relay.example"]);
});

test("the OOI model goes through the VPC binding when it answers, not the quick-tunnel URL", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const asked = [];
  const relayed = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "I", collection_id: "instruments", title: "Gauge", text: "A gauge." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    asked.push(new URL(u).hostname);
    return Response.json({ error: "rate limited" }, { status: 429 });
  });
  const OOI_RELAY = { fetch: async (url, init) => {
    relayed.push([String(url), init.headers.authorization]);
    return Response.json({ choices: [{ message: { content: "A gauge [1]." } }] });
  } };
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g",
    OOI_RELAY, OOI_RELAY_ORIGIN: "https://old-quick-tunnel.example", OOI_RELAY_TOKEN: "r" };
  for (const model of ["ooi-gemma-4-26b", "auto"]) {
    const res = await worker.fetch(new Request("https://w.example/v1/answer", {
      method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
      body: JSON.stringify({ query: "What does the gauge measure?", model }),
    }), env).then((r) => r.json());
    assert.equal(res.answer_model, "OOI Gemma 4 26B-A4B");
  }
  assert.deepEqual(relayed, Array(2).fill(["http://127.0.0.1:8787/v1/chat/completions", "Bearer r"]));
  assert.deepEqual(asked, []);
});

test("a quick tunnel's URL answers when the named tunnel behind the VPC binding is down", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const asked = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "I", collection_id: "instruments", title: "Gauge", text: "A gauge." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    asked.push(u);
    return Response.json({ choices: [{ message: { content: "A gauge [1]." } }] });
  });
  const OOI_RELAY = { fetch: async () => { throw new Error("no tunnel connector"); } };
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", OOI_RELAY,
    OOI_RELAY_ORIGIN: "https://quick.example/", OOI_RELAY_TOKEN: "r" };
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "What does the gauge measure?", model: "ooi-gemma-4-26b" }),
  }), env).then((r) => r.json());
  assert.equal(res.answer_model, "OOI Gemma 4 26B-A4B");
  assert.deepEqual(asked, ["https://quick.example/v1/chat/completions"]);
});

test("Auto moves on to Gemini when the OOI relay is down", async (t) => {
  const { default: worker } = await import("../src/index.js");
  const asked = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "I", collection_id: "instruments", title: "Gauge", text: "A gauge." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    asked.push(new URL(u).hostname);
    if (u.startsWith("https://relay.example/")) return new Response("tunnel gone", { status: 530 });
    return Response.json({ candidates: [{ content: { parts: [{ text: "A gauge [1]." }] } }] });
  });
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g",
    OOI_RELAY_ORIGIN: "https://relay.example", OOI_RELAY_TOKEN: "r" };
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "What does the gauge measure?", model: "auto" }),
  }), env).then((r) => r.json());
  assert.equal(res.answer_model, "gemini-2.5-flash");
  assert.deepEqual(asked, ["relay.example", "generativelanguage.googleapis.com"]);
});

test("a research answer names what is missing only when something is", () => {
  const prompt = answerPrompt({ question: "Which eruptions were on the south rift?", evidence: "e", sources: [], mode: "research" });
  assert.match(prompt, /If the evidence leaves part of the question unanswered, say in one short closing section what is missing/);
  assert.match(prompt, /When the evidence answers the question fully, add no such section/);
  assert.doesNotMatch(prompt, /State clearly what the evidence does not establish/);
  assert.match(prompt, /never present a partial sum as the total/);
});

test("a network-wide question about one instrument type is given every record of that type", () => {
  assert.equal(typeInventory("which CTD sensors are in the network").search, "CTD instrument");
  assert.equal(typeInventory("Which seismometers are on the RCA?").search, "seismometer seismic station instrument");
  assert.equal(typeInventory("which CTDs are at Axial?"), null);                 // a site: the inventory search keeps to it
  assert.equal(typeInventory("What does a CTD measure?"), null);                  // not a listing
  assert.equal(typeInventory("what DAS experiments were done here"), null);       // the DAS experiments have their own
  assert.equal(typeInventory("What is Pythia's Oasis, and which fault is thought to drain the overpressured reservoir?"), null);
  assert.equal(typeInventory("At about what temperature and pressure do subseafloor reactions buffer the fluid?"), null);
  assert.equal(typeInventory("At what depths were the hydrophones?"), null);
  assert.ok(typeInventory("which CTD sensors are in the network").record.test("Oregon Shelf Benthic Package CTD"));
});

test("a question about the papers that used a sensor finds the codes papers name it by", () => {
  assert.ok(isPaperUsageQuestion("What papers used AXEC2 and AXEC1?"));
  assert.ok(isPaperUsageQuestion("Which studies used the Slope Base pressure gauge?"));
  assert.ok(!isPaperUsageQuestion("What does the AXEC1 seismometer record?"));
  assert.ok(!isPaperUsageQuestion("Which multibeam echosounder was used to map bubble plumes in the 2016 time-series study?"));
  assert.equal(instrumentSearch("Which studies used the Slope Base pressure gauge?"), "Slope Base pressure gauge");
  assert.deepEqual(instrumentCodes(["What papers used AXEC2 and AXEC1?"]), ["AXEC2", "AXEC1"]);
  assert.deepEqual(instrumentCodes(["Axial Seamount Eastern Caldera Seismic Station AXEC2\ncanonical identifier EARTHSCOPE-OO-AXEC2"]), ["AXEC2"]);
  assert.deepEqual(instrumentCodes(["ASHES Hydrothermal Field CTD\nCanonical identifier: RS03ASHS-MJ03B-10-CTDPFB304"]), ["RS03ASHS-MJ03B-10-CTDPFB304", "CTDPFB304", "MJ03B"]);
  assert.deepEqual(instrumentCodes(["ASHES Cabled Observatory Vent Imaging Sonar (COVIS)\nsonar"]), ["COVIS"]);
  assert.deepEqual(instrumentCodes(["Canonical identifier: RS01SLBS-MJ01A-06-PRESTA101"]), ["RS01SLBS-MJ01A-06-PRESTA101", "PRESTA101", "MJ01A"]);
  assert.equal(askedPlace("Which studies used the Slope Base pressure gauge?"), "Slope Base");
  assert.equal(askedPlace("What papers used AXEC2 and AXEC1?"), "");
  assert.equal(askedPlace("What papers used COVIS data?"), "");
  assert.deepEqual(questionCodes("Which papers used the BOTPT at Axial?"), ["BOTPT"]);
  assert.deepEqual(questionCodes("Which OOI RCA papers used AXEC2?"), ["AXEC2"]);
  assert.equal(askedPlace("Which papers used the BOTPT at Axial?"), "Axial");
});

const ASSETS = {
  instruments: [
    { refdes: "RS03CCAL-MJ03F-05-BOTPTA301", name: "Axial Seamount Central Caldera Seafloor Pressure", instrument: "Bottom Pressure and Tilt", site: "Central Caldera", codes: ["BOTPT", "BOTP"], calibration: false },
    { refdes: "RS03CCAL-MJ03F-09-SCPRAA301", name: "Central Caldera Self-Calibrating Pressure Recorder", instrument: "Self-Calibrating Pressure Recorder", site: "Central Caldera", codes: ["SCPRA", "SCPR"], calibration: false },
    { refdes: "RS03AXBS-LJ03A-12-CTDPFB301", name: "Axial Seamount Base Seafloor CTD", instrument: "CTD", site: "Axial Base Seafloor", codes: ["CTDPF", "CTDP"], calibration: true },
    { refdes: "RS03AXPD-DP03A-01-CTDPFL304", name: "Axial Seamount Deep Profiler CTD Profiler", instrument: "CTD", site: "Axial Base Deep Profiler Mooring", codes: ["CTDPF", "CTDP"], calibration: true },
    { refdes: "RS01SLBS-LJ01A-12-CTDPFB101", name: "Oregon Slope Base Seafloor CTD", instrument: "CTD", site: "Oregon Slope Base Seafloor", codes: ["CTDPF", "CTDP"], calibration: true },
    { refdes: "RS01SUM1-LJ01B-12-VEL3DB104", name: "Southern Hydrate Ridge Flank 3D Current Meter", instrument: "3-D Single Point Velocity Meter", site: "Southern Hydrate Summit 1 Seafloor", codes: ["VEL3D", "VEL3"], calibration: false },
  ],
  sites: { "Central Caldera": "ooi_assets_site_Central_Caldera", "Southern Hydrate Summit 1 Seafloor": "ooi_assets_site_Southern_Hydrate_Summit_1_Seafloor" },
  types: { CTD: "ooi_assets_type_CTD" },
  cruise_years: { 2025: "ooi_assets_cruises_2025" },
  depth_bands: [{ low: 2000, high: null, id: "deep" }, { low: 1000, high: 2000, id: "mid" }, { low: 200, high: 1000, id: "upper" }, { low: null, high: 200, id: "shallow" }],
};

test("an asset-metadata question asks for the records the directory names: the instrument, its calibrations, a type, cruise year or depth band", () => {
  assert.deepEqual(assetChunkIds("what is the serial number of the SCPR at axial seamount?", ASSETS), ["ooi_assets_RS03CCAL-MJ03F-09-SCPRAA301"]);
  assert.deepEqual(assetChunkIds("When was the BOTPT at Central Caldera last recovered?", ASSETS), ["ooi_assets_RS03CCAL-MJ03F-05-BOTPTA301"]);
  assert.deepEqual(assetChunkIds("What are the calibration coefficients of the Axial Base CTD?", ASSETS),
    ["ooi_assets_RS03AXBS-LJ03A-12-CTDPFB301", "ooi_assets_calibration_RS03AXBS-LJ03A-12-CTDPFB301"]);
  // Up to three instances, each one's record; more, the type's record (twelve CTDs in the real directory).
  assert.deepEqual(assetChunkIds("Which CTDs are Sea-Bird SBE 16plus?", ASSETS),
    ["ooi_assets_RS03AXBS-LJ03A-12-CTDPFB301", "ooi_assets_RS03AXPD-DP03A-01-CTDPFL304", "ooi_assets_RS01SLBS-LJ01A-12-CTDPFB101"]);
  assert.deepEqual(assetChunkIds("How many deployments has the Axial Base deep profiler CTD had?", ASSETS), ["ooi_assets_RS03AXPD-DP03A-01-CTDPFL304"]);
  const many = { ...ASSETS, instruments: [...ASSETS.instruments, ...["A", "B"].map((x) => ({ ...ASSETS.instruments[2], refdes: `RS03ECAL-MJ03E-12-CTDPFB30${x}`, site: "Eastern Caldera" }))] };
  assert.deepEqual(assetChunkIds("Which CTDs are Sea-Bird SBE 16plus?", many), ["ooi_assets_type_CTD"]);
  assert.deepEqual(assetChunkIds("Which instruments were deployed on Visions 25?", ASSETS), ["ooi_assets_cruises_2025"]);
  assert.deepEqual(assetChunkIds("Which instruments are deeper than 2500 m?", ASSETS), ["deep"]);
  assert.deepEqual(assetChunkIds("Which instruments are deeper than 1500 m?", ASSETS), ["deep", "mid"]);
  assert.deepEqual(assetChunkIds("Which instruments at Southern Hydrate Ridge have been redeployed most often?", ASSETS),
    ["ooi_assets_site_Southern_Hydrate_Summit_1_Seafloor"]);
  assert.deepEqual(assetChunkIds("serial number of RS01SLBS-LJ01A-12-CTDPFB101", ASSETS), ["ooi_assets_RS01SLBS-LJ01A-12-CTDPFB101"]);
});

test("other questions ask for no asset records", () => {
  for (const q of ["which seismometers doesnt have 0 degree azimuth orientation", "what is the model of the 2015 eruption", "how many earthquakes today"]) {
    assert.deepEqual(assetChunkIds(q, ASSETS), [], q);
  }
  assert.equal(isAssetQuestion("When was the BOTPT last recovered?"), true);
  assert.equal(isAssetQuestion("Which CTDs are Sea-Bird?"), true);
});

test("an asset question fetches the directory's records by id and leads the evidence with them", async (t) => {
  const { default: worker } = await import("../src/index.js");
  let asked;
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const u = String(url);
    if (u.endsWith("/v1/context")) return Response.json({ hits: [{ chunk_id: "W", collection_id: "websites", title: "Central Caldera", text: "A page." }], neighbors: [], tool_hints: [] });
    if (u.endsWith("/v1/passages")) return Response.json({ hits: [] });
    if (u.endsWith("/v1/chunks")) {
      asked = JSON.parse(init.body);
      return Response.json({ hits: [{ chunk_id: asked.chunk_ids[0], collection_id: "ooi_asset_management", title: "SCPR", text: "serial number 001/C",
        citations: [{ source_id: "S", title: "Deploy", url: "https://github.com/oceanobservatories/asset-management" }] }] });
    }
    return Response.json({ candidates: [{ content: { parts: [{ text: "Serial 001/C [1]." }] } }] });
  });
  const env = { ATLAS_API_KEY: "k", ATLAS_API_ORIGIN: "https://api.example", GEMINI_API_KEY: "g" };
  const res = await worker.fetch(new Request("https://w.example/v1/answer", {
    method: "POST", headers: { origin: "https://coszo.org", "content-type": "application/json" },
    body: JSON.stringify({ query: "What is the serial number of the SCPR at Axial Seamount?", model: "gemini-2.5-flash" }),
  }), env).then((r) => r.json());
  assert.deepEqual(asked, { collection_id: "ooi_asset_management", chunk_ids: ["ooi_assets_RS03CCAL-MJ03F-09-SCPRAA301"] });
  assert.equal(res.answer_citations[0].url, "https://github.com/oceanobservatories/asset-management");
});
