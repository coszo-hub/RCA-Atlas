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
