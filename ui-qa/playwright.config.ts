import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const baseURL = process.env.UI_BASE_URL ?? "http://localhost:3100";

export default defineConfig({
  testDir: ".",
  testMatch: "web.spec.ts",
  outputDir: resolve(process.cwd(), "ui-qa-artifacts/test-results"),
  reporter: [
    ["list"],
    [resolve(process.cwd(), "scripts/ui-qa/manifest-reporter.mjs"), { outputFile: "ui-qa-artifacts/manifest.json" }],
    ["html", { outputFolder: resolve(process.cwd(), "ui-qa-artifacts/html-report"), open: "never" }],
  ],
  use: {
    baseURL,
    headless: true,
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "light",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  timeout: 120_000,
  projects: [
    { name: "chromium-desktop", use: { ...devices["Desktop Chrome"], browserName: "chromium" } },
    { name: "firefox-desktop", use: { ...devices["Desktop Firefox"], browserName: "firefox" } },
    { name: "webkit-desktop", use: { ...devices["Desktop Safari"], browserName: "webkit" } },
    { name: "webkit-iphone", use: { ...devices["iPhone 13"], browserName: "webkit" } },
  ],
  webServer: {
    command: `node ${resolve(process.cwd(), "scripts/ui-qa/preview.mjs")}`,
    url: `${baseURL}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
