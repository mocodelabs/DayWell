# DayWell

A calm personal companion for plans, reminders and healthy routines: tasks, calendar, alarms, a warm morning briefing,
habits, reading, fitness, affirmations, hydration, sleep, journaling and honest insights — in one installable web app.

- **Backend:** Django 5.2 + DRF, PostgreSQL 17, Redis, Celery worker + beat (`backend/`)
- **Frontend:** React 19 + TypeScript (strict), Vite, Tailwind v4, TanStack Query, React Hook Form + Zod, Radix, FullCalendar, PWA (`frontend/`)

## Quick start (local)

```bash
docker compose up -d db redis                          # PostgreSQL on 5440, Redis on 6390

cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt -c requirements.lock   # (bin/ on macOS/Linux)
# create backend/.env with DATABASE_URL=postgres://daywell:daywell@127.0.0.1:5440/daywell and REDIS_URL=redis://127.0.0.1:6390/0
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo               # optional demo account (see below)
.venv/Scripts/python manage.py runserver 127.0.0.1:8020

# reminders need these two (separate terminals; Windows needs --pool=solo and a separate beat):
.venv/Scripts/celery -A config worker --pool=solo -l info
.venv/Scripts/celery -A config beat -l info

cd ../frontend && npm install && npm run dev            # http://localhost:5193
```

Or run everything in containers: `docker compose --profile app up -d` → http://localhost:5193.

**Demo account** (local development only, created by `seed_demo`): `demo@daywell.test` / `DayWell-demo-2026`.

## Tests & checks
```bash
cd backend  && .venv/Scripts/python -m pytest -p no:warnings   # backend (PostgreSQL)
cd backend  && .venv/Scripts/ruff check .
cd frontend && npm run typecheck && npm run lint && npm test    # strict TS, oxlint (incl. jsx-a11y), Vitest
cd frontend && npm run e2e                                      # Playwright incl. axe accessibility (database daywell_e2e is flushed)
```
Current counts and results: [docs/TEST_PLAN.md](docs/TEST_PLAN.md).

## Documentation
| | |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product requirements (source of truth) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, conventions, key decisions |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Entities, constraints, time/DST rules, calculation rules |
| [docs/API_SPEC.md](docs/API_SPEC.md) | Endpoints, formats, error codes |
| [docs/NOTIFICATIONS_AND_ALARMS.md](docs/NOTIFICATIONS_AND_ALARMS.md) | Reminder engine, delivery honesty, quiet hours, push, platform limits |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phase status, security review, **known limitations** |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | What's tested and the latest results |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment (Caddy TLS), sizing, failure behaviour, VAPID, backups, monitoring, troubleshooting |
| [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) | WCAG 2.2 AA automated coverage, fixes, manual checks still required |
| [docs/REAL_DEVICE_TESTING.md](docs/REAL_DEVICE_TESTING.md) | Android/iOS notification checklist, evidence levels, native-alarm plan |
| [docs/BACKLOG.md](docs/BACKLOG.md) | Deferred features with value, risks, effort, acceptance criteria |

## About alarms (please read)
While DayWell is open, due alarms appear and play your chosen sound (if the browser allows audio). When it's closed,
reminders arrive as push notifications where the platform supports them — the operating system decides the sound, and
silent / do-not-disturb modes win. A web app cannot guarantee a ringing alarm on a sleeping phone, so DayWell never claims
one rang unless your device confirmed it. For anything critical, also set your device's own alarm.
