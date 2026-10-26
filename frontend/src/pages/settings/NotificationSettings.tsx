import { CheckCircle2, CircleAlert, Info, Play, Volume2, XCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, ErrorState, LoadingList } from "@/components/ui/feedback";
import { DayPicker, Field, Input, Select, Switch } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useDiagnostics, useNotificationPrefs, useTestAlarm, useUpdateNotificationPref } from "@/hooks/queries";
import { alarmAudio, SOUND_LABELS, SOUNDS } from "@/lib/audio";
import { formatDateTime } from "@/lib/datetime";
import { currentSubscription, deviceLabel, pushSupport, requestNotificationPermission, subscribeToPush, unsubscribeFromPush } from "@/lib/push";
import type { NotificationPreference } from "@/lib/types";
import { useSettingSaver } from "./useSettingSaver";

type Check = "ok" | "warn" | "fail" | "info";

function Row({ status, label, children }: { status: Check; label: string; children?: ReactNode }) {
  const Icon = { ok: CheckCircle2, warn: CircleAlert, fail: XCircle, info: Info }[status];
  const word = { ok: "OK", warn: "Needs attention", fail: "Not available", info: "Info" }[status];
  return (
    <li className="flex items-start gap-3 py-2.5">
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${{ ok: "text-primary", warn: "text-amber", fail: "text-danger", info: "text-muted" }[status]}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label} <span className="sr-only">— {word}</span></p>
        {children && <div className="text-sm text-muted">{children}</div>}
      </div>
    </li>
  );
}

export default function NotificationSettings() {
  return (
    <div className="flex flex-col gap-4">
      <AlarmSetup />
      <SoundSettings />
      <QuietHours />
      <CategorySettings />
      <Limitations />
    </div>
  );
}

/** The alarm setup checklist: shows what will and won't work on this device, with honest tests. */
function AlarmSetup() {
  const { prefs } = useSession();
  const diag = useDiagnostics();
  const test = useTestAlarm();
  const toast = useToast();
  const [support, setSupport] = useState(pushSupport());
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [audio, setAudio] = useState<"unknown" | "played" | "blocked" | "unsupported">(alarmAudio.isUnlocked() ? "played" : "unknown");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void currentSubscription().then((s) => setSubscribed(!!s)).catch(() => setSubscribed(false));
  }, []);
  const refresh = () => {
    setSupport(pushSupport());
    void currentSubscription().then((s) => setSubscribed(!!s));
    void diag.refetch();
  };
  const enablePush = async () => {
    setBusy(true);
    const res = await subscribeToPush(deviceLabel()).catch((e: Error) => ({ ok: false as const, reason: e.message }));
    setBusy(false);
    if (res.ok) toast.success("Notifications enabled on this device");
    else toast.error("Couldn't enable push", res.reason);
    refresh();
  };
  const disablePush = async () => {
    await unsubscribeFromPush();
    toast.info("Push turned off on this device");
    refresh();
  };
  const testSound = async () => {
    const outcome = await alarmAudio.preview(prefs.default_sound, prefs.alarm_volume);
    setAudio(outcome);
    if (outcome === "blocked") toast.error("Sound was blocked", "Your browser refused to play audio. Tap the button again, or check the site's sound settings.");
  };
  const testAlarm = async (delay: number) => {
    try {
      const res = await test.mutateAsync(delay);
      if (delay) toast.info(`Test alarm in ${delay} seconds`, "Keep DayWell open, or switch away to see a push notification.");
      else if (res.outcome === "sent") toast.success("Test sent", "The alarm should appear here now. Check Notifications for the delivery record.");
      else toast.error("Test not delivered", res.occurrence.last_error || res.outcome);
      refresh();
    } catch (e) {
      toast.error("Couldn't run the test", (e as Error).message);
    }
  };
  const d = diag.data;
  return (
    <Card>
      <CardHeader title="Alarm & notification setup" action={<Button size="sm" variant="ghost" onClick={refresh}>Re-check</Button>} />
      {diag.isPending ? <LoadingList rows={4} /> : diag.error ? <ErrorState error={diag.error} onRetry={refresh} /> : d && (
        <>
          <ul className="divide-y divide-line">
            <Row status={d.scheduler.healthy ? "ok" : "fail"} label="Reminder scheduler (server)">
              {d.scheduler.healthy ? `Running${d.scheduler.lag_seconds > 60 ? `, ${d.scheduler.lag_seconds}s behind` : ""}. Reminders are scheduled on the server and survive restarts.`
                : "The server's reminder scheduler isn't reporting. Reminders are saved but may be late until it's running again."}
            </Row>
            <Row status="info" label={`Time zone: ${d.time_zone}`}>Server time {formatDateTime(d.server_time, prefs)} in your zone. {d.quiet_hours_active ? "Quiet hours are active right now." : ""}</Row>
            <Row status={support.permission === "granted" ? "ok" : support.permission === "denied" ? "fail" : support.permission === "unsupported" ? "fail" : "warn"} label="Browser notification permission">
              {support.permission === "granted" ? "Allowed." : support.permission === "denied" ? "Blocked. Allow notifications for this site in your browser settings, then re-check."
                : support.permission === "unsupported" ? "This browser doesn't support notifications." : (
                  <Button size="sm" variant="soft" className="mt-1" onClick={async () => { await requestNotificationPermission(); refresh(); }}>Ask for permission</Button>
                )}
            </Row>
            <Row status={!d.push_configured ? "warn" : subscribed ? "ok" : "warn"} label="Push notifications on this device">
              {!d.push_configured ? "Push isn't configured on this server (VAPID keys missing). In-app alarms work while DayWell is open."
                : !support.push ? (support.ios && !support.standalone ? "On iPhone/iPad, add DayWell to your Home Screen first, then enable push from the installed app." : "This browser doesn't support Web Push.")
                : subscribed ? <span>Subscribed. <button className="underline" onClick={disablePush}>Turn off for this device</button></span>
                : <Button size="sm" variant="soft" className="mt-1" onClick={enablePush} loading={busy}>Enable push on this device</Button>}
              {!subscribed && support.push && d.push_configured && (
                <span className="block font-medium">This device won't ring or show reminders while DayWell is closed until you enable push here.</span>
              )}
              {d.subscriptions.active > 0 && (
                <span className="block">Devices that get alarms while DayWell is closed: {d.subscriptions.devices.map((x) => x.label).join(", ")}.</span>
              )}
              {d.last_push && <span className="block">Last push {formatDateTime(d.last_push.attempted_at, prefs)}: {d.last_push.result === "delivered" ? "shown on a device" : d.last_push.result === "accepted" ? "accepted by the push service (display not yet confirmed)" : `${d.last_push.result}${d.last_push.error ? ` — ${d.last_push.error}` : ""}`}.</span>}
            </Row>
            <Row status={audio === "played" ? "ok" : audio === "blocked" || audio === "unsupported" ? "fail" : "warn"} label="Alarm sound in this browser">
              {audio === "played" ? "Sound can play here." : audio === "blocked" ? "Blocked by the browser — interact with the page and try again." : "Not tested yet."}
              <Button size="sm" variant="soft" className="mt-1 ml-0 block" icon={<Volume2 className="h-4 w-4" aria-hidden />} onClick={testSound}>Play test sound</Button>
            </Row>
          </ul>
          <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
            <Button icon={<Play className="h-4 w-4" aria-hidden />} onClick={() => testAlarm(0)} loading={test.isPending}>Test alarm now</Button>
            <Button variant="secondary" onClick={() => testAlarm(30)} loading={test.isPending}>Test in 30 seconds</Button>
          </div>
          <p className="mt-2 text-xs text-muted">Tests go through the real reminder pipeline and appear in your notification history with their actual delivery result.</p>
        </>
      )}
    </Card>
  );
}

function SoundSettings() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  const [volume, setVolume] = useState(prefs.alarm_volume);
  return (
    <Card>
      <CardHeader title="Alarm sound" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Default sound">
          {({ id }) => (
            <div className="flex gap-2">
              <Select id={id} value={prefs.default_sound} onChange={(e) => save({ default_sound: e.target.value })}>{SOUNDS.map((s) => <option key={s} value={s}>{SOUND_LABELS[s]}</option>)}</Select>
              <Button variant="secondary" aria-label="Preview sound" onClick={() => alarmAudio.preview(prefs.default_sound, volume)}><Play className="h-4 w-4" aria-hidden /></Button>
            </div>
          )}
        </Field>
        <Field label={`In-app volume: ${volume}%`} hint="Applies to in-app alarms. Device volume and silent mode still apply.">
          {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} type="range" min={10} max={100} step={5} value={volume} onChange={(e) => setVolume(Number(e.target.value))} onPointerUp={() => save({ alarm_volume: volume })} onKeyUp={() => save({ alarm_volume: volume })} className="h-6 w-full accent-[var(--color-primary)]" />}
        </Field>
      </div>
    </Card>
  );
}

function QuietHours() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  return (
    <Card>
      <CardHeader title="Quiet hours" />
      <Switch label="Use quiet hours" checked={prefs.quiet_enabled} onCheckedChange={(v) => save({ quiet_enabled: v })} />
      {prefs.quiet_enabled && (
        <div className="mt-2 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="From">{({ id }) => <Input id={id} type="time" defaultValue={prefs.quiet_start.slice(0, 5)} onBlur={(e) => e.target.value && save({ quiet_start: e.target.value })} />}</Field>
            <Field label="Until">{({ id }) => <Input id={id} type="time" defaultValue={prefs.quiet_end.slice(0, 5)} onBlur={(e) => e.target.value && save({ quiet_end: e.target.value })} />}</Field>
          </div>
          <DayPicker label="On nights starting" value={prefs.quiet_days} onChange={(v) => save({ quiet_days: v })} />
          <Field label="During quiet hours, reminders…">
            {({ id }) => (
              <Select id={id} value={prefs.quiet_behavior} onChange={(e) => save({ quiet_behavior: e.target.value as "delay" })}>
                <option value="delay">Wait until quiet hours end</option><option value="silent">Arrive silently in the app (no sound, no push)</option>
              </Select>
            )}
          </Field>
          <p className="text-xs text-muted">Only reminders you've explicitly allowed (per reminder, or per category below) break through quiet hours.</p>
        </div>
      )}
      <div className="mt-3 border-t border-line pt-3">
        <Field label="Missed reminders">
          {({ id }) => (
            <Select id={id} value={prefs.missed_policy} onChange={(e) => save({ missed_policy: e.target.value as "show" })}>
              <option value="show">Show them for review when I come back</option><option value="hide">Don't surface them</option>
            </Select>
          )}
        </Field>
      </div>
    </Card>
  );
}

function CategorySettings() {
  const prefs = useNotificationPrefs();
  const update = useUpdateNotificationPref();
  const toast = useToast();
  const set = (p: NotificationPreference, patch: Partial<NotificationPreference>) =>
    update.mutate({ id: p.id, ...patch }, { onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  return (
    <Card>
      <CardHeader title="By category" />
      {prefs.isPending ? <LoadingList rows={4} /> : prefs.error ? <ErrorState error={prefs.error} /> : (
        <ul className="divide-y divide-line">
          {prefs.data.map((p) => (
            <li key={p.id} className="py-2">
              <Switch label={p.label} checked={p.enabled} onCheckedChange={(enabled) => set(p, { enabled })} />
              {p.enabled && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pb-1 text-sm">
                  <label className="inline-flex min-h-9 items-center gap-1.5"><input type="checkbox" className="h-5 w-5 accent-[var(--color-primary)]" checked={p.channels.includes("in_app")}
                    onChange={(e) => set(p, { channels: e.target.checked ? [...p.channels, "in_app"] : p.channels.filter((c) => c !== "in_app") })} />In-app alarm</label>
                  <label className="inline-flex min-h-9 items-center gap-1.5"><input type="checkbox" className="h-5 w-5 accent-[var(--color-primary)]" checked={p.channels.includes("push")}
                    onChange={(e) => set(p, { channels: e.target.checked ? [...p.channels, "push"] : p.channels.filter((c) => c !== "push") })} />Push</label>
                  <label className="inline-flex min-h-9 items-center gap-1.5"><input type="checkbox" className="h-5 w-5 accent-[var(--color-primary)]" checked={p.bypass_quiet_hours}
                    onChange={(e) => set(p, { bypass_quiet_hours: e.target.checked })} />Allowed in quiet hours</label>
                  <label className="inline-flex items-center gap-1.5">Snooze
                    <select className="rounded-md border border-line bg-surface px-1 py-0.5" value={p.snooze_minutes} onChange={(e) => set(p, { snooze_minutes: Number(e.target.value) })}>
                      {[5, 10, 15, 30, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
                    </select>
                  </label>
                  <label className="inline-flex items-center gap-1.5">At most every
                    <select className="rounded-md border border-line bg-surface px-1 py-0.5" value={p.min_gap_minutes} onChange={(e) => set(p, { min_gap_minutes: Number(e.target.value) })}>
                      {[0, 30, 60, 120, 240].map((m) => <option key={m} value={m}>{m === 0 ? "no limit" : `${m} min`}</option>)}
                    </select>
                  </label>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Limitations() {
  return (
    <Card>
      <CardHeader title="What browsers can and can't do" icon={Info} />
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
        <li>While DayWell is open (even in a background tab), due alarms appear and play your sound — if the browser allows audio.</li>
        <li>When DayWell is closed, reminders arrive as push notifications where supported. A push notification can't play a custom alarm sound or override silent / do-not-disturb modes.</li>
        <li>Phones may delay notifications to save battery, especially when the device is asleep.</li>
        <li>On iPhone and iPad, push works only after adding DayWell to your Home Screen (iOS 16.4+).</li>
        <li>For anything you absolutely must wake up for, also set your device's built-in alarm. DayWell never claims an alarm rang unless your device confirmed it.</li>
      </ul>
    </Card>
  );
}
