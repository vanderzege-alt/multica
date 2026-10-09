import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { relative, resolve, sep } from "node:path";
import os from "node:os";

const statuses = new Set(["PASS", "FAIL", "NOT RUN", "SKIPPED", "NOT AVAILABLE"]);

function annotation(test, type) {
  return test.annotations?.find((item) => item.type === type)?.description;
}

function repoPath(path) {
  if (!path) return undefined;
  const result = relative(process.cwd(), resolve(path));
  return result.split(sep).join("/");
}

function resultStatus(status) {
  if (status === "passed") return "PASS";
  if (status === "skipped") return "SKIPPED";
  return "FAIL";
}

export default class UiQaManifestReporter {
  constructor(options = {}) {
    this.outputFile = options.outputFile ?? "ui-qa-artifacts/manifest.json";
    this.targets = [];
  }

  onTestEnd(test, result) {
    const project = test.parent.project();
    const viewport = JSON.parse(annotation(test, "ui-viewport") ?? "null");
    const browserName = project.use.browserName ?? project.name;
    const browserVersion = annotation(test, "ui-browser-version") ?? "unknown";
    const attachmentPaths = result.attachments.map((item) => repoPath(item.path)).filter(Boolean);
    const statusFor = (capability) => {
      const value = annotation(test, `ui-check-${capability}`);
      return statuses.has(value) ? value : "NOT RUN";
    };
    const checks = ["screenshots", "a11y", "visual"].map((name) => {
      const status = statusFor(name);
      return {
        capability: `ui:${name}`,
        status,
        ...(status === "PASS" ? {} : { reason: "See the attached Playwright and axe artifacts for this target." }),
      };
    });
    this.targets.push({
      route: annotation(test, "ui-route") ?? "unknown",
      state: annotation(test, "ui-state") ?? "unknown",
      browser: { name: browserName, version: browserVersion },
      viewport: {
        width: viewport?.width ?? 0,
        height: viewport?.height ?? 0,
        device_scale_factor: project.use.deviceScaleFactor ?? 1,
      },
      device_profile: annotation(test, "ui-device-profile") ?? project.name,
      baseline_reference: repoPath(annotation(test, "ui-baseline-reference")) ?? null,
      result: resultStatus(result.status),
      checks,
      artifacts: {
        screenshots: attachmentPaths.filter((path) => path.endsWith(".png")),
        diffs: attachmentPaths.filter((path) => /diff/i.test(path) && path.endsWith(".png")),
        reports: attachmentPaths.filter((path) => path.endsWith(".json")),
        logs: [],
      },
    });
  }

  async onEnd(result) {
    const commit = process.env.UI_BUILD_ID ?? execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    const statusesByCapability = (capability) => {
      const statuses = this.targets.flatMap((target) =>
        target.checks.filter((check) => check.capability === capability || check.capability === `ui:${capability}`).map((check) => check.status),
      );
      if (statuses.includes("FAIL")) return "FAIL";
      if (statuses.length && statuses.every((status) => status === "PASS")) return "PASS";
      if (!this.targets.length) return "NOT AVAILABLE";
      return "NOT RUN";
    };
    const overall = result.status === "passed" ? "PASS" : "FAIL";
    const artifactPaths = this.targets.flatMap((target) => Object.values(target.artifacts).flat());
    const baseURL = process.env.UI_BASE_URL ?? "http://127.0.0.1:3100";
    const manifest = {
      schema_version: "1.0.0",
      project: "AI Agents as Employees",
      repository: "https://github.com/vanderzege-alt/multica",
      commit,
      build: {
        id: process.env.UI_BUILD_ID ?? `local-${Date.now()}`,
        url: baseURL,
        readiness: this.targets.length ? "PASS" : "NOT RUN",
      },
      adapter: { name: "playwright-web", version: "1.0.0" },
      command: process.env.UI_COMMAND ?? "ui:visual",
      runtime: { name: "node", version: process.version },
      os: { name: process.platform, version: os.release(), architecture: os.arch() },
      browser: null,
      result: overall,
      checks: ["ui:preview", "ui:screenshots", "ui:a11y", "ui:visual"].map((capability) => {
        const status = capability === "ui:preview"
          ? (result.status === "passed" ? "PASS" : "FAIL")
          : statusesByCapability(capability.slice(3));
        return {
          capability,
          status,
          ...(status === "PASS" ? {} : { reason: "No successful target covered this capability; inspect per-target results." }),
        };
      }),
      targets: this.targets,
      artifacts: {
        screenshots: this.targets.flatMap((target) => target.artifacts.screenshots),
        diffs: this.targets.flatMap((target) => target.artifacts.diffs),
        reports: ["ui-qa-artifacts/manifest.json", ...artifactPaths.filter((path) => path.endsWith(".json"))],
        logs: [],
      },
    };
    if (manifest.checks.some((check) => check.status !== "PASS")) {
      manifest.result = "FAIL";
    }
    const path = resolve(process.cwd(), this.outputFile);
    await mkdir(resolve(path, ".."), { recursive: true });
    await writeFile(path, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  }
}
