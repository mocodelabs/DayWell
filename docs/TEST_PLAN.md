# Test plan & results

All suites run against **PostgreSQL 17 and Redis 7.4** (the production engines). Time-dependent behaviour uses a
controlled clock (`time_machine`, explicit `now=`); no test waits in real time for a reminder.

## How to run
```bash
docker compose up -d db redis
cd backend  && .venv/Scripts/python -m pytest -p no:warnings && .venv/Scripts/ruff check .
cd frontend && npm run typecheck && npm run lint && npm test
cd frontend && npm run e2e        # starts its own servers; flushes database daywell_e2e and Redis db 5
```

## Latest results (2026-10-11, final regression of the hardening pass)

| Suite | Result |
|---|---|
| Backend pytest | **183 passed**, 0 failed, 0 skipped |
| Backend `ruff check` / `makemigrations --check` | clean / no changes |
| `manage.py check --deploy --tag security` (production settings) | no issues (HSTS-preload warning silenced: opt-in) |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| Frontend `tsc` strict | clean |
| Frontend `oxlint` (correctness + jsx-a11y + react-hooks, `--deny-warnings`) | clean |
| Frontend Vitest | **34 passed** (3 files) |
| `npm audit` (prod and dev deps) | 0 vulnerabilities |
| Playwright (Chromium desktop + Pixel 7) | **43 passed** — journey (11), mobile (1), regressions (1), accessibility (30) |
| Production Docker stack (Caddy → nginx → gunicorn, PostgreSQL, Redis, worker, beat) | all 8 services healthy; **24/24** HTTPS checks |
| Backup → restore drill (shipped scripts, 240 MB dataset) | counts restored exactly; stack healthy |

**Baseline before this pass** (re-run, not assumed): 167 backend, 28 frontend, 12 e2e — all passing, no skips.
Gaps at baseline: no frontend linter, no accessibility automation, production stack never run together, no load test.

## Backend coverage (pytest)
Time & recurrence (DST gap/overlap, 23/25 h days, RRULE validation, weekday/monthly/biweekly series); ownership sweep
(14 resource types + aliases); health & settings (probes bypass host check/HTTPS redirect, request ids incl. Django's
own error logs, 500 envelope hides details, **DB outage → 503**, **cache outage keeps API and login working**,
`check_scheduler`, prod refuses weak secrets, prod security flags); auth (registration, lockout, **CSRF on anonymous
endpoints**, reset, verification, export, deletion, **session revocation with cached sessions**); tasks (CRUD, transitions,
recurrence edits, idempotent materialisation); calendar (DST series, exceptions, conflicts, ICS round-trip); reminder
engine (sync idempotency, dispatch rules, quiet hours, frequency caps, claims, recovery, snooze/dismiss/complete, push
accepted≠delivered, retries, expiry, **blocked-audio snooze chain keeps one pending repeat and never records audio**);
habits; modules & insights (incl. **future days excluded**, **praise only when earned**, **briefing never names a past
commitment**, **overdue count not capped, urgent first**).

## Frontend coverage (Vitest)
Quick-entry parser, recurrence, zone/DST conversion, audio controller honesty; login/register forms; task completion;
quick add saves exactly the preview; task form validation; alarm dialog actions; **AlarmProvider integration: blocked
audio reported as `blocked`, `played` only when playback started, silent alarms never play, one tap = one snooze
request**; Today loading/data/error/offline; habits; mobile navigation; permission denied; **push subscription
re-sync**; **dialog returns focus to its opener**.

## Browser coverage (Playwright)
- `journey.e2e.ts` — register → onboarding → quick-add task → event → reminder + real alarm → habit → book/session →
  workout → dashboard → notification preferences → second user gets 404/empty lists.
- `mobile.e2e.ts` — phone flow, bottom navigation, no horizontal scroll.
- `regressions.e2e.ts` — calendar opens scrolled to the user's working hours.
- `a11y.e2e.ts` — see [ACCESSIBILITY.md](ACCESSIBILITY.md).

## Production stack verification (local Docker, isolated project `daywell-prodtest`, throwaway env file)
HTTP→HTTPS redirect (308); SPA over TLS; CSP / X-Frame-Options / nosniff on every response; hashed assets immutable;
`index.html`, `sw.js`, manifest no-cache; Django admin static via WhiteNoise; health ready/scheduler through the proxy;
anonymous API 401; Secure CSRF cookie; HSTS; **POST without CSRF → 403; foreign Origin → 403**; no CORS for foreign
origins; registration 201 with **Secure + HttpOnly** session cookie; authenticated CRUD; journal write; real test alarm
dispatched; `X-Request-ID` on responses; login rate limiting (429 after repeated failures).

Resilience (each actually performed): restart of backend+worker+beat with a reminder pending → fired once, 21 s late;
PostgreSQL stopped across a reminder's due time → API 503 (after fix; was 500), readiness 503, liveness 200, SPA loads,
automatic recovery, reminder delivered once 47 s late; Redis stopped → API, login and dashboard keep working (after fix;
was 503 everywhere), readiness 503, worker reconnects, scheduler healthy 7 s after Redis returns. Log scan across all
services: no passwords, journal text, DB/Redis passwords or session cookies.

## Performance (PRD §18.1: dashboard p95 < 500 ms under normal load)

**Environment:** one laptop — Intel i7-10510U (4 cores / 8 threads, 1.8 GHz), 15.8 GB RAM, Windows 11, Docker Desktop
(WSL2, 8 vCPU / 8 GB). The full production stack ran in Docker (Caddy TLS → nginx → gunicorn gthread 4×4 → PostgreSQL 17,
Redis, Celery worker + beat dispatching reminders). **The load generator ran on the same machine**, competing for CPU.

**Dataset:** `seed_load` — 100 heavy users + 7 others: 156k tasks, 214k reminder occurrences, 205k habit completions,
15.5k events (incl. recurring series with exceptions), 30k reading sessions, 150k water entries; 240 MB database, ANALYZEd.
Per user: ~1,500 historical tasks, 20 daily reminders, 8 habits with a year of completions.

**Workload:** `deploy/loadtest/loadtest.py` — N virtual users, each signed in as a different seeded user, repeatedly
loading the Today screen exactly as the app does (`/dashboard/today/` + active alarms + upcoming alarms + unread count)
with 0.5–1.5 s think time; 15 s warm-up, then 90–120 s measured, client-side latency through TLS. Rate limits were
raised in the throwaway test env (one IP signs in 100 users) — this measures the application, not the limiter.

| Concurrent active users | Dashboard req/s | p50 | **p95** | p99 | Shell calls p95 | Errors | Verdict |
|---|---|---|---|---|---|---|---|
| 1 (no think time) | 4.0 | 85 ms | **173 ms** | 235 ms | 75 ms | 0 | meets target |
| 5 | 3.9 | 137 ms | **336 ms** | 553 ms | 90 ms | 0 | meets target |
| 10 (clean run) | 7.5 | 161 ms | **408 ms** | 709 ms | 120 ms | 0 | meets target |
| 20 | 10.2 | 436 ms | **1,033 ms** | 1,519 ms | 426 ms | 0 | **misses target** — host CPU saturated |

Before optimisation, 20 users gave p95 1,052–1,580 ms at 7.4 dashboards/s; after, throughput rose ~40% (10.2/s) at
similar p95. At 10 users mid-run CPU was backend ≈1.8 cores, PostgreSQL ≈0.5 core; at 20 users backend ≈4.5 cores
— **the app is CPU-bound in Python, not database-bound.**

**Profiling:** 20 SQL queries per dashboard (bounded; no N+1 — no query shape repeats); slowest single query ~0.1 ms in
`EXPLAIN ANALYZE`; existing indexes are used. Python time is spread across ORM compilation, serialization and recurrence
expansion (~12 ms/dashboard for year-old series).

**Optimisations made (each justified by the profile):** alarm list endpoints skip loading 12 notification preferences
when empty (the common polled case); the app shell no longer fetches the full missed-alarm list for a count the
dashboard already returns (−1 request per page view); sessions read from Redis (`cached_db`, −1 query per request);
gunicorn configurable gthread workers. **Correctness bug found:** overdue count was capped at 20 (fixed, tested).

**Interpretation:** "10 concurrent active users each loading Today about once a second" is far heavier than typical
use (a real user opens Today a few times a day; background polling is one light request per 20 s), but this run does
not establish a user count. **The target is met at ≤10 concurrent users on this hardware and missed at 20.** Remaining
bottleneck: Python CPU per dashboard (~85 ms single-user). Next steps if needed: dedicated server CPUs (the generator
won't share them), more `backend` replicas, short per-user caching of the dashboard's static parts, or anchoring
recurrence expansion nearer the query window.

## Not covered / still to do
- Physical Android/iOS push testing — checklist in [REAL_DEVICE_TESTING.md](REAL_DEVICE_TESTING.md) (no device available).
- Manual screen-reader and forced-colours checks — [ACCESSIBILITY.md](ACCESSIBILITY.md).
- Production deployment on a Linux server with a real domain/certificate (verified locally with Caddy's internal CA only).
- Load test on production-class hardware with the generator on a separate machine.
