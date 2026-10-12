import { Moon } from "lucide-react";
import { useState } from "react";
import { ModuleReminderCard } from "@/components/ModuleReminderCard";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, ErrorState, LoadingList } from "@/components/ui/feedback";
import { Field, FormError, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useSleep, useWellnessMutation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { addDays, formatDate, formatTime, minutesLabel, todayIn, zonedToIso } from "@/lib/datetime";

export default function Sleep() {
  const { prefs } = useSession();
  const s = useSleep();
  const mut = useWellnessMutation();
  const toast = useToast();
  const today = todayIn(prefs.time_zone);
  const [v, setV] = useState({ wake_date: today, bedtime: prefs.bedtime.slice(0, 5), wake: prefs.wake_time.slice(0, 5), quality: "" });
  const [error, setError] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const bedDate = v.bedtime > v.wake ? addDays(v.wake_date, -1) : v.wake_date;
    mut.mutate(() => api.post("/wellness/sleep/", {
      bedtime_at: zonedToIso(bedDate, v.bedtime, prefs.time_zone), wake_at: zonedToIso(v.wake_date, v.wake, prefs.time_zone), quality: v.quality ? Number(v.quality) : null,
    }), { onSuccess: () => toast.success("Sleep logged"), onError: (err) => setError((err as Error).message) });
  };
  if (s.isPending) return <LoadingList />;
  if (s.error) return <ErrorState error={s.error} onRetry={() => s.refetch()} />;
  const sum = s.data.summary.summary;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader title="Last two weeks" icon={Moon} />
        {sum.nights === 0 ? <p className="text-sm text-muted">Log a night to see your rhythm.</p> : (
          <dl className="grid grid-cols-2 gap-3">
            <div><dt className="text-xs text-muted">Nights logged</dt><dd className="text-lg font-semibold">{sum.nights}</dd></div>
            <div><dt className="text-xs text-muted">Average sleep</dt><dd className="text-lg font-semibold">{sum.average_minutes ? minutesLabel(sum.average_minutes) : "—"}</dd></div>
            <div><dt className="text-xs text-muted">Bedtime consistency</dt><dd className="text-lg font-semibold">{sum.bedtime_spread_minutes === null ? "—" : `±${sum.bedtime_spread_minutes} min`}</dd></div>
            <div><dt className="text-xs text-muted">Average rating</dt><dd className="text-lg font-semibold">{sum.average_quality ? `${sum.average_quality.toFixed(1)} / 5` : "—"}</dd></div>
          </dl>
        )}
        <p className="mt-3 text-xs text-muted">Based only on what you log. This is a personal habit view, not a medical sleep analysis.</p>
        <ul className="mt-3 divide-y divide-line text-sm">
          {s.data.logs.results.map((l) => (
            <li key={l.id} className="flex justify-between py-1.5"><span>{formatDate(l.date, prefs, "weekday")}</span><span className="text-muted">{formatTime(l.bedtime_at, prefs)} → {formatTime(l.wake_at, prefs)} · {minutesLabel(l.duration_minutes)}</span></li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Log last night" />
        <form onSubmit={submit} className="grid grid-cols-2 gap-3">
          <div className="col-span-2"><FormError message={error} /></div>
          <Field label="Woke up on" className="col-span-2">{({ id }) => <Input id={id} type="date" max={today} value={v.wake_date} onChange={(e) => setV({ ...v, wake_date: e.target.value })} />}</Field>
          <Field label="Went to bed">{({ id }) => <Input id={id} type="time" value={v.bedtime} onChange={(e) => setV({ ...v, bedtime: e.target.value })} />}</Field>
          <Field label="Woke up">{({ id }) => <Input id={id} type="time" value={v.wake} onChange={(e) => setV({ ...v, wake: e.target.value })} />}</Field>
          <Field label="How rested? (optional)" className="col-span-2">{({ id }) => <Select id={id} value={v.quality} onChange={(e) => setV({ ...v, quality: e.target.value })}><option value="">Skip</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} / 5</option>)}</Select>}</Field>
          <Button type="submit" className="col-span-2" loading={mut.isPending}>Save</Button>
        </form>
      </Card>
      <ModuleReminderCard path="/wellness/sleep-reminder/winddown/" title="Wind-down reminder" description={`Planned bedtime: ${prefs.bedtime.slice(0, 5)}. A nudge 30–60 minutes before helps.`} />
      <ModuleReminderCard path="/wellness/sleep-reminder/wake/" title="Wake-up reminder" description="A notification, not a guaranteed ringing alarm — keep a device alarm for anything critical." />
    </div>
  );
}
