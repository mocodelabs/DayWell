# Notifications and alarms

The reminder engine is DayWell's core. Its guiding rule (PRD §3, §6.4, §18.4): **never claim an alarm sounded or a
notification was delivered without evidence.**

## Pipeline

1. **Definition** — a `Reminder` is absolute (date + time + optional RRULE in an IANA zone) or relative (N minutes before a
   task's start/deadline, every instance of a task series, or every occurrence of a calendar event). Module-owned
   reminders (daily affirmation, reading, routine, hydration, wind-down, wake, morning briefing, evening recap) use a
   `system_key`.
2. **Materialisation (`sync_reminder`)** — computes the desired occurrences for the next `REMINDER_HORIZON_DAYS` (14) and
   reconciles: creates missing ones (`bulk_create` on the **unique `idempotency_key`**), revives ones that became
   desired again, and **cancels** (never deletes) scheduled ones that are no longer wanted. Running it twice is a no-op.
   It runs inside the same transaction as the change that caused it (task postponed, event moved, habit paused…) and
   every 15 minutes (`reminders.extend_horizon`) to roll the window forward.
3. **Dispatch (`reminders.dispatch_due`, every 30 s via Celery beat)** —
   - recovers rows stuck in `dispatching` > 5 min (worker crash) back to `scheduled`;
   - **claims** due rows with `SELECT … FOR UPDATE SKIP LOCKED` and marks them `dispatching` — two workers can never take
     the same occurrence; a Redis lock also prevents overlapping runs;
   - evaluates each (first match wins): reminder disabled → `cancelled`; older than `REMINDER_STALE_AFTER` (15 min) →
     `missed`, **never pushed late**; module off → `skipped`; category off → `skipped`; linked task closed / habit done or
     paused → `skipped`; quiet hours → delayed to quiet-hours end (or delivered **silently** in-app); category frequency
     cap → `skipped` (high/critical exempt); same target already alerted within 60 s → `skipped` (dedupe);
   - delivers on the enabled channels and records a `NotificationDelivery` per attempt.
4. **Retries** — transient push failures (network, 429, 5xx) retry at 30 s, 2 min, 8 min; permanent ones don't; 404/410
   deactivate the subscription. Internal errors retry with bounded attempts, then `failed`.
5. **Escalation** — reminders with "keep reminding until I respond" re-alert every N minutes, at most 3 times.

Lateness budget: an occurrence is dispatched within ~30 s of its time while beat and a worker are up. Lag is reported at
`/health/scheduler/` and in Settings → Notifications.

## Delivery channels and what "delivered" means

| Channel | When it's attempted | `accepted` means | `delivered` means |
|---|---|---|---|
| In-app (`in_app`) | category channel enabled | the open app can see it at `/alarms/active/` | the app **displayed** it (`POST /alarms/{id}/shown/`) |
| Web Push (`push`) | category channel enabled, VAPID configured, device subscribed, not silent | the push service returned 2xx | the service worker **displayed** it and posted a signed receipt |

Audio is tracked separately: `audio_status` is `played` only if the browser's `play()` promise resolved; `blocked` if
autoplay policy refused; `muted` for silent (quiet-hours) alarms. `audio_played_at` is set only for `played`.

Every notification carries `tag = occ-<id>`, so if transport-level at-least-once delivery ever produces a duplicate, the
operating system replaces rather than stacks it.

### Adding a native channel
Implement `DeliveryChannel.deliver(occurrence, ctx) -> list[NotificationDelivery]` in `apps/reminders/channels.py` (e.g.
FCM/APNs high-priority alarms from a native Android/iOS wrapper using platform alarm APIs) and add it to `CHANNELS` and to
`NotificationPreference.Channel`. Sync, dispatch rules, snooze and history are unchanged. No native channel ships in v1.

## In the browser
- `AlarmProvider` polls `/alarms/active/` every 20 s while visible, on focus, and when the service worker reports a push.
  Upcoming occurrences (next 2 h) schedule a *refetch* at their exact time so the in-app alarm is punctual — **browser
  timers never decide whether an alarm exists**; the server does.
- One shared audio controller: the same alarm can't start twice; a second alarm waits ("2 more waiting").
- First user gesture "unlocks" audio; if the browser still blocks it, the dialog says so and offers **Play sound**.
- When the tab is hidden and notifications are permitted, the app shows a system notification (same `tag`).
- Actions: Snooze (default or 5/10/15/30/60 min), Mark done (completes the linked task / habit-for-the-day), Dismiss
  (records dismissal; never completes the task), Silence. `Esc` snoozes.

## Snooze, dismiss, complete, missed
- **Snooze** marks the original `snoozed` (history kept) and creates exactly one child occurrence (`<key>:snoozeN`);
  double taps return the same child; any older pending child is cancelled. Max 12 snoozes, then reschedule/dismiss.
- **Missed recovery** (Notifications → Needs attention, and a banner app-wide): mark complete, snooze, reschedule to a
  chosen time, keep overdue (task stays on the overdue list), or dismiss. Nothing is auto-completed, and stale alarms are
  never fired in a burst after downtime. `missed_policy = hide` turns the review list off.

## Quiet hours
Start/end (may cross midnight; the start day decides), days, and behaviour: **delay** until quiet hours end (original
`scheduled_for` preserved, `fire_at` moved) or **silent** (in-app only, no sound, no push). A reminder breaks through only
if the user explicitly allowed it — per reminder (`bypass_quiet_hours`) or per category.

## Briefings and deduplication
Morning briefing and evening recap are system reminders (category `briefing`) whose text is computed **at send time**
from real data. If the day's first commitment has its own reminder within the next 60 minutes, the briefing gives counts
only and doesn't name it, so the same event never produces two messages back to back. Per-category "at most every N
minutes" caps add frequency control.

## Evidence levels
Scheduled → accepted by the push service → displayed (receipt) → audio played (foreground app only) → guaranteed native
alarm (not possible in a PWA). Details and the real-device checklist: [REAL_DEVICE_TESTING.md](REAL_DEVICE_TESTING.md).

## Subscription lifecycle
Subscriptions are created only from an explicit user action (onboarding step or Settings). The device remembers its
opt-in (a non-sensitive `localStorage` flag); on every app start and on `pushsubscriptionchange` the app re-sends the current
subscription (idempotent upsert that also re-activates it) or re-subscribes if the browser dropped it while permission is
still granted — never prompting. Turning push off on a device removes the server record and the opt-in.

## Web Push setup
1. Generate VAPID keys (`python -c "from py_vapid import Vapid01; ..."` — see DEPLOYMENT.md) and set `VAPID_PUBLIC_KEY`,
   `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`.
2. Serve over HTTPS (required by browsers; `localhost` is exempt).
3. Users enable push from Settings → Notifications (permission is requested only from that button or onboarding step).
4. Subscriptions are stored encrypted; expired ones (404/410) are deactivated automatically; users can remove devices.

## Platform limitations (shown to users in Settings)

| Situation | What happens |
|---|---|
| DayWell open (foreground or background tab) | Alarm dialog appears; sound plays if the browser allows audio |
| DayWell closed, push enabled (Chrome/Edge/Firefox desktop, Android) | System notification; the OS decides the sound; silent/DND wins; may be delayed when asleep |
| iPhone/iPad | Push only for the Home-Screen-installed app (iOS 16.4+); no custom alarm sound |
| Push not configured or permission denied | Reminders still fire in-app and appear in history and the missed list |
| Server or beat down | Reminders are kept; on recovery anything older than 15 min becomes "missed" for review, never a burst |

A PWA **cannot guarantee** continuous ringing while closed or asleep. If guaranteed background alarms become mandatory,
build a native wrapper using platform alarm APIs behind the channel interface above.

## Testing alarms
Settings → Notifications → **Test alarm now / in 30 seconds** creates a real occurrence that goes through the same
dispatcher and shows its true result in the notification history. Automated tests use a controlled clock
(`dispatch_due(now=…)`, `time_machine`) — no real waiting.
