# Real-device notification testing

**Status: first physical device tested on 2026-10-26** (Android phone, Chrome, installed app) against the live trial
(https://daywell-three.vercel.app) — background push displayed and confirmed. Not yet tested: locked screen over time,
swiped-away app, reboot, Battery Saver / Do Not Disturb, offline recovery, permission revoke, and any iOS device. Earlier
verification used mocked push services (unit tests), the production Docker stack and desktop Chromium.

## Five different things — never conflate them

| # | Evidence level | Where DayWell records it | What it proves |
|---|---|---|---|
| 1 | **Scheduled** | `ReminderOccurrence.status = scheduled`, `fire_at` | The server will try at that time (durable in PostgreSQL) |
| 2 | **Accepted** by the push service | `NotificationDelivery.result = accepted` (+ HTTP status) | Google/Apple/Mozilla took the message. **Not** that the phone got it |
| 3 | **Displayed** | `result = delivered`, `confirmed_at` — set only by the service worker's signed receipt (push) or the open app (`/alarms/{id}/shown/`) | The browser showed a notification / the app showed the alarm |
| 4 | **Audio played** | `audio_status = played`, `audio_played_at` — only when the app's `play()` promise resolved | Sound started in the foreground app. Push notification sound is chosen by the OS and is never claimed |
| 5 | **Guaranteed native alarm** | — | **Not possible in a PWA.** See "If closed-app ringing is required" |

Diagnostics: Settings → Notifications shows permission, subscription, scheduler health, last push result, audio test.
History: Notifications page shows each occurrence with per-channel results.

## Prerequisites
- Production build served over **HTTPS** with a real certificate (service workers and push require it; the service worker
  is registered only in production builds). The `docker-compose.prod.yml` stack with a public hostname works.
- VAPID keys configured (`/api/v1/push/config/` returns `configured: true`).
- One test account per device; server log access to correlate `request_id`s.

## Android (Chrome)
1. Open the site and tap DayWell's own **Install app** button (sign-in page, phone header, or More menu; Chrome's ⋮ → Install app also works). Launch from the home-screen icon (standalone window).
2. Settings → Notifications → **Enable push on this device** → allow. Expect "Push … Subscribed".
3. **Play test sound** → hear it. **Test alarm now** → alarm dialog + sound in the app; history shows *in-app: shown on your device*.
4. **Test in 30 seconds**, then **switch to another app** → a system notification arrives; history shows *Push: shown on your device* (receipt). Tap **Snooze 10 min** on the notification → app opens and confirms snooze; a repeat arrives 10 min later.
5. **Test in 30 seconds**, **lock the screen** → notification on the lock screen (note delay). Repeat with Battery Saver on and with Do Not Disturb on (expect silence/suppression — DND wins).
6. **Swipe the app away** (closed) → schedule a reminder 2 min ahead → notification arrives with the app closed.
7. Airplane mode for 20 min across a reminder's time, then reconnect → no burst of old alerts; Notifications → Needs attention lists the missed one (if > 15 min late) or it arrives once (if within 15 min).
8. Revoke the notification permission in Android settings → Settings → Notifications shows "Blocked"; next push marks the subscription expired; re-enable works.
9. Clear site data → push stops; reopen the app → re-sync (the app re-subscribes automatically only if permission is still granted).

## iOS / iPadOS (Safari, 16.4+)
1. Safari → Share → **Add to Home Screen**. Push works **only** from the Home-Screen app, not in a Safari tab.
2. Open from the Home Screen → Settings → Notifications → Enable push → allow (iOS asks only after a tap).
3. Steps 3–7 as Android. Expect: notification sound is the iOS default; Focus modes suppress; **no** sound when the app is closed beyond the system notification sound; audio in the foreground app requires a prior tap (autoplay policy).
4. Lock screen, low-power mode, and "Scheduled Summary" may delay or batch notifications — record observed delays.

## Desktop (Chrome/Edge/Firefox/Safari)
Enable push, close the tab (browser still running) → notification appears; close the browser entirely → nothing until it
restarts (expected). macOS Focus / Windows Do Not Disturb suppress notifications.

## Record results
| Device / OS / browser | Installed? | Permission | Test now (in-app + sound) | Background push | Locked screen | App closed | Snooze from notification | Offline recovery | Observed delay |
|---|---|---|---|---|---|---|---|---|---|
| Android 10 phone (Xiaomi/MIUI-style UI), Chrome, 2026-10-26 | Yes (home-screen app) | Allowed | **Pass** — alarm dialog with Snooze/Dismiss/Silence; `audio_status = played` (3×) | **Pass** — 2 test alarms + morning briefing in the notification shade; receipts `delivered` | Not tested | Not tested separately | Not tested | Not tested | Sent → displayed in **1–8 s** (scheduler tick ≤ 60 s after the due time) |
| Windows PC, Chrome, 2026-10-15 | No (browser tab) | Allowed | **Pass** — `audio_status = played` | **Pass** — receipt `delivered` | n/a | Browser running, tab closed: not tested | Not tested | Not tested | ~1 s |

### Notes from the first Android test (2026-10-26)
- **Root cause of the earlier "no notification" report:** the phone had never completed push registration — only the
  Windows PC was subscribed, so the server had nowhere to send. After reopening the installed app (loading the current
  build) and tapping **Enable push on this device**, the device registered as "Chrome on Android" and pushes arrived.
- Changes made because of it: a banner on phones/tablets that aren't subscribed ("Alarms won't ring on this device while
  DayWell is closed"), the settings page now names the subscribed devices, and failed registrations are reported to the
  server log (`push enable failed on device`, with the failing step and browser error — no personal data).
- Server evidence (live database): subscription created 07:55 UTC; deliveries `delivered` with signed receipts at
  +1 s, +8 s and +1 s after sending. Two later pushes were `accepted` without a receipt (notification not yet shown or
  the receipt not sent) — check again on the next test.
- On Android with the app closed the notification uses the system notification sound; DayWell's alarm tone plays only
  in the open app (expected for a PWA — see evidence level 5).
- **Next on this phone:** steps 5–9 above (lock screen, swiped-away app, Battery Saver/DND, airplane mode, permission
  revoke). MIUI-style battery management is known to delay background delivery: test with and without
  *Settings → Apps → DayWell/Chrome → Battery → No restrictions*.

## If closed-app ringing is required (native plan — not started)
A PWA cannot ring continuously while closed, bypass silent mode, or wake a sleeping device reliably. If that becomes a
requirement, build thin native shells that reuse the existing API and add a native delivery channel
(`apps/reminders/channels.py` → `DeliveryChannel`):
- **Android:** schedule with `AlarmManager.setExactAndAllowWhileIdle`/`setAlarmClock` (Android 12+ needs the `SCHEDULE_EXACT_ALARM`/`USE_EXACT_ALARM` permission and Play policy justification), a high-importance notification channel with a custom sound, full-screen intent for alarm-clock use (restricted on Android 14+), and FCM high-priority data messages to (re)sync schedules. Doze and OEM battery managers still apply; test per OEM.
- **iOS:** local notifications via `UNUserNotificationCenter` (max 64 pending; custom sounds ≤ 30 s), APNs to refresh schedules; **Critical Alerts** (bypass silent/Focus) need an Apple entitlement granted only for specific use cases (health/safety). iOS 26 *AlarmKit* (if available on the target OS) provides system alarms with user permission.
- **Server:** keep occurrences authoritative; the native app acknowledges delivery/display with the same receipt model so the evidence levels above stay honest.
Estimate: 3–5 weeks per platform for a production-quality shell (sync, permissions, store review), plus device-lab testing.
