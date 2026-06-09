#!/usr/bin/env node
/**
 * dev-api.js
 * Cross-platform launcher for the FastAPI backend.
 *
 * Picks the right Python interpreter:
 *   1. .venv\Scripts\python.exe   (Windows)
 *      .venv/bin/python           (POSIX)
 *   2. python3 / py
 *
 * Forwards signals so Ctrl+C kills the child too, and streams stdout/stderr
 * with an [api] prefix so concurrently can color-code the streams.
 */

const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const repoRoot = path.resolve(__dirname, "..");

function pickPython() {
  const isWin = process.platform === "win32";
  const venvPy = isWin
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python");

  if (fs.existsSync(venvPy)) {
    return { exe: venvPy, label: ".venv" };
  }

  const fallbacks = isWin ? ["py", "python", "python3"] : ["python3", "python"];
  for (const cand of fallbacks) {
    const probe = spawn(cand, ["--version"], { stdio: "ignore" });
    probe.on("error", () => {});
    probe.on("exit", (code) => {
      // synchronous probing is fine here; the child exits quickly
    });
    // We just trust PATH order: try the first one that exists on PATH
    // by attempting to spawn and checking 'error' synchronously is racy,
    // so instead we let Node pick via shell. Simpler: use the first fallback
    // and let spawn fail loudly if missing.
    return { exe: fallbacks[0], label: fallbacks[0] };
  }
  return { exe: "python", label: "python" };
}

const { exe, label } = pickPython();

console.log(`[api] launching: ${exe} -m src.api   (interpreter: ${label})`);

const child = spawn(exe, ["-m", "src.api"], {
  cwd: repoRoot,
  stdio: ["ignore", "pipe", "pipe"],
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
});

function pipe(stream, prefix) {
  let buf = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buf += chunk;
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() ?? "";
    for (const line of lines) {
      process.stdout.write(`${prefix} ${line}\n`);
    }
  });
  stream.on("end", () => {
    if (buf.length) process.stdout.write(`${prefix} ${buf}\n`);
  });
}

pipe(child.stdout, "[api]");
pipe(child.stderr, "[api]");

child.on("exit", (code, signal) => {
  console.log(`[api] exited (code=${code}, signal=${signal})`);
  // Exit the wrapper so concurrently can restart or shut down siblings.
  process.exit(code ?? 0);
});

// Forward Ctrl+C / SIGTERM to child.
function shutdown(sig) {
  if (process.platform === "win32") {
    // On Windows, child Python receives CTRL_BREAK_EVENT via tree-kill;
    // simplest: kill the process tree.
    try {
      spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
    } catch {
      child.kill();
    }
  } else {
    child.kill(sig);
  }
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
