"""Dashboard load test for DayWell (PRD §18.1: dashboard API p95 < 500 ms under normal load).

Each virtual user signs in as a distinct seeded load-test user (`manage.py seed_load`) and repeats the requests the
Today screen makes: /dashboard/today/ plus the app-shell calls (active/missed/upcoming alarms, unread count), with think
time between page views. Latency is measured client-side through the full stack (TLS proxy → nginx → gunicorn → Django).

    python deploy/loadtest/loadtest.py --base https://localhost:8443 --users 100 --concurrency 20 --duration 120 --insecure

Only run against an environment seeded for load testing — never production with real users.
"""

from __future__ import annotations

import argparse
import random
import statistics
import threading
import time
from collections import defaultdict

import requests
import urllib3

# What the app shell requests alongside the dashboard on a Today page view (keep in sync with AppShell/AlarmProvider).
SHELL_CALLS = ["/api/v1/alarms/active/", "/api/v1/alarms/upcoming/?hours=2", "/api/v1/notifications/unread-count/"]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def login(base: str, email: str, password: str, verify: bool) -> requests.Session:
    s = requests.Session()
    s.verify = verify
    s.get(f"{base}/api/v1/auth/csrf/", timeout=30)
    token = s.cookies.get("daywell_csrftoken")
    r = s.post(f"{base}/api/v1/auth/login/", json={"email": email, "password": password}, timeout=30,
               headers={"X-CSRFToken": token, "Origin": base, "Referer": f"{base}/login"})
    r.raise_for_status()
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://localhost:8443")
    ap.add_argument("--users", type=int, default=100, help="number of seeded load-test users to sign in as")
    ap.add_argument("--concurrency", type=int, default=20, help="simultaneous virtual users")
    ap.add_argument("--duration", type=int, default=120, help="measured seconds (after warm-up)")
    ap.add_argument("--warmup", type=int, default=15)
    ap.add_argument("--think", type=float, default=1.0, help="mean think time between page views (s); 0 = stress")
    ap.add_argument("--password", default="Loadtest-password-2026")
    ap.add_argument("--insecure", action="store_true", help="skip TLS verification (local self-signed proxy)")
    ap.add_argument("--docker-stats", default="", help="container name filter: print `docker stats` sampled mid-run (e.g. daywell-prod)")
    args = ap.parse_args()
    if args.insecure:
        urllib3.disable_warnings()

    sessions: list[requests.Session] = []
    for i in range(args.users):
        sessions.append(login(args.base, f"loadtest-{i}@daywell.loadtest", args.password, not args.insecure))
    print(f"signed in {len(sessions)} users")

    lat: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    lock = threading.Lock()
    start = time.monotonic()
    measure_from = start + args.warmup
    stop_at = measure_from + args.duration

    def worker(idx: int) -> None:
        rnd = random.Random(idx)
        while time.monotonic() < stop_at:
            s = sessions[rnd.randrange(len(sessions))]
            for path in ["/api/v1/dashboard/today/", *SHELL_CALLS]:
                t0 = time.perf_counter()
                try:
                    r = s.get(f"{args.base}{path}", timeout=30)
                    ok = r.status_code == 200
                except requests.RequestException:
                    ok = False
                ms = (time.perf_counter() - t0) * 1000
                key = "dashboard" if "dashboard" in path else "shell"
                if time.monotonic() >= measure_from:
                    with lock:
                        lat[key].append(ms)
                        if not ok:
                            errors[key] += 1
            if args.think:
                time.sleep(rnd.uniform(0.5 * args.think, 1.5 * args.think))

    stats_out: list[str] = []

    def sample() -> None:
        import subprocess

        time.sleep(max(0.0, measure_from + args.duration / 2 - time.monotonic()))
        out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"],
                             capture_output=True, text=True, check=False).stdout
        stats_out.extend(line for line in out.splitlines() if args.docker_stats in line)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.concurrency)]
    if args.docker_stats:
        threads.append(threading.Thread(target=sample))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\nconcurrency={args.concurrency} think={args.think}s duration={args.duration}s users={args.users}")
    for key in ("dashboard", "shell"):
        v = lat[key]
        if not v:
            continue
        print(f"{key:9s} n={len(v):5d}  rps={len(v) / args.duration:6.1f}  p50={percentile(v, .5):6.0f} ms  p95={percentile(v, .95):6.0f} ms  "
              f"p99={percentile(v, .99):6.0f} ms  max={max(v):6.0f} ms  mean={statistics.mean(v):6.0f} ms  errors={errors[key]}")
    if stats_out:
        print("container CPU mid-run:")
        for line in stats_out:
            print("  " + line)


if __name__ == "__main__":
    main()
