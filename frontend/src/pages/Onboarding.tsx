import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { ArrowLeft, ArrowRight, Bell, Check } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Field, FormError, Input, Switch } from "@/components/ui/form";
import { useSession } from "@/features/auth/session";
import { keys, useSaveHabit, useUpdatePreferences } from "@/hooks/queries";
import { deviceLabel, pushSupport, requestNotificationPermission, subscribeToPush } from "@/lib/push";
import type { ModuleKey, Preferences, Tone } from "@/lib/types";

const FOCUS: { key: string; label: string; modules: ModuleKey[] }[] = [
  { key: "plan", label: "Planning my day", modules: [] },
  { key: "remember", label: "Remembering appointments", modules: [] },
  { key: "habits", label: "Building healthy habits", modules: [] },
  { key: "exercise", label: "Exercising regularly", modules: ["fitness"] },
  { key: "reading", label: "Reading more", modules: ["reading"] },
  { key: "water", label: "Drinking enough water", modules: ["hydration"] },
  { key: "sleep", label: "Sleeping more consistently", modules: ["sleep"] },
  { key: "reflect", label: "Reflecting and journaling", modules: ["journal"] },
  { key: "calm", label: "Feeling calmer", modules: ["mindfulness", "affirmations"] },
  { key: "goals", label: "Working towards goals", modules: ["goals"] },
];

export const MODULE_INFO: { key: ModuleKey; label: string; description: string }[] = [
  { key: "affirmations", label: "Affirmations", description: "A short, supportive line each day." },
  { key: "reading", label: "Reading", description: "Books, reading sessions and goals." },
  { key: "fitness", label: "Fitness", description: "Workout routines and simple session logs." },
  { key: "hydration", label: "Hydration", description: "Water target and gentle reminders." },
  { key: "sleep", label: "Sleep & bedtime", description: "Wind-down reminders and a simple sleep log." },
  { key: "journal", label: "Journal & gratitude", description: "Private daily reflections." },
  { key: "mindfulness", label: "Mindfulness", description: "Short breathing and reflection timers." },
  { key: "goals", label: "Goals", description: "Track progress towards personal goals." },
  { key: "admin", label: "Personal admin", description: "Chores, errands, bills, renewals and shopping lists — organised task lists with reminders." },
];

export const TONES: { key: Tone; label: string; sample: string }[] = [
  { key: "warm", label: "Warm and friendly", sample: "Good morning! A new day is here. Let's take it one step at a time." },
  { key: "calm", label: "Calm and mindful", sample: "Good morning. Take a breath. The day unfolds one moment at a time." },
  { key: "direct", label: "Direct and concise", sample: "Good morning. Here's your day." },
  { key: "energetic", label: "Energetic", sample: "Good morning! Let's make today count!" },
  { key: "minimal", label: "Minimal", sample: "Good morning." },
];

const STARTERS = [
  { key: "water", label: "Drink water", body: { name: "Drink water", category: "hydration", icon: "glass-water", target_type: "count", target_value: "8", unit: "glasses", schedule_rule: "FREQ=DAILY" } },
  { key: "read", label: "Read 15 minutes", body: { name: "Read", category: "reading", icon: "book-open", target_type: "duration", target_value: "15", unit: "min", schedule_rule: "FREQ=DAILY" } },
  { key: "stretch", label: "Stretch", body: { name: "Stretch", category: "health", icon: "person-standing", target_type: "binary", target_value: "1", unit: "", schedule_rule: "FREQ=DAILY" } },
  { key: "walk", label: "Walk outdoors", body: { name: "Walk outdoors", category: "fitness", icon: "footprints", target_type: "binary", target_value: "1", unit: "", schedule_rule: "FREQ=WEEKLY;BYDAY=MO,WE,FR" } },
  { key: "prepare", label: "Prepare for tomorrow", body: { name: "Prepare for tomorrow", category: "home", icon: "list-checks", target_type: "binary", target_value: "1", unit: "", schedule_rule: "FREQ=DAILY" } },
] as const;

const STEPS = ["Welcome", "Focus", "Modules", "Rhythm", "Tone", "Notifications", "Permission", "First routine", "Ready"];

export default function Onboarding() {
  const { user, prefs } = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const update = useUpdatePreferences();
  const saveHabit = useSaveHabit();
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [focus, setFocus] = useState<string[]>(prefs.focus_areas ?? []);
  const [draft, setDraft] = useState<Partial<Preferences>>({
    modules: { ...prefs.modules }, wake_time: prefs.wake_time.slice(0, 5), bedtime: prefs.bedtime.slice(0, 5), tone: prefs.tone,
    greeting_enabled: prefs.greeting_enabled, morning_notification: prefs.morning_notification, greeting_time: prefs.greeting_time.slice(0, 5),
    evening_summary: prefs.evening_summary, quiet_enabled: true, quiet_start: prefs.bedtime.slice(0, 5), quiet_end: prefs.wake_time.slice(0, 5),
  });
  const [permission, setPermission] = useState(pushSupport().permission);
  const [permissionNote, setPermissionNote] = useState("");
  const [starter, setStarter] = useState<string | null>(null);
  const set = (patch: Partial<Preferences>) => setDraft((d) => ({ ...d, ...patch }));

  const toggleFocus = (f: (typeof FOCUS)[number]) => {
    const on = !focus.includes(f.key);
    setFocus((cur) => (on ? [...cur, f.key] : cur.filter((k) => k !== f.key)));
    if (on && f.modules.length) set({ modules: { ...(draft.modules as Preferences["modules"]), ...Object.fromEntries(f.modules.map((m) => [m, true])) } });
  };

  const finish = async (skipRest = false) => {
    setError("");
    try {
      await update.mutateAsync({ ...(skipRest ? {} : draft), focus_areas: focus, complete_onboarding: true });
      if (!skipRest && starter) {
        const s = STARTERS.find((x) => x.key === starter);
        if (s) await saveHabit.mutateAsync({ ...s.body } as never);
      }
      await qc.invalidateQueries({ queryKey: keys.me });
      navigate("/", { replace: true });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const askPermission = async () => {
    setPermissionNote("");
    const res = await subscribeToPush(deviceLabel()).catch((e: Error) => ({ ok: false as const, reason: e.message }));
    const p = pushSupport().permission;
    setPermission(p);
    if (!res.ok) {
      if (p === "default") await requestNotificationPermission().then(setPermission);
      setPermissionNote(res.reason);
    } else {
      setPermissionNote("You're all set. We'll notify you here when reminders are due.");
    }
  };

  const last = step === STEPS.length - 1;
  return (
    <div className="min-h-dvh px-4 py-8">
      <main className="mx-auto max-w-xl">
        <div className="mb-6 flex items-center justify-between">
          <p className="font-[family-name:var(--font-display)] text-xl font-semibold text-primary-strong">DayWell</p>
          {!last && <Button variant="ghost" size="sm" onClick={() => finish(true)} loading={update.isPending && step === 0}>Skip setup</Button>}
        </div>
        <ol className="mb-6 flex gap-1" aria-label={`Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`}>
          {STEPS.map((s, i) => <li key={s} className={clsx("h-1.5 flex-1 rounded-full", i <= step ? "bg-primary" : "bg-sage")} aria-hidden />)}
        </ol>
        <section className="rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow-card)] sm:p-7 dw-enter" key={step} aria-live="polite">
          <FormError message={error} />
          {step === 0 && (
            <>
              <h1 className="text-2xl font-semibold">Hello{user.display_name ? `, ${user.display_name}` : ""}! Welcome to DayWell.</h1>
              <p className="mt-3 text-muted">DayWell keeps your plans, reminders and healthy routines in one calm place. Each morning it shows you a short, honest briefing of your day — built only from what you've added.</p>
              <p className="mt-3 text-muted">This takes about two minutes. You can skip anything and change it later in Settings.</p>
            </>
          )}
          {step === 1 && (
            <>
              <h1 className="text-xl font-semibold">What would you like help with?</h1>
              <p className="mt-1 text-sm text-muted">Pick as many as you like.</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {FOCUS.map((f) => (
                  <button key={f.key} type="button" aria-pressed={focus.includes(f.key)} onClick={() => toggleFocus(f)}
                    className={clsx("flex items-center gap-2 rounded-xl border p-3 text-left text-sm", focus.includes(f.key) ? "border-primary bg-sage-soft font-medium" : "border-line hover:bg-sage-soft")}>
                    <span className={clsx("grid h-5 w-5 place-items-center rounded-md border", focus.includes(f.key) ? "border-primary bg-primary text-on-primary" : "border-line")} aria-hidden>
                      {focus.includes(f.key) && <Check className="h-3.5 w-3.5" />}
                    </span>
                    {f.label}
                  </button>
                ))}
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h1 className="text-xl font-semibold">Choose your modules</h1>
              <p className="mt-1 text-sm text-muted">Tasks, calendar, reminders and habits are always on. These are optional — turned-off modules stay out of your way and never send reminders.</p>
              <div className="mt-3 divide-y divide-line">
                {MODULE_INFO.map((m) => (
                  <Switch key={m.key} label={m.label} description={m.description} checked={!!draft.modules?.[m.key]}
                    onCheckedChange={(v) => set({ modules: { ...(draft.modules as Preferences["modules"]), [m.key]: v } })} />
                ))}
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <h1 className="text-xl font-semibold">Your daily rhythm</h1>
              <p className="mt-1 text-sm text-muted">Used for your briefing time, planning suggestions and quiet hours. Your time zone is {prefs.time_zone}.</p>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <Field label="Usual wake-up">{({ id }) => <Input id={id} type="time" value={draft.wake_time} onChange={(e) => set({ wake_time: e.target.value, quiet_end: e.target.value })} />}</Field>
                <Field label="Usual bedtime">{({ id }) => <Input id={id} type="time" value={draft.bedtime} onChange={(e) => set({ bedtime: e.target.value, quiet_start: e.target.value })} />}</Field>
              </div>
            </>
          )}
          {step === 4 && (
            <>
              <h1 className="text-xl font-semibold">How should DayWell talk to you?</h1>
              <div className="mt-4 flex flex-col gap-2" role="radiogroup" aria-label="Tone">
                {TONES.map((t) => (
                  <button key={t.key} type="button" role="radio" aria-checked={draft.tone === t.key} onClick={() => set({ tone: t.key })}
                    className={clsx("rounded-xl border p-3 text-left", draft.tone === t.key ? "border-primary bg-sage-soft" : "border-line hover:bg-sage-soft")}>
                    <p className="text-sm font-medium">{t.label}</p>
                    <p className="text-sm text-muted">“{t.sample}”</p>
                  </button>
                ))}
              </div>
              <div className="mt-3"><Switch label="Show a personal greeting" checked={!!draft.greeting_enabled} onCheckedChange={(v) => set({ greeting_enabled: v })} /></div>
            </>
          )}
          {step === 5 && (
            <>
              <h1 className="text-xl font-semibold">Notifications, your way</h1>
              <div className="mt-3 divide-y divide-line">
                <Switch label="Morning briefing notification" description="A short summary of your day at your chosen time." checked={!!draft.morning_notification} onCheckedChange={(v) => set({ morning_notification: v })} />
                {draft.morning_notification && (
                  <Field label="Briefing time" className="py-2">{({ id }) => <Input id={id} type="time" value={draft.greeting_time} onChange={(e) => set({ greeting_time: e.target.value })} className="max-w-40" />}</Field>
                )}
                <Switch label="Evening recap" description="A kind look back at the day, with options for anything left." checked={!!draft.evening_summary} onCheckedChange={(v) => set({ evening_summary: v })} />
                <Switch label={`Quiet hours (${draft.quiet_start}–${draft.quiet_end})`} description="Reminders wait until morning unless you mark them as allowed to break through." checked={!!draft.quiet_enabled} onCheckedChange={(v) => set({ quiet_enabled: v })} />
              </div>
            </>
          )}
          {step === 6 && (
            <>
              <h1 className="flex items-center gap-2 text-xl font-semibold"><Bell className="h-5 w-5 text-primary" aria-hidden /> Allow notifications?</h1>
              <p className="mt-2 text-sm text-muted">So reminders can reach you when DayWell isn't on screen. While DayWell is open, alarms appear and play a sound in the app either way.</p>
              <p className="mt-2 text-sm text-muted">Honest note: browsers can't guarantee a ringing alarm when the app is closed or your device is asleep, and your phone's silent mode always wins. You can test this any time in Settings → Notifications.</p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button onClick={askPermission} disabled={permission === "granted" && permissionNote.startsWith("You're")}>Allow notifications</Button>
                <span className="text-sm text-muted">Status: {permission === "unsupported" ? "not supported in this browser" : permission}</span>
              </div>
              {permissionNote && <p role="status" className="mt-3 text-sm">{permissionNote}</p>}
            </>
          )}
          {step === 7 && (
            <>
              <h1 className="text-xl font-semibold">Start a first routine?</h1>
              <p className="mt-1 text-sm text-muted">Optional. Small is good — you can add more later.</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {STARTERS.map((s) => (
                  <button key={s.key} type="button" aria-pressed={starter === s.key} onClick={() => setStarter(starter === s.key ? null : s.key)}
                    className={clsx("rounded-xl border p-3 text-left text-sm", starter === s.key ? "border-primary bg-sage-soft font-medium" : "border-line hover:bg-sage-soft")}>
                    {s.label}
                  </button>
                ))}
              </div>
            </>
          )}
          {step === 8 && (
            <>
              <h1 className="text-2xl font-semibold">You're ready.</h1>
              <p className="mt-2 text-muted">Your Today page will show your plan, reminders and routines. Add your first task with the + button — or just say something like “Dentist on Friday at 3 pm”.</p>
            </>
          )}
          <div className="mt-6 flex items-center justify-between gap-2">
            {step > 0 ? <Button variant="ghost" icon={<ArrowLeft className="h-4 w-4" aria-hidden />} onClick={() => setStep((s) => s - 1)}>Back</Button> : <span />}
            {last ? (
              <Button size="lg" onClick={() => finish(false)} loading={update.isPending || saveHabit.isPending}>Show my day</Button>
            ) : (
              <Button onClick={() => setStep((s) => s + 1)} icon={<ArrowRight className="h-4 w-4" aria-hidden />}>{step === 0 ? "Let's begin" : "Continue"}</Button>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
