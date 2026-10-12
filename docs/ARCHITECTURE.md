# Architecture

DayWell is a **modular monolith**: one Django project (API + Celery tasks) and one React SPA. No microservices — every
domain shares one PostgreSQL database and one transaction boundary, which is what makes reminder state changes atomic.

```
 Browser / installed PWA                        Server
 ┌────────────────────────────┐   same origin   ┌───────────────────────────────────────────────┐
 │ React SPA (Vite build)     │  /api/v1/* ───► │ nginx ──► gunicorn ── Django + DRF (API)       │
 │  TanStack Query cache      │  cookies+CSRF   │                         │                     │
 │  AlarmProvider (polls,     │                 │                         ▼                     │
 │   rings, confirms display) │                 │                    PostgreSQL ◄── Celery worker│
 │ Service worker (sw.js)     │ ◄── Web Push ── │                         ▲          ▲          │
 │  shell cache, push display,│   (FCM/APNs/    │                         │          │ queue    │
 │  display receipts          │    Mozilla)     │                       Redis ◄── Celery beat    │
 └────────────────────────────┘                 └───────────────────────────────────────────────┘
```

## Backend layout (`backend/`)

| App | Responsibility |
|---|---|
| `core` | Abstract owned models, owner-scoped viewsets & FK fields, error envelope, request IDs + JSON logging, health endpoints, **time-zone and RRULE utilities**, field encryption, export registry, module gate, `seed_demo` |
| `accounts` | Email user, session auth (401 vs 403), registration/login/logout, lockout, password reset, email verification, session list/revoke, audit events, export, deletion |
| `preferences` | Per-user preferences (locale, modules, layout, tone, briefings, rhythm, quiet hours) and per-category notification preferences |
| `tasks` | Categories, tasks, subtasks, recurring task series (materialised instances), activity log |
| `events` | Calendar events, RRULE expansion, per-occurrence exceptions, conflicts, ICS import/export |
| `reminders` | **The alarm engine**: reminders, occurrences, deliveries, push subscriptions, dispatcher, channels, user actions, notification centre |
| `habits` | Generic habit engine (binary/count/duration/numeric; RRULE or N-per-week), completions, progress, streaks |
| `affirmations` | Library (seeded by migration), daily selection, favourites, custom, history |
| `reading` | Books, notes/quotes, timed and manual sessions, statistics |
| `fitness` | Routines (with reminders), workout sessions, statistics |
| `wellness` | Hydration, sleep log, private journal, mindfulness sessions |
| `insights` | Range statistics (daily/weekly/monthly/yearly), goals, weekly reviews |
| `briefing` | Today dashboard aggregation, tone-aware message templates, smart day planner, briefing notifications |

Each app keeps HTTP (views/serializers) separate from business logic (`services.py`, `dispatch.py`, `actions.py`,
`planner.py`), so the same functions run from API requests and Celery jobs.

### Conventions
- **CSRF**: enforced for authenticated writes by DRF and, via `csrf_protect`, on the anonymous auth endpoints (login, register, password reset, email verification) — DRF skips CSRF for anonymous requests, which would allow login CSRF.
- **Ownership**: every user-data model has `owner`; viewsets derive from `OwnedModelViewSet` (queryset filtered by
  `request.user`, owner stamped on create). Cross-user IDs return **404** (no existence oracle). FK inputs use
  `OwnedPrimaryKeyRelatedField`, so a user cannot link to another user's category/book/routine/habit.
- **Errors**: one envelope `{"error": {"code", "message", "fields": {field: [msgs]}}}`; unhandled errors are logged with
  the request id and return a generic 500 message.
- **State changes** run in `transaction.atomic` with `select_for_update(of=("self",))` where races matter.
- **Reminder re-derivation** runs *inside* the transaction that changed the task/event/habit, so data and its
  reminders can never disagree.
- **Optional modules** are gated by `core.modules.require_module` on writes and by the dispatcher on delivery; turning a
  module off never deletes data.

## Authentication decision
Same-origin **Django session cookies** (HttpOnly, SameSite=Lax, Secure in production) + **CSRF token** header for unsafe
methods. Rationale: the SPA is served from the same origin (nginx or Vite proxy), so cookies "just work"; nothing
sensitive lives in `localStorage`; sessions are revocable server-side (session list + revoke). Tokens/JWT would add
refresh logic and XSS exposure for no benefit here. CORS is off unless `CORS_ALLOWED_ORIGINS` is set.
Login is throttled per IP (`auth` scope) **and** locked per account after 8 failures in 15 minutes.

## Frontend layout (`frontend/src/`)

- `lib/` — `api.ts` (fetch + CSRF + error envelope), `types.ts` (API contracts), `datetime.ts` (all display through
  `Intl` with the *user's* zone), `recurrence.ts`, `quickparse.ts`, `audio.ts`, `push.ts`
- `hooks/queries.ts` — TanStack Query hooks; mutations invalidate whole domains (dashboard, tasks, calendar, alarms…)
- `features/auth/session.tsx` — `RequireAuth`, appearance (theme/reduced motion/text scale)
- `features/alarms/` — `AlarmProvider` + `AlarmDialog` (foreground alarm surface)
- `components/ui/` — accessible primitives on Radix (Dialog/AlertDialog/Switch/Toast) + feedback states
- `components/layout/` — app shell (sidebar, mobile top/bottom bars, quick-add FAB, offline + missed banners, up-next panel)
- `pages/` — one lazy-loaded module per route; Growth and Settings have nested lazy routes
- `public/sw.js` — hand-written service worker; `public/sounds/*.wav` and `public/icons/*` are generated by
  `scripts/generate_assets.py` (original synthesised tones; no third-party assets)

Design tokens live once in `styles.css` (`:root` + dark theme) and are exposed to Tailwind via `@theme inline`; components
use semantic names (`bg-surface`, `text-muted`, `bg-primary`), never hex values.

## Key technical decisions

| Decision | Choice | Why |
|---|---|---|
| Recurrence | RFC 5545 RRULE via `python-dateutil`, expanded in **floating local time** then localised | Well-tested; keeps "06:30 every weekday" at 06:30 across DST; standard for ICS |
| DST policy | Gap → shift forward by gap; overlap → first instant | RFC 5545 §3.3.5 behaviour; deterministic; tested |
| Recurring tasks | Series definition + materialised instances (unique series+date) | Tasks need per-instance completion/postpone; idempotent |
| Recurring events | Virtual expansion + exception rows keyed by original local start | Unbounded series without row explosion; standard EXDATE/RECURRENCE-ID model |
| Reminder scheduling | Materialised occurrences (14-day horizon) + 30 s beat dispatcher with `SKIP LOCKED` | Durable (rows survive restarts), idempotent (unique keys), observable (lag metric) — no in-memory timers, no ETA tasks |
| Briefing notifications | System reminders through the same engine | Inherit quiet hours, dedupe, delivery honesty |
| Calendar UI | FullCalendar 6 + Luxon plugin | Maintained, accessible-enough, named time zones, drag & drop |
| PWA | Hand-written service worker | Full control: never caches `/api`, push receipts, notification actions |
| Push keys at rest | Fernet (`FIELD_ENCRYPTION_KEYS`, MultiFernet rotation) | Endpoints/keys are device credentials |
| AI | Not used | Dashboard text is rule-based from real data (PRD: no external AI for ordinary rendering) |
| TLS / proxy | Caddy (automatic HTTPS) → nginx (SPA + /api) → gunicorn | Real certificates without manual renewal; nginx re-resolves backend IPs |
| Cache | `ResilientRedisCache` (cache errors = misses) | Redis holds only disposable data; an outage must not take the API down (rate limits fail open, health still alerts) |
| Sessions | `cached_db` (Redis read-through, PostgreSQL durable) | One query fewer per request; revocation goes through the session engine so cached copies are cleared |
| Health probes | `HealthProbeMiddleware` answers `/health/*` before host checks and the HTTPS redirect | Container probes use `127.0.0.1:8000`, which production `ALLOWED_HOSTS` rightly rejects |
| Outages | DB/cache connection errors → 503 `service_unavailable` + `Retry-After` | Tells clients and monitors an outage apart from a bug |
| App server | gunicorn `gthread` (`GUNICORN_WORKERS` × `GUNICORN_THREADS`) | Configurable concurrency; measured CPU-bound (TEST_PLAN §Performance) |
