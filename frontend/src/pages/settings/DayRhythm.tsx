import clsx from "clsx";
import { Card, CardHeader, SegmentedControl } from "@/components/ui/feedback";
import { DayPicker, Field, Input, Switch } from "@/components/ui/form";
import { useSession } from "@/features/auth/session";
import { TONES } from "../Onboarding";
import { useSettingSaver } from "./useSettingSaver";

export default function DayRhythm() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader title="How DayWell talks to you" />
        <div className="flex flex-col gap-2" role="radiogroup" aria-label="Tone">
          {TONES.map((t) => (
            <button key={t.key} type="button" role="radio" aria-checked={prefs.tone === t.key} onClick={() => save({ tone: t.key }, "Tone updated")}
              className={clsx("rounded-xl border p-3 text-left", prefs.tone === t.key ? "border-primary bg-sage-soft" : "border-line hover:bg-sage-soft")}>
              <p className="text-sm font-medium">{t.label}</p><p className="text-sm text-muted">“{t.sample}”</p>
            </button>
          ))}
        </div>
        <Switch label="Personal greeting" description="Turn off for a plain dashboard." checked={prefs.greeting_enabled} onCheckedChange={(v) => save({ greeting_enabled: v })} />
      </Card>
      <Card>
        <CardHeader title="Morning briefing & evening recap" />
        <div className="mb-3">
          <p className="mb-1.5 text-sm font-medium">Briefing length</p>
          <SegmentedControl label="Briefing length" value={prefs.briefing_style} onChange={(v) => save({ briefing_style: v })} options={[{ value: "short", label: "Short" }, { value: "detailed", label: "Detailed" }]} />
        </div>
        <Switch label="Morning briefing notification" description="Sent at your briefing time with your real plan for the day. If the first event has its own reminder soon after, the briefing won't repeat it."
          checked={prefs.morning_notification} onCheckedChange={(v) => save({ morning_notification: v })} />
        <Field label="Briefing time" className="max-w-48">{({ id }) => <Input id={id} type="time" defaultValue={prefs.greeting_time.slice(0, 5)} onBlur={(e) => e.target.value && save({ greeting_time: e.target.value })} />}</Field>
        <Switch label="Evening recap" description="Shown on Today in the evening, and sent as a notification." checked={prefs.evening_summary} onCheckedChange={(v) => save({ evening_summary: v })} />
        <Field label="Recap time" className="max-w-48">{({ id }) => <Input id={id} type="time" defaultValue={prefs.evening_time.slice(0, 5)} onBlur={(e) => e.target.value && save({ evening_time: e.target.value })} />}</Field>
      </Card>
      <Card>
        <CardHeader title="Daily rhythm & planning" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Usual wake-up">{({ id }) => <Input id={id} type="time" defaultValue={prefs.wake_time.slice(0, 5)} onBlur={(e) => e.target.value && save({ wake_time: e.target.value })} />}</Field>
          <Field label="Usual bedtime">{({ id }) => <Input id={id} type="time" defaultValue={prefs.bedtime.slice(0, 5)} onBlur={(e) => e.target.value && save({ bedtime: e.target.value })} />}</Field>
          <Field label="Working hours start">{({ id }) => <Input id={id} type="time" defaultValue={prefs.work_start.slice(0, 5)} onBlur={(e) => e.target.value && save({ work_start: e.target.value })} />}</Field>
          <Field label="Working hours end">{({ id }) => <Input id={id} type="time" defaultValue={prefs.work_end.slice(0, 5)} onBlur={(e) => e.target.value && save({ work_end: e.target.value })} />}</Field>
          <Field label="Buffer between planned items (min)">{({ id }) => <Input id={id} type="number" min={0} max={120} defaultValue={prefs.planning_buffer_minutes} onBlur={(e) => save({ planning_buffer_minutes: Number(e.target.value) })} />}</Field>
          <Field label="Yearly reading goal (books)">{({ id }) => <Input id={id} type="number" min={0} max={500} defaultValue={prefs.reading_yearly_goal} onBlur={(e) => save({ reading_yearly_goal: Number(e.target.value) })} />}</Field>
        </div>
        <div className="mt-3"><DayPicker label="Work days" value={prefs.work_days} onChange={(v) => save({ work_days: v })} /></div>
      </Card>
    </div>
  );
}
