// One command, one address: starts the FastAPI backend (port 8842, internal)
// and the Next.js app (http://localhost:3000), which forwards /api to it.
// Ctrl+C stops both.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const win = process.platform === "win32";
const py = [join(root, "venv", win ? "Scripts/python.exe" : "bin/python")].find(existsSync) ?? "python";

const procs = [
  spawn(py, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8842"], { cwd: join(root, "backend"), stdio: "inherit" }),
  spawn(win ? "npx.cmd" : "npx", ["next", "dev", "-p", "3000"], { cwd: join(root, "frontend"), stdio: "inherit", shell: win }),
];
console.log("\n  Gnani Shop → http://localhost:3000\n");
// On Windows, kill() stops only the shell, leaving `next dev` running and
// holding the port — take down each whole process tree instead.
const killTree = (p) => {
  if (p.exitCode !== null) return;
  if (win) spawnSync("taskkill", ["/pid", String(p.pid), "/T", "/F"], { stdio: "ignore" });
  else p.kill();
};
let stopping = false;
const stop = () => {
  if (stopping) return;
  stopping = true;
  procs.forEach(killTree);
  process.exit();
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const p of procs) p.on("exit", (code) => { if (code) { console.error(`a server exited (${code}); stopping`); stop(); } });
