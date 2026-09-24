import { expect, test } from "@playwright/test";
import { mockGateway } from "./mocks.js";

const ready = page => page.waitForFunction(() => window.__atlas?.scene?.frame?.dist > 0, null, { timeout: 30_000 });
const regionButton = (page, name) => page.getByRole("navigation", { name: "Regions" }).getByRole("button", { name: new RegExp(`^${name}`) });
async function openSensorBySearch(page, text) {
  await page.getByRole("searchbox", { name: /Search sensors and sites/ }).fill(text);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500);
}

test("fly to Axial, open a site, open a sensor, see a chart", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.screenshot({ path: "e2e/screens/01-overview.png" });
  await regionButton(page, "Axial Seamount").click();
  await page.waitForTimeout(2200);
  await page.screenshot({ path: "e2e/screens/02-axial.png" });
  await page.getByRole("button", { name: /^Axial Base · LJ03A, \d+ sensors$/ }).click();
  await expect(page.getByRole("heading", { name: "Axial Seamount Base" })).toBeVisible();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "e2e/screens/03-site-panel.png" });
  await openSensorBySearch(page, "CTDPFA303");   // 200 m platform CTD; confirmed to have a public ERDDAP feed
  await expect(page.getByText(/checked live/)).toBeVisible();
  await expect(page.locator(".chart canvas")).toBeVisible();
  await expect(page.getByRole("link", { name: /Download this range/ })).toBeVisible();
  await page.screenshot({ path: "e2e/screens/04-sensor-chart.png" });
});

test("family focus mutes other families", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.getByRole("button", { name: /^Seismic/ }).click();
  await expect(page.getByRole("button", { name: /^Water properties/ })).toHaveClass(/muted/);
});

test("3D contours and 2D top-down", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await regionButton(page, "Axial Seamount").click();
  await page.waitForTimeout(2200);
  await page.getByRole("button", { name: "Contours" }).click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "e2e/screens/05-contours-3d.png" });
  await page.getByRole("button", { name: "2D" }).click();
  await page.waitForTimeout(1500);
  const tilt = await page.evaluate(() => { const s = window.__atlas.scene; const d = s.camera.position.clone().sub(s.controls.target); return Math.acos(d.y / d.length()) * 180 / Math.PI; });
  expect(tilt).toBeLessThan(1);
  await expect(page.getByRole("slider", { name: /Vertical/ })).toBeDisabled();
  await page.screenshot({ path: "e2e/screens/06-2d.png" });
});

test("arrow keys move the camera but not while typing", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  const target = () => page.evaluate(() => window.__atlas.scene.controls.target.toArray());
  const a = await target();
  await page.keyboard.down("ArrowRight"); await page.waitForTimeout(500); await page.keyboard.up("ArrowRight");
  const b = await target();
  expect(Math.hypot(b[0] - a[0], b[2] - a[2])).toBeGreaterThan(1);
  await page.getByRole("textbox", { name: /Ask/ }).focus();
  await page.keyboard.down("ArrowLeft"); await page.waitForTimeout(500); await page.keyboard.up("ArrowLeft");
  const c = await target();
  expect(Math.hypot(c[0] - b[0], c[2] - b[2])).toBeLessThan(0.01);
});

test("mouse movement alone never moves the camera", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  const pos = () => page.evaluate(() => window.__atlas.scene.camera.position.toArray().map(v => v.toFixed(3)).join());
  const before = await pos();
  for (const [x, y] of [[40, 40], [1560, 960], [1500, 60]]) await page.mouse.move(x, y, { steps: 6 });
  await page.waitForTimeout(800);
  expect(await pos()).toBe(before);
});

test("gateway down shows the snapshot wording", async ({ page }) => {
  await mockGateway(page, { down: true });
  await page.goto("/");
  await ready(page);
  await openSensorBySearch(page, "CTDPFA303");
  await expect(page.getByText(/Live data unavailable\. Showing snapshot from/)).toBeVisible();
});

test("chat answers and minimizes", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.getByRole("textbox", { name: /Ask/ }).fill("What is at Axial Base?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Axial Base has a seafloor package and two profilers.")).toBeVisible();
  await page.getByRole("button", { name: "Minimize chat" }).click();
  await expect(page.getByRole("button", { name: "Open chat" })).toBeVisible();
});

test("missing bundle shows the build command", async ({ page }) => {
  await page.route("**/atlas/manifest.json", r => r.fulfill({ status: 404, body: "" }));
  await page.goto("/");
  await expect(page.getByText(/build_atlas_bundle/)).toBeVisible();
});

test("Axial detail sharpens as you zoom", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  // Vite answers a missing file with index.html and 200, so check the type too.
  const hasTiles = await page.evaluate(async () => { const r = await fetch("/atlas/auv/index.json"); return r.ok && (r.headers.get("content-type") ?? "").includes("json"); });
  test.skip(!hasTiles, "AUV tiles not built (plan 1, Task 9)");
  await page.evaluate(() => window.__atlas.scene.flyTo({ ll: [-130.009, 45.953], dist: 3.2, polar: 0.95, az: -0.5, exag: 2 }));
  await page.waitForTimeout(6000);
  const s = await page.evaluate(() => window.__atlas.lod());
  expect(s.L2).toBeGreaterThan(0);
  await expect(page.getByText("1 m", { exact: true })).toBeVisible();
  await page.screenshot({ path: "e2e/screens/07-axial-1m.png" });
});

test("the GMRT and MBARI credits are on screen by default; the chat alone does not collapse the legend", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await expect(page.getByRole("complementary", { name: "Atlas chat" })).toBeVisible();
  const credit = page.getByLabel("Map credits");
  await expect(credit).toBeVisible();
  await expect(credit).toContainText("GMRT, Ryan et al. (2009), CC BY 4.0");
  const hasTiles = await page.evaluate(() => !!window.__atlas.scene.auv);
  if (hasTiles) await expect(credit).toContainText("MBARI");
  await expect(page.getByText("Seafloor depth")).toBeVisible();   // legend expanded
  // The credit line stays clear of every panel and inside the window.
  const clear = await page.evaluate(() => {
    const c = document.querySelector(".credit").getBoundingClientRect();
    const overlaps = [...document.querySelectorAll(".panel")].some(p => { const r = p.getBoundingClientRect();
      return !(c.right <= r.left || c.left >= r.right || c.bottom <= r.top || c.top >= r.bottom); });
    return !overlaps && c.left >= 0 && c.bottom <= innerHeight;
  });
  expect(clear).toBe(true);
});

for (const [width, height] of [[1600, 1000], [1366, 768], [1280, 800]]) {
  test(`an opened site is framed in free space at ${width}x${height} with the chat open`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await mockGateway(page);
    await page.goto("/");
    await ready(page);
    await expect(page.getByRole("complementary", { name: "Atlas chat" })).toBeVisible();
    await page.evaluate(() => window.__atlas.open("axial-seamount-base"));
    await expect(page.getByRole("heading", { name: "Axial Seamount Base" })).toBeVisible();
    await page.waitForTimeout(2500);   // the flight (1.3 s) and the glide to the new center
    const wraps = width - 412 - 472 < 580;
    // Wrapped, the terrain controls and the legend collapse to toggles.
    await expect(page.getByRole("button", { name: "Terrain controls" })).toHaveCount(wraps ? 1 : 0);
    await expect(page.getByRole("button", { name: "Legend", exact: true })).toBeVisible();
    const hit = await page.evaluate(() => {
      const m = document.querySelector(".site.selected"), b = m.getBoundingClientRect();
      const el = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return { onMarker: el?.closest(".site") === m, inPanel: !!el?.closest(".panel") };
    });
    expect(hit).toEqual({ onMarker: true, inPanel: false });
    await page.screenshot({ path: `e2e/screens/08-site-${width}x${height}.png` });
  });
}

test("reduced motion: the operating halo rests faint instead of solid", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  const halo = await page.evaluate(() => { const h = document.querySelector(".site .halo"); const cs = getComputedStyle(h);
    return { opacity: cs.opacity, animation: cs.animationName }; });
  expect(halo).toEqual({ opacity: "0.25", animation: "none" });
  await context.close();
});

test("unplaced sensors: listed from the regions panel, open their detail without a site, back returns to the list", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  const target = () => page.evaluate(() => window.__atlas.scene.controls.target.toArray().map(v => v.toFixed(3)).join());
  const before = await target();
  await page.getByRole("button", { name: /^Unplaced sensors/ }).click();
  const panel = page.getByRole("complementary", { name: "Unplaced sensors" });
  await expect(panel).toBeVisible();
  const expected = await page.evaluate(async () => (await (await fetch("/atlas/sensors.json")).json()).unplaced.length);
  await expect(panel.locator(".sp-row")).toHaveCount(expected);
  await panel.getByRole("button", { name: /^ASHES PI mass spectrometer/ }).click();
  await expect(panel.getByRole("heading", { name: "ASHES PI mass spectrometer" })).toBeVisible();
  await expect(panel.getByText(/No recorded position/)).toBeVisible();
  await panel.getByRole("button", { name: "← Unplaced sensors" }).click();
  await expect(panel.getByRole("button", { name: /^ASHES PI mass spectrometer/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  expect(await target()).toBe(before);   // nothing flew
});

test("search finds a sensor with no recorded position and opens it without a flight; Escape then steps back", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  const target = () => page.evaluate(() => window.__atlas.scene.controls.target.toArray().map(v => v.toFixed(3)).join());
  const before = await target();
  const box = page.getByRole("searchbox", { name: /Search sensors and sites/ });
  await box.fill("Distributed Acoustic Sensing 2024");
  await expect(page.getByRole("option").first()).toContainText("no recorded position");
  await page.keyboard.press("Enter");
  const panel = page.getByRole("complementary", { name: "Unplaced sensors" });
  await expect(panel.getByRole("heading", { name: /Distributed Acoustic Sensing 2024/ })).toBeVisible();
  await expect(box).not.toBeFocused();
  await page.waitForTimeout(600);
  expect(await target()).toBe(before);
  await page.keyboard.press("Escape");   // detail -> list
  await expect(panel.getByRole("heading", { name: "Unplaced sensors" })).toBeVisible();
  await page.keyboard.press("Escape");   // list -> closed
  await expect(panel).toHaveCount(0);
});

test("a site's unlocated sensors open their detail; arrows scroll the panel, not the map", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.evaluate(() => window.__atlas.open("axial-seamount-base"));
  const panel = page.getByRole("complementary", { name: /Axial Base · LJ03A site/ });
  await expect(panel).toBeVisible();
  await page.waitForTimeout(1800);
  const row = panel.getByRole("button", { name: "Axial Base bottom pressure and tilt instrument, location not recorded" });
  await row.focus();
  const target = () => page.evaluate(() => window.__atlas.scene.controls.target.toArray());
  const a = await target();
  await page.keyboard.down("ArrowDown"); await page.waitForTimeout(400); await page.keyboard.up("ArrowDown");
  const b = await target();
  expect(Math.hypot(b[0] - a[0], b[2] - a[2])).toBeLessThan(0.001);
  await row.click();
  await expect(panel.getByRole("heading", { name: "Axial Base bottom pressure and tilt instrument" })).toBeVisible();
  await panel.getByRole("button", { name: "← Axial Base · LJ03A" }).click();
  await expect(panel.getByRole("heading", { name: "Axial Seamount Base" })).toBeVisible();
});

test("primary node hover lists nearby sites with counts, and its position accuracy and source", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.locator(".pnode", { hasText: "PN3B" }).dispatchEvent("mouseenter", { clientX: 600, clientY: 400 });
  const tip = page.getByRole("tooltip");
  await expect(tip).toContainText("Catalogued sites within 30 km");
  await expect(tip).toContainText(/Axial Central Caldera\s*\d+ sensors · \d/);
  await expect(tip).toContainText(/Position approximate\. Source: /);
});

test("markers are tab stops only once they are shown", async ({ page }) => {
  await mockGateway(page);
  await page.goto("/");
  await ready(page);
  await page.waitForTimeout(300);
  expect(await page.locator('.site[tabindex="0"]').count()).toBe(0);   // region mode: labels, no markers
  await regionButton(page, "Axial Seamount").click();
  await page.waitForTimeout(2400);
  expect(await page.locator('.site[tabindex="0"]').count()).toBeGreaterThan(0);
});
