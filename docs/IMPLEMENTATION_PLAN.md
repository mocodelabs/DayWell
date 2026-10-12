# Implementation plan & status

Starting point: the repository was empty (new project at `C:\Claude_code\daywell`). The plan followed the PRD's six
phases, building the reliable daily-operations core (tasks, calendar, recurrence, reminder engine) before wellness.

Legend: ✅ done and tested · 🟡 done with a documented limitation · ⬜ not in this release

## Phase 1 — Foundation ✅
- ✅ Django 5.2 + DRF modular monolith; settings split `base/dev/test/prod`; env-based config; `.env.example`
- ✅ PostgreSQL 17 + Redis 7.4 (Docker Compose for local services); Celery worker + beat
- ✅ Email auth with session cookies + CSRF; registration, login (IP throttle + account lockout), logout, password
  change/reset, email verification, session list/revoke, audit events, data export, account deletion
- ✅ Preferences (locale, zone, formats, week start, theme, accessibility, modules, layout, tone, rhythm, quiet hours)
- ✅ Design tokens (PRD palette, dark theme), app shell (collapsible sidebar, mobile top bar + bottom nav, quick-add FAB,
  up-next panel), reusable accessible components on Radix primitives
- ✅ Error envelope, request ids, JSON logs, health endpoints; CI workflow; tests

## Phase 2 — Daily operations ✅
- ✅ Tasks: CRUD, priorities, Eisenhower quadrant, categories, tags, subtasks, deadlines, durations, links, notes;
  complete/reopen/start/postpone/cancel; overdue; search/filters/pagination; activity history
- ✅ Recurring tasks (RRULE series, materialised instances, this/series edits & deletes)
- ✅ Calendar: day/week/month (FullCalendar), all-day, location/meeting link, categories, RRULE recurrence with
  per-occurrence exceptions, attendance, conflicts, search, drag-and-drop with this/series choice, ICS import/export
- ✅ Reminder engine: absolute + relative reminders, materialised idempotent occurrences, 30 s `SKIP LOCKED` dispatcher,
  quiet hours (delay/silent), module/category gating, frequency caps, dedupe, missed detection, bounded retries,
  escalation, snooze/dismiss/complete/keep/reschedule, notification centre, diagnostics, test alarms
- ✅ Foreground alarm (AlarmProvider/AlarmDialog), honest audio reporting, Web Push with encrypted subscriptions and
  display receipts
- ✅ Today dashboard API + UI; quick add with interpreted preview

## Phase 3 — Warm interaction ✅
- ✅ Personalised, tone-aware greetings (5 tones, deterministic daily variety, weekend wording), short/detailed briefing
- ✅ Briefing never names a commitment that's already over; says "happening now" for in-progress items
- ✅ Morning briefing & evening recap notifications (system reminders computed at send time from real data)
- ✅ Briefing ↔ reminder deduplication; per-category frequency caps
- ✅ Smart day planner (suggest around fixed commitments, buffers, working hours, overload warning; accept per item)

## Phase 4 — Wellness ✅
- ✅ Generic habit engine (binary/count/duration/numeric; RRULE or N-per-week; rest days; pause/archive; history; streaks)
- ✅ Affirmations (54 original affirmations in 9 categories seeded by migration; daily pick without 30-day repeats;
  favourites; custom; history; copy/share; reminder; viewed/acknowledged tracking)
- ✅ Reading (books, notes/highlights/quotes, timer + manual sessions, stats, yearly goal, reminder)
- ✅ Fitness (routines with prep-buffer reminders, session log with optional exercises/distance/effort, planned vs done, trend)
- ✅ Hydration (targets/units, quick add, week view, interval reminders), Sleep (log, consistency, wind-down/wake reminders),
  Journal (private, gratitude, mood, prompts, search), Mindfulness (guided timer), Personal admin (category lists +
  templates for bills, renewals, chores, errands, shopping)

## Phase 5 — Insights & polish ✅
- ✅ Daily/weekly/monthly/yearly insights from source data with stated calculation rules; future days excluded
- ✅ Weekly review (reflection + stats snapshot), accomplishments, gentle suggestions; goals (manual + derived metrics)
- ✅ Onboarding (9 skippable steps, permission in context, first routine)
- ✅ Accessibility pass: labelled controls, aria-pressed toggles, alertdialog alarms, skip link, focus styles, text
  scale, reduced motion, status never by colour alone
- 🟡 Offline: app shell cached, clear offline banner, data reads that are already in memory stay visible; **no offline
  writes** (deliberate for v1 — see limitations)

## Hardening pass (2026-10-10/11) ✅ / 🟡
Baseline re-verified first (167/28/12 tests passing). Defects found by running the production stack, load and
accessibility tests — all fixed with regression tests:
- **Deployment:** container health probes rejected by `ALLOWED_HOSTS`/HTTPS redirect (stack never became healthy); nginx
  cached the backend IP (502 after any backend restart); nginx dropped CSP/X-Frame headers on pages (location-level
  `add_header`); worker/beat inherited an HTTP health check they can't pass; no TLS layer in the compose stack (now Caddy);
  backup/restore scripts didn't pass the env file the compose file requires.
- **Security:** login/registration/password-reset accepted POSTs without CSRF (login CSRF); with Redis-cached sessions,
  revocation must clear the cache (caught by a test before shipping).
- **Resilience:** a Redis outage took the whole API down (now degrades; rate limits fail open, health alerts); DB outages
  returned a generic 500 (now 503 + Retry-After); Celery logs weren't JSON.
- **Correctness:** dashboard overdue count capped at 20 and the 20 chosen were the oldest, not the most important.
- **Push:** a browser-rotated subscription was never re-registered (push would silently stop).
- **Accessibility:** text contrast (PRD muted grey 4.06:1), calendar contrast and keyboard/ARIA issues, focus lost on every
  dialog close, small touch targets — see ACCESSIBILITY.md.
- **Performance:** measured; target met at ≤10 concurrent active users on a 4-core laptop, missed at 20 (CPU-bound) — see
  TEST_PLAN.md §Performance.

## Phase 6 — Production hardening ✅ / 🟡
- ✅ Security review (see below), `check --deploy --tag security` clean, `pip-audit` and `npm audit` clean
- ✅ Dockerfiles (backend, frontend+nginx with CSP), `docker-compose.prod.yml` with health checks and ordered startup
- ✅ Backup/restore scripts; restore drill performed with the shipped scripts against the production compose stack (240 MB dataset)
- ✅ Full production stack run locally (Caddy TLS → nginx → gunicorn, PostgreSQL, Redis, worker, beat): health checks, HTTPS, CSRF/CORS, secure cookies, restarts and DB/Redis outages verified
- ✅ Playwright E2E (11-step journey incl. a real alarm + mobile flow)
- 🟡 Push delivery verified against mocked push services and the real server pipeline; **not verified on a physical
  phone** (none available) — checklist in REAL_DEVICE_TESTING.md
- 🟡 Monitoring = health endpoints + structured logs + documented alerts; no metrics backend (Prometheus/Sentry) wired

## Security review summary
| Area | Status |
|---|---|
| Cross-user access | owner-scoped querysets, owned FK fields, 404 on foreign ids — 22 automated isolation tests + E2E |
| Auth | Django hashing (PBKDF2), min length 10 + common/numeric/similarity validators, IP throttle, account lockout, session revocation on password change/reset, no account enumeration |
| CSRF/CORS | CSRF enforced on session writes (tested); CORS off by default |
| Secrets | env only; prod refuses weak secret; VAPID private key never sent to clients; push keys encrypted at rest |
| Logging | no request bodies logged; audit events contain no secrets/content |
| Headers | HSTS, secure cookies, nosniff, frame deny, CSP + Permissions-Policy in nginx |
| Push receipt endpoint | unauthenticated by necessity; signed, expiring, per-delivery token; throttled; can only mark that delivery displayed |
| Journal privacy | never logged, never sent to third parties; AI consent flag defaults off (no AI integration exists) |

## Known limitations (honest list)
1. **Background alarms are best-effort** (PWA): push notifications only, OS decides sound; no ringing when closed. Native wrapper needed for guaranteed alarms.
2. **No offline writes / background sync** in v1 — changes require a connection (clearly signposted in the UI).
3. **Weather** in the briefing is not implemented (PRD: "only if enabled and supported"; no provider chosen).
4. **External calendar sync** (Google/Outlook) not implemented — ICS import/export only (PRD lists it as a later phase).
5. **OAuth sign-in** not implemented (PRD: later phase). **Attachments** on tasks: links only, no file uploads.
6. **Book metadata lookup** not integrated (manual entry; the model is ready for it).
7. **Evening checklist** for sleep is done via habits in the "sleep" category rather than a separate checklist model.
8. **DailySummary** is computed on demand rather than stored (keeps it exact); weekly reviews do snapshot.
9. **AI suggestions** are not implemented; the setting is shown disabled.
10. Recurring-event series edits keep exceptions keyed to original times; exceptions whose original time no longer exists after a series time change are ignored.
11. Routine reminders whose prep buffer crosses midnight fire on the routine's weekday (not the previous evening).
12. Dashboard p95 < 500 ms is met at ≤10 concurrent active users on the 4-core test laptop and **missed at 20** (CPU-bound); not yet measured on production hardware.
13. Accessibility: automated checks pass, but manual screen-reader / forced-colours / voice-control checks have not been done.
14. While Redis is down, rate limits and login lockouts fail open (deliberate, logged, health alerts).
15. Production deployment verified only locally (Caddy internal CA); not yet on a public host with a real certificate.
16. Deferred features with value/risk/effort/acceptance criteria: BACKLOG.md.
