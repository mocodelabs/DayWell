# Real-device notification testing

**Status: NOT yet performed on physical devices.** Push has been verified against mocked push services (unit tests), the
full server pipeline has been verified in the production Docker stack, and the browser flows run in desktop Chromium.
No Android or iOS device was available. Run this checklist before launch and record results in the table at the end.

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
1. Open the site → menu → **Install app**. Launch from the home-screen icon (standalone window).
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
| | | | | | | | | | |

## If closed-app ringing is required (native plan — not started)
A PWA cannot ring continuously while closed, bypass silent mode, or wake a sleeping device reliably. If that becomes a
requirement, build thin native shells that reuse the existing API and add a native delivery channel
(`apps/reminders/channels.py` → `DeliveryChannel`):
- **Android:** schedule with `AlarmManager.setExactAndAllowWhileIdle`/`setAlarmClock` (Android 12+ needs the `SCHEDULE_EXACT_ALARM`/`USE_EXACT_ALARM` permission and Play policy justification), a high-importance notification channel with a custom sound, full-screen intent for alarm-clock use (restricted on Android 14+), and FCM high-priority data messages to (re)sync schedules. Doze and OEM battery managers still apply; test per OEM.
- **iOS:** local notifications via `UNUserNotificationCenter` (max 64 pending; custom sounds ≤ 30 s), APNs to refresh schedules; **Critical Alerts** (bypass silent/Focus) need an Apple entitlement granted only for specific use cases (health/safety). iOS 26 *AlarmKit* (if available on the target OS) provides system alarms with user permission.
- **Server:** keep occurrences authoritative; the native app acknowledges delivery/display with the same receipt model so the evidence levels above stay honest.
Estimate: 3–5 weeks per platform for a production-quality shell (sync, permissions, store review), plus device-lab testing.
