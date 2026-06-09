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
 * Runs a preflight: if API_SERVER_PORT (default 9001) is already bound,
 * print the holding PID and a `taskkill`/`kill` hint, then exit non-zero
 * so `concurrently` doesn't keep respawning into a port collision.
 *
 * Forwards signals so Ctrl+C kills the child too, and streams stdout/stderr
 * with an [api] prefix so concurrently can color-code the streams.
 */

const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const net = require("node:net");

const repoRoot = path.resolve(__dirname, "..");

const DEFAULT_API_PORT = 9001;
function resolveApiPort() {
  const raw = (process.env.API_SERVER_PORT ?? String(DEFAULT_API_PORT)).trim();
  return /^\d+$/.test(raw) ? Number(raw) : DEFAULT_API_PORT;
}

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
const apiPort = resolveApiPort();
const apiHost = (process.env.API_SERVER_ADDRESS ?? "127.0.0.1").trim() || "127.0.0.1";

/**
 * Probe whether `host:port` is already in LISTEN state.
 * On Windows we use `netstat -ano` because `net.connect` against a port
 * another process is listening on succeeds and tells us nothing useful.
 * On POSIX a same-host connect attempt that succeeds means "something is
 * listening", which is what we want to detect.
 */
function probePort(host, port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const finish = (status, info) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve({ status, info });
    };
    socket.setTimeout(800);
    socket.once("connect", () => finish("listening", { kind: "connect" }));
    socket.once("timeout", () => finish("free", { kind: "timeout" }));
    socket.once("error", (err) => {
      // ECONNREFUSED on localhost => nothing is listening.
      if (err && err.code === "ECONNREFUSED") {
        finish("free", { kind: "refused" });
      } else {
        finish("unknown", { kind: "error", code: err && err.code });
      }
    });
    socket.connect(port, host);
  });
}

function windowsListeningPids(port) {
  const out = spawnSync("netstat", ["-ano", "-p", "TCP"], { encoding: "utf8" });
  if (out.status !== 0) return [];
  const pids = new Set();
  const re = new RegExp(`\\s127\\.0\\.0\\.1:${port}\\s.*LISTENING\\s+(\\d+)`, "i");
  for (const line of out.stdout.split(/\r?\n/)) {
    const m = line.match(re);
    if (m) pids.add(m[1]);
  }
  return [...pids];
}

function posixListeningPids(port) {
  const out = spawnSync("lsof", [`-tiTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
  if (out.status !== 0) return [];
  return out.stdout.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

async function preflight() {
  const result = await probePort(apiHost, apiPort);
  if (result.status === "free") return;
  const pids = process.platform === "win32"
    ? windowsListeningPids(apiPort)
    : posixListeningPids(apiPort);
  console.error("");
  console.error(`  X  Port ${apiPort} is already in use on ${apiHost}.`);
  if (pids.length) {
    console.error(`     Held by PID: ${pids.join(", ")}`);
    if (process.platform === "win32") {
      console.error(`     Kill with:   taskkill /F /PID ${pids[0]}`);
      console.error(`     Or:          npm run clean`);
    } else {
      console.error(`     Kill with:   kill -9 ${pids[0]}`);
    }
  } else {
    console.error("     (Could not identify the holder — try `npm run clean`.)");
  }
  console.error(`     Override port: set API_SERVER_PORT=<other> in the environment.`);
  console.error("");
  process.exit(1);
}

(async () => {
  await preflight();
  launch();
})();

function launch() {
  console.log(`[api] launching: ${exe} -m src.api   (interpreter: ${label}, target ${apiHost}:${apiPort})`);

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
}
