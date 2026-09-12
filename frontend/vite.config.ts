import { readFileSync } from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/** Version reported by the feedback button's context panel. Read from
    package.json so the two can't drift apart. */
const pkgVersion = (() => {
  try {
    const pkg = readFileSync(path.resolve(__dirname, "package.json"), "utf8");
    return String(JSON.parse(pkg).version ?? "unknown");
  } catch {
    return "unknown";
  }
})();

const DEFAULT_API_PORT = 9001;
const apiPortRaw = (process.env.API_SERVER_PORT ?? String(DEFAULT_API_PORT)).trim();
const apiPort = /^\d+$/.test(apiPortRaw) ? apiPortRaw : String(DEFAULT_API_PORT);
const apiTarget = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkgVersion),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./__tests__/setup.ts"],
    globals: true,
  },
});
