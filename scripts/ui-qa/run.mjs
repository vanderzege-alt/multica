import { spawn } from "node:child_process";

const command = process.argv[2];
const supported = ["ui:screenshots", "ui:a11y", "ui:visual", "ui:baseline:update"];

if (!supported.includes(command)) {
  process.stderr.write(`Usage: node scripts/ui-qa/run.mjs ${supported.join("|")}\n`);
  process.exit(2);
}

const args = ["exec", "playwright", "test", "--config=ui-qa/playwright.config.ts"];
if (command === "ui:screenshots" || command === "ui:a11y" || command === "ui:visual" || command === "ui:baseline:update") {
  args.push("--grep=public marketing homepage", "--workers=1");
  if (process.platform !== "linux" && !process.env.UI_ALL_BROWSERS) args.push("--project=chromium-desktop");
}
if (command === "ui:baseline:update") args.push("--update-snapshots");
const child = spawn("pnpm", args, {
  env: {
    ...process.env,
    UI_COMMAND: command === "ui:baseline:update" ? "ui:visual" : command,
  },
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.on("SIGINT", () => child.kill("SIGINT"));
process.on("SIGTERM", () => child.kill("SIGTERM"));
child.once("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
