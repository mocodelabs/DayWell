# Data model

PostgreSQL 17. All absolute timestamps are `timestamptz` stored in UTC. Wall-clock values that must survive DST and
travel (event start/end, task date/time, habit and reminder times) are stored as `date` + `time` **plus** the IANA zone
they belong to. Every user-owned row has an `owner` FK with `ON DELETE CASCADE` (account deletion removes everything).

## Entities (PRD §17 mapping)

| PRD entity | Implementation | Notes |
|---|---|---|
| User | `accounts.User` | Email login (case-insensitive unique), `display_name`, `email_verified_at` |
| — | `accounts.UserSession` | Tracks logins for "active sessions" + revoke |
| AuditEvent | `accounts.AuditEvent` | login/failed/logout/password/reset/export/delete/push events; never stores secrets or content; `SET_NULL` on user delete |
| UserPreference | `preferences.UserPreference` | Locale/formats/zone, theme, reduced motion, text scale, onboarding, `modules` (JSON flags), `dashboard_layout`, tone, briefing style/times, wake/bed/work hours, targets, sound/volume, quiet hours (start/end/days/behaviour), missed policy, AI consents (off) |
| NotificationPreference | `preferences.NotificationPreference` | One per user+category (unique): enabled, channels, sound, vibrate, snooze, bypass quiet hours, `min_gap_minutes` (frequency cap) |
| Category | `tasks.Category` | Unique per owner (case-insensitive) |
| Task | `tasks.Task` | priority, `important` (Eisenhower axis), status, `scheduled_date` + `scheduled_time` + derived `scheduled_at` (UTC), `time_zone`, duration, deadline, tags (JSON), link, `completed_at`, `postponed_count`, series link, `deleted_at` (only for series instances) |
| TaskSubtask | `tasks.TaskSubtask` | ordered checklist |
| TaskRecurrence | `tasks.TaskSeries` | RRULE + template fields + `checklist`; `generated_until`; instances unique on `(series, occurrence_date)` |
| — | `tasks.TaskActivity` | append-only: created/started/completed/reopened/postponed(from→to)/rescheduled/cancelled — source for insights |
| CalendarEvent + EventRecurrence | `events.CalendarEvent` | wall-clock start/end + zone; derived `start`/`end` (first occurrence, UTC) and `series_end` (NULL = forever); RRULE; status; attendance; `ical_uid` |
| — | `events.EventException` | one occurrence changed/cancelled, keyed by original local start (`YYYY-MM-DDTHH:MM` or date); `override_start/end` UTC for range queries; unique `(event, original_key)` |
| Reminder | `reminders.Reminder` | absolute (date+time+RRULE+zone) or relative (offset before task start/deadline, task series, or event); habit link; sound/vibrate/snooze/priority/bypass/escalation; `system_key` for module-owned reminders (unique per owner when set); `archived` |
| ReminderOccurrence | `reminders.ReminderOccurrence` | one firing: `scheduled_for` (original) vs `fire_at` (moved by quiet hours), status machine, timestamps for sent/delivered/audio/acted/dismissed/completed/snoozed/read, attempts/backoff, escalations, snooze parent chain, **`idempotency_key` UNIQUE** |
| NotificationDelivery | `reminders.NotificationDelivery` | one attempt on one channel: result `accepted` (handed over) vs `delivered` (client confirmed), transient flag, retry count/time, HTTP status, error |
| DeviceSubscription | `reminders.DeviceSubscription` | Web Push; `endpoint_hash` (sha256, unique), endpoint + keys **Fernet-encrypted** |
| Habit + HabitSchedule | `habits.Habit` | schedule is `schedule_rule` (RRULE over dates) **or** `times_per_week`; target type/value/unit; reminder time; active/paused/archived (`paused_at`) |
| HabitCompletion | `habits.HabitCompletion` | unique `(habit, date)`: done / partial / skipped(rest day), value |
| Affirmation / UserAffirmation | `affirmations.*` | library rows have `owner NULL` (seeded by migration 0002); one `UserAffirmation` per user per day (unique); favourites |
| Book / ReadingSession | `reading.*` | + `BookNote` (note/highlight/quote); at most one running timer per user (partial unique index on `ended_at IS NULL`) |
| WorkoutRoutine / WorkoutSession | `fitness.*` | routine days (0=Mon), time, prep buffer, reminder flag; sessions with optional distance/exercises/effort |
| WaterIntake | `wellness.WaterIntake` | always stored in ml |
| JournalEntry | `wellness.JournalEntry` | private; gratitude (≤3), mood (optional) |
| — | `wellness.SleepLog`, `wellness.MindfulnessSession` | one sleep log per wake date |
| Goal | `insights.Goal` (+ `GoalCheckIn`) | manual or derived metric (books, reading minutes, workouts, habit completions, tasks) |
| WeeklyReview | `insights.WeeklyReview` | unique per owner+week; stores a **stats snapshot** at save time (reproducible) |
| DailySummary | *computed, not stored* | **Intentional simplification:** daily figures are computed on demand from source rows (`insights.services.range_stats`), so they can never drift from the data. Weekly reviews snapshot their numbers. |

## Occurrence status machine

```
scheduled ──claim──► dispatching ──► sent ──► snoozed | dismissed | completed | acknowledged | rescheduled
    │                    │  └──────► scheduled (transient failure, backoff)   └► failed
    │                    └─────────► skipped (module/category off, item done, frequency cap, duplicate)
    │                    └─────────► missed (older than REMINDER_STALE_AFTER when first seen)
    │                    └─────────► scheduled with later fire_at (quiet hours: delay)
    └──(definition changed)──► cancelled (history kept; revived if the change is undone)
```

## Time & DST rules
- Nonexistent local time (spring forward): shifted forward by the gap (02:30 → 03:30).
- Ambiguous local time (fall back): first instant.
- Day boundaries are computed per zone, so DST days are 23 or 25 hours long.
- **Travel:** changing your time zone moves *floating* items (absolute reminders, habits) to the new zone; calendar
  events and timed tasks keep the zone they were created in.

## Calculation rules (insights)
Documented in every insights response (`definitions`) and summarised here:
- Only days **up to today** are counted — future plans never lower a rate.
- Task completion rate = completed ÷ (planned − cancelled); planned = tasks scheduled in the period + times postponed out of it.
- Habit consistency = done ÷ (scheduled − rest days); partly-done doesn't count as done.
- Habit streaks: consecutive scheduled days done; rest days neutral; today not yet done isn't a miss. N-per-week habits count consecutive weeks meeting the target.
- Rates are `null` (shown "—") when the denominator is 0.

## Indexes & constraints (highlights)
`(status, fire_at)` and `(owner, status, fire_at)` on occurrences (dispatcher + alarm queries); `(owner, status, scheduled_date)`,
`(owner, deadline)`, `(owner, completed_at)` on tasks; `(owner, start)`, `(owner, series_end)` on events;
unique: occurrence `idempotency_key`, task `(series, occurrence_date)`, exception `(event, original_key)`,
habit completion `(habit, date)`, notification pref `(user, category)`, reminder `(owner, system_key)` where set,
one daily affirmation, one sleep log per day, one running reading timer, one weekly review per week.
