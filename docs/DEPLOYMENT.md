# Deployment & operations

## Services

| Service | Image / command | Notes |
|---|---|---|
| `db` | `postgres:17-alpine` | the only stateful store that matters — back it up |
| `redis` | `redis:7.4-alpine` (AOF, password) | Celery broker + cache (throttles, lockouts, beat heartbeat). Losing it loses nothing durable |
| `migrate` | backend image: `migrate` + `seed_affirmations` | one-shot, runs before the app starts; safe to re-run |
| `backend` | backend image: gunicorn `config.wsgi` | health: `/health/ready/` |
| `worker` | `celery -A config worker` | sends reminders, retries, escalations; scale horizontally |
| `beat` | `celery -A config beat` | **exactly one** instance; drives dispatch every 30 s |
| `web` | frontend image: nginx serving the SPA + proxying `/api`, `/health`, `/static`, `/django-admin` (re-resolves `backend` via Docker DNS, so backend restarts don't cause 502s) | health: `/healthz` |
| `proxy` | `caddy:2.8-alpine` with `deploy/Caddyfile`: **automatic HTTPS** (Let's Encrypt for `DAYWELL_SITE_ADDRESS`; an internal CA for `localhost`), HTTP→HTTPS redirect, sets `X-Forwarded-*` | ports `HTTP_PORT`/`HTTPS_PORT` (80/443) |

Health checks: `backend` → `/health/ready/` (DB + cache); `worker` → `celery inspect ping`; `beat` → `manage.py check_scheduler` (heartbeat scheduled by beat **and** executed by a worker within 3 min, dispatch lag < 5 min — usable from external monitoring too). `/health/*` is answered before host validation and the HTTPS redirect so container probes work.

## First deployment (Docker Compose)

```bash
cp .env.example .env.prod          # fill in every value; never commit it
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml ps
curl -fsS http://localhost:8080/health/ready/
curl -fsS http://localhost:8080/health/scheduler/   # "ok" within ~1 minute of start
```

Set `DAYWELL_SITE_ADDRESS` to your public hostname (DNS pointing at the host, ports 80/443 open) and Caddy obtains and
renews the certificate. Keep `NUM_PROXIES=2` (Caddy + nginx) — it makes per-IP rate limits unspoofable; add 1 if a cloud
load balancer sits in front too. `SECURE_SSL_REDIRECT` defaults on in production settings.

`DAYWELL_ENV_FILE` selects a different env file (default `.env.prod`), e.g. a throwaway verification stack:
`DAYWELL_ENV_FILE=/tmp/test.env docker compose -p daywell-check -f docker-compose.prod.yml --env-file /tmp/test.env up -d --build`.

Create an operator account for the Django admin (optional): `docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser`.

## Free trial hosting: Vercel + Neon (showcase deployment)

Live at **https://daywell-three.vercel.app** (Vercel Hobby team `mocode-labs`, project `daywell`; Neon free Postgres
`daywell-db` in Frankfurt, connected through the Vercel Marketplace). Meant for trials and demos, not production.

How the Docker stack maps onto it:

| Docker stack | Vercel trial |
|---|---|
| Caddy + nginx | Vercel edge; `vercel.json` routes `/api`, `/health`, `/internal`, `/django-admin`, `/static` to the `api` service (Django) and everything else to the `web` service (Vite build, SPA fallback); security headers/CSP set in `vercel.json` |
| gunicorn | Django as one Vercel Function (Python 3.13, region `fra1`); `collectstatic` runs automatically at build |
| PostgreSQL | Neon via the pooled `DATABASE_URL` (`DB_CONN_MAX_AGE=0`, `DB_DISABLE_SERVER_SIDE_CURSORS=true`) |
| Redis | none: `CACHE_BACKEND=database` (table `daywell_cache`, created with `createcachetable`) and DB sessions |
| Celery worker + beat | `apps/core/scheduler.py`: the same periodic jobs run from `GET /internal/tick/` (Bearer `SCHEDULER_TOKEN`) and, with `INLINE_SCHEDULER=true`, from the in-app alarm poll (every 20 s while the app is open). A daily Vercel cron also calls the tick (Hobby crons are daily only) |

**Reminder timing limitation:** while nobody has DayWell open, the only clock is the daily cron, so push notifications to
closed apps can be hours late. For timely push, point a free external pinger (e.g. cron-job.org) at
`https://daywell-three.vercel.app/internal/tick/` every minute with the header `Authorization: Bearer <SCHEDULER_TOKEN>`.
`/health/scheduler/` reports 503 when the clock has stalled for more than 3 minutes.

Other trial limits: email goes to the function log (console backend), so password-reset mails are not delivered; Neon's
free compute sleeps when idle (first request after a pause is slower); Hobby functions run in one region.

Operations:
```bash
vercel deploy --prod                       # from the repo root (linked project)
vercel env ls production                   # names only; secrets are stored as sensitive
vercel env pull <file> --environment=production   # DATABASE_URL_UNPOOLED for migrations
DATABASE_URL=<unpooled url> CACHE_BACKEND=database python manage.py migrate   # run before deploying schema changes
```
Demo data was loaded with `manage.py seed_demo` (demo@daywell.test / DayWell-demo-2026 — public demo credentials).

## Configuration
All configuration is environment variables — see `.env.example` (documented inline). Production settings
(`config.settings.prod`) **refuse to start** without a strong `DJANGO_SECRET_KEY` and a `DATABASE_URL`, and enable HSTS,
secure cookies, SSL redirect and JSON logs. `SECURE_HSTS_PRELOAD` is opt-in.

### VAPID keys (Web Push)
```bash
docker compose -f docker-compose.prod.yml run --rm backend python -c "
import base64; from py_vapid import Vapid01; from cryptography.hazmat.primitives import serialization as s
v = Vapid01(); v.generate_keys(); b = lambda x: base64.urlsafe_b64encode(x).rstrip(b'=').decode()
print('VAPID_PUBLIC_KEY=' + b(v.public_key.public_bytes(s.Encoding.X962, s.PublicFormat.UncompressedPoint)))
print('VAPID_PRIVATE_KEY=' + b(v.private_key.private_numbers().private_value.to_bytes(32, 'big')))"
```
Put both in `.env.prod`, set `VAPID_SUBJECT=mailto:you@yourdomain`, restart `backend` and `worker`. Changing the key pair
invalidates every existing subscription — users re-enable push from Settings → Notifications.

## Migrations
`migrate` runs automatically on every `up`. Manually: `docker compose -f docker-compose.prod.yml run --rm migrate`.
Django migrations are idempotent (already-applied ones are skipped); the affirmation seed uses insert-if-missing.
Before deploying a release, CI runs `makemigrations --check` so no model change ships without its migration.

## Static assets
The frontend image builds the SPA (`npm run build`) and nginx serves `/assets/*` immutable for a year, `index.html`,
`sw.js` and the manifest with `no-cache` so updates reach installed PWAs. Django admin static files are collected into
the backend image at build time and served by WhiteNoise.

## Capacity and sizing
gunicorn runs threaded workers: `GUNICORN_WORKERS` (default 4 ≈ cores) × `GUNICORN_THREADS` (default 4). Each thread may
hold one PostgreSQL connection, so keep workers × threads (+ Celery concurrency) well under PostgreSQL's
`max_connections` (100). The app is **CPU-bound in Python**: on a 4-core laptop the dashboard p95 stays under 500 ms up
to ~10 concurrent active users each loading Today every second (TEST_PLAN.md §Performance); beyond that add CPU or
`backend` replicas. Load-test with `deploy/loadtest/loadtest.py` against a stack seeded by
`manage.py seed_load --force` — never against real users.

## Failure behaviour (verified in the production stack)
| Event | What users see | Recovery |
|---|---|---|
| backend/worker/beat restart | brief 502 only while gunicorn starts | automatic; scheduled reminders still fire (durable rows) |
| PostgreSQL down | API → **503** `service_unavailable` ("temporarily unavailable, your data is safe"); SPA loads; `/health/ready/` 503, `/health/live/` 200 | automatic reconnect; reminders due during the outage dispatch once on recovery if < 15 min late, otherwise listed as missed |
| Redis down | **API keeps working**; rate limits and login lockouts fail **open** (warning logged ≤1/min/process); `/health/ready/` 503 so monitoring alerts; reminder dispatch pauses | worker/beat reconnect automatically; sessions fall back to PostgreSQL (`cached_db`) |

## Backup and restore
Both scripts read `ENV_FILE` (default `.env.prod`), `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME` from the environment.
- **Backup:** `./deploy/backup.sh` → `backups/daywell-<UTC timestamp>.dump` (custom format), verified with
  `pg_restore --list`, keeps `KEEP_DAYS` (14) days. Schedule it daily (cron/systemd timer) and copy dumps off-host
  (object storage with versioning). Redis needs no backup.
- **Restore:** `./deploy/restore.sh backups/<file>.dump` — asks for confirmation, stops app containers, restores with
  `--clean --if-exists`, runs migrations, restarts. Check `/health/ready/` and `/health/scheduler/` afterwards.
  Occurrences whose time passed while restoring become "missed" for review (no burst of stale alarms).
- **Verified (2026-10-10) with the shipped scripts against the production compose stack:** backup → add data → restore →
  row counts back to the backup's values, the post-backup row gone, stack healthy (24/24 HTTPS checks). Repeat quarterly.

## Logging & monitoring
- Logs are JSON lines on stdout (`LOG_JSON` on in production) — API, Celery worker and beat alike — with `request_id`
  (also returned as `X-Request-ID`). Request bodies are never logged: a scan of all service logs after a session with a
  password, a journal entry and the DB/Redis passwords found none of them. Celery masks the broker password.
- Alert on: `/health/ready/` non-200; `/health/scheduler/` 503 (beat dead or dispatch lag > 5 min); log lines
  `reminder dispatch is lagging`; worker/beat container restarts; spikes of `dispatch failed` or `push failed`.
- Useful SQL: `SELECT status, count(*) FROM reminders_reminderoccurrence WHERE fire_at > now() - interval '1 day' GROUP BY 1;`

## Secret rotation
| Secret | How |
|---|---|
| `DJANGO_SECRET_KEY` | change and restart → all sessions and reset/verify links are invalidated (users sign in again) |
| `FIELD_ENCRYPTION_KEYS` | prepend a new Fernet key (`new,old`), restart; old values still decrypt; re-subscribing re-encrypts; remove the old key later. If unset, a key derived from `DJANGO_SECRET_KEY` is used — then rotating the secret key makes stored push subscriptions undecryptable (they are deactivated and users re-enable push) |
| `POSTGRES_PASSWORD` / `REDIS_PASSWORD` | `ALTER USER …` / `CONFIG SET requirepass`, update `.env.prod`, restart |
| VAPID keys | see above (forces re-subscription) |
| SMTP credentials | update and restart backend |

## Troubleshooting

| Symptom | Check |
|---|---|
| Reminders never fire | `/health/scheduler/` or `docker compose exec beat python manage.py check_scheduler`; is `beat` running (exactly one)? `worker` logs for `reminders.dispatch_due` every 30 s |
| 503 `service_unavailable` from the API | PostgreSQL unreachable — check `db` health and connection limits |
| Reminders fire late | dispatcher lag in diagnostics; worker concurrency; DB load |
| Push "accepted" but nothing on the phone | OS battery optimisation / DND; site notification permission; iOS needs the Home-Screen app |
| Push always `expired` | subscription revoked or VAPID keys changed — re-enable push on the device |
| "Sound was blocked" | browser autoplay policy — interact with the page; check site sound settings |
| 403 CSRF on login | `CSRF_TRUSTED_ORIGINS` must include the public `https://` origin; cookies require same origin |
| 429 on login | IP throttle or account lockout (15 min) — or `NUM_PROXIES` wrong so all users share one IP |
| Wrong local times | user's time zone in Settings → Profile; events keep the zone they were created in |

## Local development (no Docker for the app)
```bash
docker compose up -d db redis
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt -c requirements.lock
cp ../.env.example .env   # then point DATABASE_URL/REDIS_URL at 127.0.0.1:5440 / 6390 and set DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate && python manage.py seed_demo
python manage.py runserver 127.0.0.1:8020
celery -A config worker --pool=solo -l info      # Windows needs --pool=solo
celery -A config beat -l info                    # separate process (-B is not supported on Windows)
cd ../frontend && npm install && npm run dev     # http://localhost:5193
```
Or everything in containers: `docker compose --profile app up -d`.
