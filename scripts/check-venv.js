#!/usr/bin/env node
/**
 * check-venv.js
 * Verifies the project venv exists and Python is runnable.
 * Exits 0 on success, non-zero with a clear message otherwise.
 */
const path = require("node:path");
const fs = require("node:fs");

const repoRoot = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";
const venvPy = isWin
  ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
  : path.join(repoRoot, ".venv", "bin", "python");

if (!fs.existsSync(venvPy)) {
  console.error("");
  console.error("  X Virtualenv non trovato: " + venvPy);
  console.error("");
  console.error("    Crealo con:");
  if (isWin) {
    console.error("      py -m venv .venv");
    console.error("      .venv\\Scripts\\python.exe -m pip install -r requirements.txt");
  } else {
    console.error("      python3 -m venv .venv");
    console.error("      .venv/bin/python -m pip install -r requirements.txt");
  }
  console.error("");
  process.exit(1);
}

console.log("  OK .venv trovato: " + venvPy);
process.exit(0);
