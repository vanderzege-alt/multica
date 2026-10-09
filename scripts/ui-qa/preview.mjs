import { spawn } from "node:child_process";
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const repoRoot = process.cwd();
const baseURL = process.env.UI_BASE_URL ?? "http://localhost:3100";
const port = process.env.FRONTEND_PORT ?? (new URL(baseURL).port || "3100");
const readyURL = new URL("/", baseURL);
const child = spawn("pnpm", ["--filter", "@multica/web", "dev"], {
  cwd: repoRoot,
  detached: process.platform !== "win32",
  env: { ...process.env, FRONTEND_PORT: port },
  stdio: "inherit",
  shell: process.platform === "win32",
});
let stopping = false;
let stopTimer;

function signalChild(signal) {
  stopping = true;
  if (!child.pid) return;
  try {
    if (process.platform === "win32") child.kill(signal);
    else process.kill(-child.pid, signal);
  } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
}

async function stopAndWait(signal = "SIGTERM") {
  if (stopping) return;
  signalChild(signal);
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  stopTimer = setTimeout(() => {
    signalChild("SIGKILL");
    process.exit(1);
  }, 5_000);
}

async function waitUntilReady(timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`Preview exited before readiness (code=${child.exitCode}, signal=${child.signalCode})`);
    }
    try {
      const response = await fetch(readyURL, { signal: AbortSignal.timeout(2_000) });
      if (response.ok) return;
    } catch {
      // Readiness is retried only while the child remains alive and within the fixed deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Preview did not return a successful response from ${readyURL} within ${timeoutMs}ms`);
}

async function writeReadiness() {
  const commit = process.env.UI_BUILD_ID ?? execFileSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).trim();
  const payload = {
    project: "AI Agents as Employees",
    repository: "https://github.com/vanderzege-alt/multica",
    commit,
    build_id: process.env.UI_BUILD_ID ?? `local-${Date.now()}`,
    url: baseURL,
    readiness: "PASS",
    checked_url: readyURL.href,
  };
  const output = resolve(repoRoot, "ui-qa-artifacts/preview.json");
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

process.on("SIGINT", () => void stopAndWait("SIGINT"));
process.on("SIGTERM", () => void stopAndWait("SIGTERM"));
child.once("exit", (code) => {
  if (stopTimer) clearTimeout(stopTimer);
  if (!stopping) process.exitCode = code ?? 1;
});

try {
  await waitUntilReady();
  await writeReadiness();
  await new Promise((resolve) => child.once("exit", resolve));
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  await stopAndWait();
  process.exitCode = 1;
}
