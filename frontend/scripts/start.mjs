import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import path from "node:path";

const HOST = "127.0.0.1";
const PORT = 5173;
const URL = `http://${HOST}:${PORT}/`;

function isPortFree(port, host) {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => server.close(() => resolve(true)));
    server.listen(port, host);
  });
}

function listeningPidsWindows(port) {
  const { stdout = "" } = spawnSync("netstat", ["-ano"], {
    encoding: "utf8",
  });
  const pids = new Set();
  for (const line of stdout.split(/\r?\n/)) {
    if (!line.includes(`:${port}`) || !line.includes("LISTENING")) continue;
    const parts = line.trim().split(/\s+/);
    const pid = parts[parts.length - 1];
    if (pid && pid !== "0") pids.add(pid);
  }
  return [...pids];
}

function killPort(port) {
  if (process.platform === "win32") {
    const pids = listeningPidsWindows(port);
    for (const pid of pids) {
      spawnSync("taskkill", ["/PID", pid, "/F"], { stdio: "ignore" });
    }
    return pids.length > 0;
  }
  spawnSync("sh", ["-c", `lsof -ti tcp:${port} | xargs -r kill -9`], {
    stdio: "ignore",
  });
  return true;
}

async function waitUntil(predicate, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await predicate()) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

function openBrowser(url) {
  const [cmd, args] =
    process.platform === "win32"
      ? ["cmd", ["/c", "start", "", url]]
      : process.platform === "darwin"
        ? ["open", [url]]
        : ["xdg-open", [url]];
  const child = spawn(cmd, args, { stdio: "ignore", detached: true });
  child.unref();
}

const hadProcess = killPort(PORT);
if (hadProcess) {
  await waitUntil(() => isPortFree(PORT, HOST), 5000);
}

const viteEntry = path.resolve("node_modules", "vite", "bin", "vite.js");
const child = spawn(process.execPath, [viteEntry, "--strictPort"], {
  stdio: "inherit",
  env: process.env,
});

if (await waitUntil(() => isPortFree(PORT, HOST).then((free) => !free), 15000)) {
  openBrowser(URL);
}

child.on("exit", (code) => process.exit(code ?? 0));
