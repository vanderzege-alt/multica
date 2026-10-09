import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

const route = "/login";
const state = "anonymous-login";

test("public login state emits screenshot, axe, and visual evidence", async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
      return route.fulfill({ status: 200, contentType: "font/woff2", body: "" });
    }
    return route.continue();
  });
  await page.route(/\/(api|auth)\//, (request) =>
    request.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.goto(route);
  await expect(page.locator("body")).toBeVisible();
  await page.mouse.move(-1, -1);

  const viewport = page.viewportSize();
  const browserVersion = page.context().browser()?.version() ?? "unknown";
  testInfo.annotations.push({ type: "ui-route", description: route });
  testInfo.annotations.push({ type: "ui-state", description: state });
  testInfo.annotations.push({ type: "ui-viewport", description: JSON.stringify(viewport) });
  testInfo.annotations.push({ type: "ui-browser-version", description: browserVersion });
  testInfo.annotations.push({
    type: "ui-device-profile",
    description: testInfo.project.name,
  });

  const screenshotPath = testInfo.outputPath("anonymous-login.png");
  await mkdir(dirname(screenshotPath), { recursive: true });
  const screenshot = await page.screenshot({ path: screenshotPath, animations: "disabled" });
  await testInfo.attach("screenshot", { path: screenshotPath, contentType: "image/png" });
  testInfo.annotations.push({ type: "ui-check-screenshots", description: "PASS" });

  let visualError: unknown;
  try {
    await expect(page).toHaveScreenshot("anonymous-login.png", { animations: "disabled" });
    testInfo.annotations.push({ type: "ui-check-visual", description: "PASS" });
  } catch (error) {
    visualError = error;
    testInfo.annotations.push({ type: "ui-check-visual", description: "FAIL" });
  }
  testInfo.annotations.push({
    type: "ui-baseline-reference",
    description: testInfo.snapshotPath("anonymous-login.png"),
  });

  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const axePath = testInfo.outputPath("axe-report.json");
  await writeFile(axePath, `${JSON.stringify(axe, null, 2)}\n`, "utf8");
  await testInfo.attach("axe-report", { path: axePath, contentType: "application/json" });
  testInfo.annotations.push({
    type: "ui-check-a11y",
    description: axe.violations.length === 0 ? "PASS" : "FAIL",
  });

  expect(axe.violations, `axe found ${axe.violations.length} violation(s); see attached axe-report`).toEqual([]);
  if (visualError) throw visualError;
  expect(screenshot.byteLength).toBeGreaterThan(0);
});
