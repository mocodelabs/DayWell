# API specification (v1)

Base path `/api/v1/`. JSON in and out. A machine-readable OpenAPI schema is served at `/api/schema/` with Swagger UI at
`/api/docs/` (plain `APIView` endpoints below are documented here by hand).

## Conventions
- **Auth:** session cookie `daywell_session`. Unsafe methods require header `X-CSRFToken` = cookie `daywell_csrftoken`
  (set by `GET /auth/csrf/`). Unauthenticated → `401`.
- **Ownership:** every resource is scoped to the signed-in user. Another user's id → `404`.
- **Pagination:** list endpoints return `{count, next, previous, results}`; `?page=` and `?page_size=` (max 200).
- **Search/order:** `?search=` and `?ordering=` where noted.
- **Times:** absolute instants are ISO 8601 with offset (UTC). Wall-clock fields (`scheduled_date`, `start_time`, …) are local to the item's `time_zone`.
- **Errors:**

```json
{ "error": { "code": "validation_error", "message": "Please correct the highlighted fields.", "fields": { "title": ["Give the task a title."] } } }
```

| Status | `code` examples | Meaning |
|---|---|---|
| 400 | `validation_error`, `invalid` | bad input / invalid rule |
| 401 | `not_authenticated` | no session |
| 403 | `permission_denied`, `module_disabled` | forbidden / optional module turned off |
| 404 | `not_found` | missing or not yours |
| 409 | `conflict`, `already_handled` | valid request, wrong state (e.g. completing a cancelled task, acting on a handled alarm) |
| 429 | `throttled`, `locked_out` | rate limit / account lockout |
| 500 | `server_error` | generic, details only in logs (with `X-Request-ID`) |

## Health (unauthenticated)
`GET /health/live/` · `GET /health/ready/` (DB + cache, 503 if degraded) · `GET /health/scheduler/` (beat heartbeat age and oldest due occurrence lag; 503 when stalled)

## Accounts — `/auth/`, `/account/`
| Method & path | Body / params | Notes |
|---|---|---|
| GET `/auth/csrf/` | — | sets CSRF cookie |
| POST `/auth/register/` | `email, password, display_name?, time_zone?` | 201 → `{user, preferences}` (logged in) or `{verification_required}` |
| POST `/auth/login/` | `email, password` | `{user, preferences}`; 429 `locked_out` after 8 failures/15 min |
| POST `/auth/logout/` | — | 204 |
| GET/PATCH `/auth/me/` | `display_name` | |
| POST `/auth/password/change/` | `current_password, new_password` | signs out other sessions |
| POST `/auth/password/reset/` | `email` | same response whether or not the account exists |
| POST `/auth/password/reset/confirm/` | `uid, token, new_password` | signs out everywhere |
| POST `/auth/email/verify/` · `/auth/email/verify/resend/` | `uid, token` | |
| GET `/auth/sessions/` · DELETE `/auth/sessions/{key}/` | | |
| GET `/account/export/` | | full JSON export (attachment) |
| POST `/account/delete/` | `password, confirm: "DELETE"` | permanent |

## Preferences
`GET/PATCH /preferences/` (see `Preferences` in `frontend/src/lib/types.ts`; `modules` patch merges; `complete_onboarding: true` stamps onboarding) ·
`GET /preferences/sounds/` · `GET /notification-preferences/` · `PATCH /notification-preferences/{id}/` (`enabled, channels[in_app|push], sound, vibrate, snooze_minutes, bypass_quiet_hours, min_gap_minutes`)

## Tasks
| Method & path | Notes |
|---|---|
| GET `/tasks/` | filters: `status` (csv), `priority` (csv), `date_from`, `date_to`, `category`, `tag`, `open`, `inbox`, `overdue`, `admin`, `important`, `series`; `search`; `ordering` (`scheduled_date`, `deadline`, `created_at`, `priority_rank`, `completed_at`) |
| POST `/tasks/` | `title`, `description`, `notes`, `priority`, `important`, `category`, `tags[]`, `scheduled_date`, `scheduled_time`, `duration_minutes`, `deadline`, `link_url`, `checklist[]`, `recurrence` (RRULE), `reminders[{offset_minutes, anchor: start\|deadline}]` → returns the first instance for recurring tasks |
| GET/PATCH/DELETE `/tasks/{id}/` | `?scope=this\|series` for series instances (delete series keeps completed history) |
| POST `/tasks/{id}/complete/` · `/reopen/` · `/start/` · `/cancel/` | idempotent where sensible; 409 on invalid transitions |
| POST `/tasks/{id}/postpone/` | `{preset: tomorrow\|next_week\|weekend}` or `{to_date, to_time?}` |
| GET/POST `/tasks/{id}/subtasks/` · PATCH/DELETE `/tasks/{id}/subtasks/{sid}/` | |
| CRUD `/categories/` | `name, color (forest\|sage\|terracotta\|amber\|sky\|plum\|slate\|rose), icon` |

Task response adds `scheduled_at`, `is_overdue`, `quadrant` (`do|schedule|delegate|later`), `series_rule`, `reminders[]`, `subtasks[]`.

## Calendar
| Method & path | Notes |
|---|---|
| CRUD `/calendar/events/` | `title, description, location, meeting_url, category, all_day, time_zone, start_date, start_time, end_date, end_time, rrule, status, attendance, reminder_offsets[]` — create/update responses include `conflicts[]` |
| GET `/calendar/events/occurrences/?start=&end=&category=&q=` | expanded occurrences (max 400 days) + `conflicts[]`; each has `key` (original local start) |
| POST `/calendar/events/{id}/occurrence/` | change one occurrence: `{key, cancelled?, title?, description?, location?, start_date?, start_time?, end_date?, end_time?, attendance?}` |
| DELETE `/calendar/events/{id}/occurrence/?key=` | cancel one occurrence |
| POST `/calendar/events/{id}/attendance/` | `{attendance, key?}` |
| GET `/calendar/events/conflicts/?start=&end=` | |
| GET `/calendar/events/export/` | `text/calendar` (RRULE + EXDATE) |
| POST `/calendar/events/import/` | multipart `file` (≤2 MB); idempotent by UID → `{created, skipped, errors[]}` |

## Reminders & alarms
| Method & path | Notes |
|---|---|
| CRUD `/reminders/` | absolute reminders: `title, message, category, priority, dtstart_date, dtstart_time, rrule, time_zone, sound, vibrate, snooze_minutes, bypass_quiet_hours, repeat_until_ack, repeat_every_minutes, enabled`; list `?kind=relative` shows task/event reminders; response has `next_fire_at`, `linked` |
| GET `/alarms/active/` | alarms the open app should ring now |
| GET `/alarms/missed/` | needs attention (missed / failed / not acted on > 1 h; last 7 days) |
| GET `/alarms/upcoming/?hours=` | |
| POST `/alarms/{id}/snooze/` `{minutes?}` · `/dismiss/` · `/complete/` · `/keep/` · `/reschedule/` `{at}` | transactional, idempotent; 409 `already_handled` |
| POST `/alarms/{id}/shown/` `{audio: played\|blocked\|muted\|unsupported}` | the app confirms display (→ delivery `delivered`) and real audio outcome |
| GET `/alarms/diagnostics/` | scheduler health, push config, subscriptions, last push, quiet hours, zone |
| POST `/alarms/test/` `{delay_seconds}` | real test occurrence through the pipeline (throttled) |
| GET `/notifications/?category=&status=&unread=` · GET `/notifications/{id}/` · POST `/notifications/{id}/read/` · POST `/notifications/read-all/` · GET `/notifications/unread-count/` | history with `deliveries[]` |
| GET `/push/config/` | `{configured, public_key}` |
| GET/POST `/push/subscriptions/` · DELETE `/push/subscriptions/{id}/` · POST `/push/unsubscribe/` `{endpoint}` | |
| POST `/push/receipt/` `{receipt}` | **unauthenticated**, signed per-delivery token from the push payload; marks only that delivery displayed |

## Habits
CRUD `/habits/` (`name, description, category, icon, color, target_type, target_value, unit, schedule_rule, times_per_week, start_date, reminder_time, streaks_enabled`) ·
GET `/habits/today/?date=` (checklist with completion, week progress, streak) ·
POST `/habits/{id}/complete/` `{date?, value?, status?: done|partial|skipped, notes?}` · `/increment/` `{date?, amount}` · `/undo/` `{date?}` · `/pause/` · `/resume/` · `/archive/` ·
GET `/habits/{id}/history/?start=&end=` · POST `/habits/reorder/` `{ids[]}`

## Growth modules (write endpoints return 403 `module_disabled` when the module is off)
- **Affirmations:** GET `/affirmations/today/` · POST `/affirmations/daily/{id}/view|acknowledge/` · CRUD `/affirmations/library/` (`?category=&favorites=true&custom=true`; library rows read-only) · POST/DELETE `/affirmations/library/{id}/favorite/` · GET `/affirmations/history/` · GET/PUT `/affirmations/reminder/` `{enabled, time, days[]}`
- **Reading:** CRUD `/reading/books/` · POST `/reading/books/{id}/complete/` · GET/POST `/reading/books/{id}/notes/` · DELETE `/reading/books/{id}/notes/{nid}/` · POST `/reading/books/{id}/timer/start/` · CRUD `/reading/sessions/` (manual: `book, date, duration_minutes, start_time?, start_page?, end_page?, pages_read?`) · GET `/reading/sessions/running/` · POST `/reading/sessions/{id}/stop/` · GET `/reading/stats/` · GET/PUT `/reading/reminder/`
- **Fitness:** CRUD `/fitness/routines/` · CRUD `/fitness/sessions/` (`?start=&end=`) · GET `/fitness/sessions/today/` · GET `/fitness/stats/`
- **Wellness:** GET/POST/DELETE `/wellness/water/` (`{amount, unit?, date?}`) · GET `/wellness/water/summary/` · GET/PUT `/wellness/water-reminder/` `{enabled, time, until, every_minutes, days}` · CRUD `/wellness/sleep/` · GET `/wellness/sleep/summary/` · PUT `/wellness/sleep-reminder/{winddown|wake}/` · CRUD `/wellness/journal/` (`?q=`) · GET `/wellness/journal/prompt/` · GET/POST/DELETE `/wellness/mindfulness/`

## Insights, goals, dashboard, planner
- GET `/insights/summary/?start=&end=` · `/insights/daily/?date=` · `/insights/weekly/?week_start=` (+ accomplishments, suggestions, review) · `/insights/monthly/?month=YYYY-MM` · `/insights/yearly/?year=`
- POST `/insights/weekly-reviews/` (upsert for the week, snapshots stats) · GET `/insights/weekly-reviews/`
- CRUD `/goals/` · GET/POST `/goals/{id}/check-ins/` · POST `/goals/{id}/complete|archive|reactivate/`
- GET `/dashboard/today/` — greeting, local date/time, briefing sentences, agenda, next up, tasks, priorities, overdue, habits, reminders summary, progress, conflicts, modules, layout, evening recap, and module sections when enabled
- GET `/planner/suggest/?date=` — suggestions only · POST `/planner/apply/` `{date, items[{task_id, start_time}]}`
