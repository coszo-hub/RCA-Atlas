import { expect, test } from "@playwright/test";
import { mockGateway } from "./mocks.js";

// Ask Atlas with the four demo questions, answered from captured Worker responses (e2e/mocks.js): the evidence rises
// on the map, and hovering, clicking, stepping and Escape drive it. window.__atlas.evidence() reports what is on screen.
const ready = page => page.waitForFunction(() => window.__atlas?.scene?.frame?.dist > 0, null, { timeout: 30_000 });
const evidence = page => page.evaluate(() => window.__atlas.evidence());
const target = page => page.evaluate(() => window.__atlas.scene.controls.target.toArray());
const mute = page => page.evaluate(() => window.__atlas.scene.targets.mute);
async function ask(page, q) {
  await page.getByRole("textbox", { name: /Ask/ }).fill(q);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}
async function open(page, opts) {
  await mockGateway(page, opts);
  await page.goto("/");
  await ready(page);
}
const risen = page => page.waitForFunction(() => { const e = window.__atlas.evidence(); return e.shown && e.spikes.every(s => s.height > 0) && e.spikes.length > 0; }, null, { timeout: 8000 });

test("instruments: numbered spikes rise; hover grows one, click flies there with a card, ← / → tour, Escape clears", async ({ page }) => {
  await open(page, { askDelay: 1500 });   // long enough to see the map wait for the answer
  await page.screenshot({ path: "e2e/screens/ask-empty.png" });
  const before = await target(page);
  await ask(page, "What's been measuring Axial's inflation before the next eruption?");
  await expect(page.getByText("Reading the corpus…")).toBeVisible();
  await page.screenshot({ path: "e2e/screens/ask-reading.png" });
  expect((await evidence(page)).shown).toBe(false);   // the map waits for the answer
  await expect(page.getByRole("table", { name: "Evidence on the map" })).toBeVisible();
  await risen(page);
  await page.waitForTimeout(1600);   // the stagger and the framing flight
  let ev = await evidence(page);
  expect(ev.spikes.map(s => s.ns)).toEqual([[1], [2], [3], [4], [5]]);
  expect(await mute(page)).toBe(0.55);
  expect(Math.hypot(...(await target(page)).map((v, i) => v - before[i]))).toBeGreaterThan(5);   // framed on the evidence
  await page.screenshot({ path: "e2e/screens/ask-inflation-risen.png" });

  await page.getByRole("button", { name: /^Source 2:/ }).hover();
  await page.waitForTimeout(500);
  ev = await evidence(page);
  expect(ev.hover).toBe(2);
  expect(ev.spikes[1].height / ev.spikes[0].height).toBeGreaterThan(1.3);

  await page.getByRole("row", { name: /^2 BOTPTA303/ }).click();
  await page.waitForTimeout(1800);
  ev = await evidence(page);
  expect(ev.active).toBe(2);
  expect(ev.card.text).toContain("International District Hydrothermal Field 2 Seafloor Pressure");
  expect(ev.card.text).toContain("RS03INT2-MJ03D-06-BOTPTA303");
  const loc = ev.located.find(x => x.n === 2), t = await target(page);
  expect(Math.hypot(t[0] - (loc.lon + 127.15) * 111.32 * Math.cos(45.15 * Math.PI / 180), t[2] + (loc.lat - 45.15) * 111.13)).toBeLessThan(0.5);
  await page.mouse.move(900, 900);
  await page.screenshot({ path: "e2e/screens/ask-inflation-card.png" });

  await page.getByRole("button", { name: "Live data →" }).click();
  const site = page.getByRole("complementary", { name: /Axial International District · MJ03D site/ });
  await expect(site.getByRole("heading", { name: "International District Hydrothermal Field 2 Seafloor Pressure" })).toBeVisible();
  await site.getByRole("button", { name: /^Close/ }).click();

  await page.locator("body").click({ position: { x: 1000, y: 990 } });
  await page.keyboard.press("ArrowRight");
  expect((await evidence(page)).active).toBe(3);
  await page.keyboard.press("ArrowLeft");
  expect((await evidence(page)).active).toBe(2);
  await page.keyboard.press("Escape");
  ev = await evidence(page);
  expect(ev.card).toBeNull();
  expect(ev.shown).toBe(true);
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
  expect((await evidence(page)).shown).toBe(false);
  expect(await mute(page)).toBe(0);
});

test("off-screen evidence gets an edge chip; clicking it flies there", async ({ page }) => {
  await open(page);
  await ask(page, "What's been measuring Axial's inflation before the next eruption?");
  await risen(page);
  await page.getByRole("row", { name: /^2 BOTPTA303/ }).click();
  await page.waitForTimeout(1800);
  const ev = await evidence(page);
  const chip = ev.chips.find(c => c.ns.includes(5));
  expect(chip).toBeTruthy();
  expect(chip.x).toBeGreaterThanOrEqual(412);   // on the free area's edge, not under the panel
  await page.locator(".ev-chip", { hasText: "BOTPTA301" }).filter({ has: page.locator("b", { hasText: /^5$/ }) }).click();
  await page.waitForTimeout(1800);
  const after = await evidence(page);
  expect(after.active).toBe(5);
  expect(after.chips.some(c => c.ns.includes(5))).toBe(false);
});

test("inventory from the deployed Worker (no [n], no excerpts): sensors and sites, merged by location", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "What instruments are on Southern Hydrate Ridge?" }).click();
  await risen(page);
  await page.waitForTimeout(2600);
  const ev = await evidence(page);
  expect(ev.located).toHaveLength(15);
  expect(ev.spikes.flatMap(s => s.ns).sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
  expect(ev.spikes.length).toBeLessThan(15);
  await page.getByRole("row", { name: /^5 HYS12/ }).click();
  await page.waitForTimeout(1800);
  expect((await evidence(page)).card.text).toContain("Southern Hydrate Ridge Summit Seismic Station HYS12");
  await page.mouse.move(900, 900);
  await page.screenshot({ path: "e2e/screens/ask-hydrate.png" });
});

test("data access: DAS routes glow as cables; the sited instrument is a spike", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "How do I get the DAS data?" }).click();
  await risen(page);
  await page.waitForTimeout(2200);
  let ev = await evidence(page);
  expect(ev.cables.map(c => c.ns[0])).toEqual([1, 2]);
  expect(ev.cables[0].layers.every(id => id.startsWith("multidas"))).toBe(true);
  expect(ev.spikes.map(s => s.ns)).toEqual([[3]]);
  await page.screenshot({ path: "e2e/screens/ask-das-overview.png" });
  await page.getByRole("row", { name: /^1 MultiDAS/ }).click();
  await page.waitForTimeout(1800);
  ev = await evidence(page);
  expect(ev.card.text).toContain("DAS25 MultiDAS");
  await page.mouse.move(900, 900);
  await page.screenshot({ path: "e2e/screens/ask-das.png" });
});

test("events: the day's hypocentres light up beneath the glass caldera; Escape restores the terrain", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "How many earthquakes at Axial yesterday?" }).click();
  await expect(page.getByRole("table", { name: "Earthquakes on the map" })).toBeVisible();
  await page.waitForTimeout(3600);
  let ev = await evidence(page);
  expect(ev.quakes).toBe(71);
  expect(await page.evaluate(() => window.__atlas.scene.targets.see)).toBe(1);
  await expect(page.getByRole("group", { name: "Subsurface" }).getByRole("button", { name: "On" })).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "e2e/screens/ask-quakes-overview.png" });
  await page.getByRole("row", { name: /^5 02:02:21/ }).click();
  await page.waitForTimeout(1800);
  ev = await evidence(page);
  expect(ev.card.text).toContain("Earthquake 5 · 02:02:21 UTC");
  await page.mouse.move(900, 900);
  await page.screenshot({ path: "e2e/screens/ask-quakes.png" });
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__atlas.scene.targets.see)).toBe(0);
});

test("broad science: documents only; the map is not dimmed and says so", async ({ page }) => {
  await open(page);
  await page.waitForTimeout(800);
  const before = await target(page);
  await page.getByRole("button", { name: "What's known about the 2015 Axial eruption?" }).click();
  await expect(page.getByText("No mapped instruments in this answer.")).toBeVisible();
  await page.waitForTimeout(600);
  expect((await evidence(page)).spikes).toEqual([]);
  expect(await mute(page)).toBe(0);
  (await target(page)).forEach((v, i) => expect(v).toBeCloseTo(before[i], 2));
  await expect(page.getByRole("link", { name: /Geodetic Monitoring at Axial Seamount.*↗$/ }).first()).toBeVisible();
  await page.screenshot({ path: "e2e/screens/ask-eruption.png" });
});

test("the Worker down: one line with Retry, and the map is untouched", async ({ page }) => {
  await open(page);
  await ask(page, "Where can I download the BPR record?");
  await expect(page.getByText("Answer temporarily unavailable (HTTP 503).")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  expect((await evidence(page)).shown).toBe(false);
});

test("a new question sinks the old spikes before the new rise; an earlier answer shows its evidence again", async ({ page }) => {
  await open(page);
  await ask(page, "What's been measuring Axial's inflation before the next eruption?");
  await risen(page);
  await ask(page, "How do I get the DAS data?");
  await page.waitForFunction(() => window.__atlas.evidence().cables.length === 2, null, { timeout: 8000 });
  await page.getByRole("button", { name: /^Show the evidence for: What's been measuring/ }).click();
  await page.waitForFunction(() => window.__atlas.evidence().spikes.length === 5, null, { timeout: 8000 });
});

test("reduced motion: spikes stand at full height at once", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  await open(page, { askDelay: 0 });
  await ask(page, "What's been measuring Axial's inflation before the next eruption?");
  await expect(page.getByRole("table", { name: "Evidence on the map" })).toBeVisible();
  await page.waitForTimeout(150);
  const ev = await evidence(page);
  expect(ev.spikes.every(s => s.height > 0)).toBe(true);
  await context.close();
});
