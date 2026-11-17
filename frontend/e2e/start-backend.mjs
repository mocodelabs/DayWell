// Start a Django server for end-to-end tests on a dedicated, freshly flushed database.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "../../backend");
const venvPython = process.platform === "win32" ? resolve(backend, ".venv/Scripts/python.exe") : resolve(backend, ".venv/bin/python");
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");
const env = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: "config.settings.dev",
  DATABASE_URL: process.env.E2E_DATABASE_URL ?? "postgres://daywell:daywell@127.0.0.1:5440/daywell_e2e",
  REDIS_URL: process.env.E2E_REDIS_URL ?? "redis://127.0.0.1:6390/5",
  CELERY_TASK_ALWAYS_EAGER: "true",
  THROTTLE_AUTH: "1000/minute",
  THROTTLE_USER: "1000000/hour",
  THROTTLE_SENSITIVE: "1000/hour",
  THROTTLE_TEST_NOTIFY: "1000/hour",
  FRONTEND_URL: "http://127.0.0.1:5194",
  CSRF_TRUSTED_ORIGINS: "http://127.0.0.1:5194,http://localhost:5194",
};

// The database is flushed (user ids restart), so rate-limit counters and lockouts in the e2e Redis DB must be cleared too.
const flushRedis = spawnSync(python, ["-c", "import os, redis; redis.from_url(os.environ['REDIS_URL']).flushdb()"], { cwd: backend, env, stdio: "inherit" });
if (flushRedis.status !== 0) process.exit(flushRedis.status ?? 1);

for (const args of [["migrate", "--noinput"], ["flush", "--noinput"], ["seed_affirmations"], ["billing_seed_plans"]]) {
  const r = spawnSync(python, ["manage.py", ...args], { cwd: backend, env, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}
const server = spawn(python, ["manage.py", "runserver", "127.0.0.1:8021", "--noreload"], { cwd: backend, env, stdio: "inherit" });
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
