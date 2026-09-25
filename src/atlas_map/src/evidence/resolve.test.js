import { describe, expect, it } from "vitest";
import { askBundle } from "../test/fixtures/ask/bundle.js";
import das from "../test/fixtures/ask/das.json";
import eruption from "../test/fixtures/ask/eruption.json";
import hydrate from "../test/fixtures/ask/hydrate.json";
import inflation from "../test/fixtures/ask/inflation.json";
import inflation2 from "../test/fixtures/ask/inflation.v2.json";
import quakes from "../test/fixtures/ask/quakes.json";
import quakes2 from "../test/fixtures/ask/quakes.v2.json";
import { readableExcerpt, resolveEvidence, shortSite } from "./resolve.js";

const bundle = askBundle();
const byN = (ev, n) => ev.located.find(x => x.n === n);

describe("resolveEvidence: captured answers from the deployed Worker", () => {
  it("instrument inventory: INSTRUMENT ids become sensors in their family colour, pages naming a site become sites", () => {
    const ev = resolveEvidence(hydrate, bundle);
    expect(ev.located.map(x => x.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
    expect(byN(ev, 1)).toMatchObject({ kind: "site", id: "southern-hydrate-ridge", family: null, label: "Southern Hydrate Ridge" });
    expect(byN(ev, 2)).toMatchObject({ kind: "site", id: "southern-hydrate-ridge" });   // "Southern Hydrate Ridge VISIONS ’14"
    expect(byN(ev, 3)).toMatchObject({ kind: "sensor", id: "RS01SUM1-LJ01B-05-HYDLFA104", family: "acoustic", color: "#d55181",
      code: "HYDLFA104", site: "Hydrate Ridge", depth: 780, lat: 44.5664, lon: -125.1467, siteId: "southern-hydrate-ridge" });
    expect(byN(ev, 5)).toMatchObject({ kind: "sensor", id: "EARTHSCOPE-OO-HYS12", code: "HYS12" });
    // No recorded position: placed at its site.
    expect(byN(ev, 15)).toMatchObject({ kind: "sensor", id: "RS01SUM2-MJ01B-15-OBSBBA102", lon: -125.14792, lat: 44.569111 });
    expect(ev.documents).toEqual([]);
    expect(ev.events).toBeNull();
  });

  it("without an excerpt, a sensor is described from the bundle and keeps the hit title", () => {
    const ev = resolveEvidence(hydrate, bundle);
    expect(byN(ev, 3)).toMatchObject({ excerpt: "HTI 90-U · hydrophone", quote: false });
    expect(byN(ev, 1)).toMatchObject({ excerpt: "", quote: false });
    expect(byN(ev, 3).title).toBe("Southern Hydrate Ridge Flank Low-Frequency Hydrophone");
    expect(byN(ev, 3).sourceUrl).toBe("https://oceanobservatories.org/site/rs01sum1/");
  });

  it("data access: DAS portal routes become glowing cables; a PI portal route for a sited instrument is that sensor", () => {
    const ev = resolveEvidence(das, bundle);
    expect(byN(ev, 1)).toMatchObject({ kind: "cable", id: "das25-multidas", code: "MultiDAS", color: "#ffbd59" });
    expect(byN(ev, 1).layers).toEqual(expect.arrayContaining(["multidas-north-1", "multidas-south-4"]));
    expect(byN(ev, 1).layers.every(id => id.startsWith("multidas"))).toBe(true);
    expect(byN(ev, 2)).toMatchObject({ kind: "cable", id: "das24", layers: ["optodas-south-first-span"] });
    expect(byN(ev, 3)).toMatchObject({ kind: "sensor", id: "PI-COVIS" });
    expect(ev.documents.map(d => d.n)).toEqual([4, 5]);
    expect(ev.documents[1]).toMatchObject({ title: expect.stringMatching(/^DAS-N2N/), url: "https://doi.org/10.1093/gji/ggad460" });
    // a cable's anchor sits on its route
    expect(byN(ev, 1).lon).toBeLessThan(-124); expect(byN(ev, 1).lon).toBeGreaterThan(-131);
  });

  it("broad science: documents only, nothing on the map", () => {
    const ev = resolveEvidence(eruption, bundle);
    expect(ev.located).toEqual([]);
    expect(ev.documents).toHaveLength(6);
    expect(resolveEvidence(inflation, bundle).located).toEqual([]);
  });

  it("the Axial count route without events: a count, no located evidence, the catalog as further reading", () => {
    const ev = resolveEvidence(quakes, bundle);
    expect(ev.located).toEqual([]);
    expect(ev.events).toBeNull();
    expect(ev.count).toEqual({ day: "2026-09-23", tz: "UTC", today: false, n: 71 });
    expect(ev.documents[0]).toMatchObject({ n: 1, title: "Axial Seamount Earthquake Catalog" });
  });

  it("a count of the asker's day so far carries its zone, from the answer when there are no events", () => {
    const ev = resolveEvidence({ ...quakes, answer: "There have been 65 Axial Seamount earthquakes so far today, Thursday, September 24 (Pacific Daylight Time), in the live catalog.",
      tool_hints: [{ name: "axial_count_events", input_schema: { day: "2026-09-24", tz: "America/Los_Angeles", today: true } }] }, bundle);
    expect(ev.count).toEqual({ day: "2026-09-24", tz: "America/Los_Angeles", today: true, n: 65 });
  });
});

describe("resolveEvidence: the new Worker shape", () => {
  it("[n] citations keep their numbers; excerpts of instrument records read as a short description", () => {
    const ev = resolveEvidence(inflation2, bundle);
    expect(ev.located.map(x => [x.n, x.id])).toEqual([
      [1, "RS03CCAL-MJ03F-05-BOTPTA301"], [2, "RS03INT2-MJ03D-06-BOTPTA303"], [3, "RS03ECAL-MJ03E-06-BOTPTA302"],
      [4, "EARTHSCOPE-OO-AXCC1"], [5, "RS03AXBS-LJ03A-14-BOTPTA301"]]);
    expect(byN(ev, 2)).toMatchObject({ code: "BOTPTA303", site: "Intl District", family: "pressure" });
    expect(byN(ev, 1).excerpt).toBe("PMEL/Chadwick PMELcabled BPR/Tilt · pressure");
    expect(byN(ev, 1).quote).toBe(false);
    expect(ev.documents).toEqual([expect.objectContaining({ n: 6, title: "Eruption forecasts at Axial Seamount", quote: true,
      excerpt: expect.stringMatching(/^Axial Seamount was on R\/V Revelle/) })]);
  });

  it("events: time-ordered hypocentres, numbered", () => {
    const ev = resolveEvidence(quakes2, bundle);
    expect(ev.events).toHaveLength(71);
    expect(ev.events[0]).toEqual({ n: 1, time: "2026-09-23T00:08:50.930Z", lat: 45.9405, lon: -130.018833, depth_km: 0.63, mag: 0.2 });
    expect(ev.events.every((e, i) => i === 0 || e.time >= ev.events[i - 1].time)).toBe(true);
    expect(ev.count.n).toBe(71);
  });
});

describe("resolveEvidence: resolution rules", () => {
  const cite = (id, title, url = "") => ({ id, title, url });
  const hit = (sid, title, extra = {}) => ({ chunk_id: `${sid}-CHUNK`, title, citations: [{ source_id: sid, url: extra.url ?? null }], metadata: {}, ...extra });

  it("a refdes in the excerpt, an EarthScope station id, and an IRIS station URL each find their sensor", () => {
    const ev = resolveEvidence({ answer_citations: [cite("P1", "Paper one"), cite("P2", "Paper two"), cite("P3", "Station", "https://ds.iris.edu/mda/OO/AXCC1/")],
      hits: [hit("P1", "Paper one", { excerpt: "Pressure at RS03INT2-MJ03D-06-BOTPTA303 rose 20 cm." }), hit("P2", "Paper two", { metadata: { station: "station_OO_AXCC1" } }),
        hit("P3", "Station", { url: "https://ds.iris.edu/mda/OO/AXCC1/" })] }, bundle);
    expect(ev.located.map(x => [x.n, x.id])).toEqual([[1, "RS03INT2-MJ03D-06-BOTPTA303"], [2, "EARTHSCOPE-OO-AXCC1"], [3, "EARTHSCOPE-OO-AXCC1"]]);
  });

  it("several sensors at one site make a site; a site named in the excerpt is found; unknown ids are documents", () => {
    const ev = resolveEvidence({ answer_citations: [cite("A", "Two at the summit"), cite("B", "Cruise report"), cite("C", "Nothing")],
      hits: [hit("A", "Two at the summit", { excerpt: "RS01SUM2-MJ01B-12-ADCPSK101 and RS01SUM2-MJ01B-00-FLOBNC101 were recovered." }),
        hit("B", "Cruise report", { excerpt: "We dove at Axial Central Caldera and then at the vents." }), hit("C", "Nothing")] }, bundle);
    expect(ev.located.map(x => [x.n, x.kind, x.id])).toEqual([[1, "site", "southern-hydrate-ridge-summit-2"], [2, "site", "axial-seamount-central-caldera"]]);
    expect(ev.documents.map(d => d.n)).toEqual([3]);
  });

  it("a malformed response resolves to nothing", () => {
    expect(resolveEvidence({}, bundle)).toEqual({ located: [], documents: [], events: null, count: null });
    expect(resolveEvidence(null, bundle).located).toEqual([]);
  });
});

describe("helpers", () => {
  it("shortSite trims site labels to fit the table", () => {
    expect(shortSite("Axial International District · MJ03C")).toBe("Intl District");
    expect(shortSite("Axial Central Caldera")).toBe("Central Caldera");
    expect(shortSite("Axial Base · LJ03A")).toBe("Axial Base");
    expect(shortSite("Southern Hydrate Ridge Summit · HYS12")).toBe("Hydrate Ridge Summit");
    expect(shortSite("ASHES Hydrothermal Field · MJ03B")).toBe("ASHES Vent Field");
  });
  it("readableExcerpt quotes prose and summarises instrument records", () => {
    expect(readableExcerpt("Axial re-inflated 1.25 m.")).toEqual({ excerpt: "Axial re-inflated 1.25 m.", quote: true });
    expect(readableExcerpt("Instrument: X Canonical identifier: EARTHSCOPE-OO-AXCC1 Type: seismometer Projects: Regional Cabled Array Location: Axial Seamount Central Caldera Status: catalogued_instance Sensor components: not separately enumerated"))
      .toEqual({ excerpt: "seismometer", quote: false });
    expect(readableExcerpt("")).toEqual({ excerpt: "", quote: false });
  });
  it("readableExcerpt drops URLs from prose, in brackets or bare, and tidies what is left", () => {
    expect(readableExcerpt("Data for 2025–2026 RCA Distributed Acoustic Sensing experiment are available to download from DAS25 MultiDAS (http://piweb.ooirsn.uw.edu/das25/data/MultiDAS/); DAS25 OptoDAS (http://piweb.ooirsn.uw.edu/das25/data/OptoDAS/). Physical site: RCA north and south backbone cables…").excerpt)
      .toBe("Data for 2025–2026 RCA Distributed Acoustic Sensing experiment are available to download from DAS25 MultiDAS; DAS25 OptoDAS. Physical site: RCA north and south backbone cables…");
    expect(readableExcerpt("Pressure records are in the SCPR data (http://piweb.ooirsn.uw.edu/scpr/data/SCPR_Data/) , by year.").excerpt)
      .toBe("Pressure records are in the SCPR data, by year.");
    expect(readableExcerpt("https://academic.oup.com/gji/article/236/2/1026/7453669 by University of Washington user on 20 May 2026 DAS-N2N: denoising").excerpt)
      .toBe("by University of Washington user on 20 May 2026 DAS-N2N: denoising");
    expect(readableExcerpt("See www.example.org/a_very/long/path, then [https://x.org/y] and the rest.").excerpt).toBe("See, then and the rest.");
    expect(readableExcerpt("http://piweb.ooirsn.uw.edu/das/")).toEqual({ excerpt: "", quote: false });
  });
});
