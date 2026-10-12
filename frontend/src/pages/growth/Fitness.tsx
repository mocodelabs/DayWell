import { Dumbbell, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Badge, Card, CardHeader, EmptyState, ErrorState, LoadingList } from "@/components/ui/feedback";
import { DayPicker, Field, FormError, Input, Select, Switch, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useFitnessMutation, useFitnessStats, useRoutines, useWorkouts } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate, formatWallTime, minutesLabel, percent, todayIn, WEEKDAYS_SHORT } from "@/lib/datetime";
import type { Routine, WorkoutSession } from "@/lib/types";

export default function Fitness() {
  const { prefs } = useSession();
  const stats = useFitnessStats();
  const routines = useRoutines();
  const sessions = useWorkouts();
  const mut = useFitnessMutation();
  const [routineForm, setRoutineForm] = useState<Routine | null | undefined>(undefined);
  const [logForm, setLogForm] = useState<{ routine?: Routine } | null>(null);
  const [deleting, setDeleting] = useState<Routine | null>(null);
  const s = stats.data;
  const maxMinutes = Math.max(1, ...(s?.trend.map((t) => t.minutes) ?? [1]));
  return (
    <div className="flex flex-col gap-4">
      {s && (
        <Card>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div><dt className="text-xs text-muted">This week</dt><dd className="text-lg font-semibold">{s.week.sessions} session{s.week.sessions === 1 ? "" : "s"}</dd><dd className="text-xs text-muted">{minutesLabel(s.week.minutes)}</dd></div>
            <div><dt className="text-xs text-muted">Planned vs done (week)</dt><dd className="text-lg font-semibold">{s.week.planned ? `${s.week.planned_completed}/${s.week.planned}` : "—"}</dd><dd className="text-xs text-muted">{percent(s.week.rate)}</dd></div>
            <div><dt className="text-xs text-muted">This month</dt><dd className="text-lg font-semibold">{s.month.sessions}</dd><dd className="text-xs text-muted">{minutesLabel(s.month.minutes)}</dd></div>
            <div><dt className="text-xs text-muted">All time</dt><dd className="text-lg font-semibold">{minutesLabel(s.total_minutes)}</dd></div>
          </dl>
          <div className="mt-4" aria-label="Minutes per week, last 8 weeks" role="img">
            <div className="flex h-20 items-end gap-1.5">
              {s.trend.map((t) => (
                <div key={t.week_start} className="flex flex-1 flex-col items-center gap-1">
                  <div className="w-full rounded-t bg-primary/80" style={{ height: `${(t.minutes / maxMinutes) * 100}%`, minHeight: t.minutes ? 4 : 1 }} title={`${t.week_start}: ${t.minutes} min, ${t.sessions} sessions`} />
                </div>
              ))}
            </div>
            <p className="mt-1 text-xs text-muted">Minutes per week, last 8 weeks. Every ability and pace counts.</p>
          </div>
        </Card>
      )}
      <Card>
        <CardHeader title="Routines" icon={Dumbbell} action={<Button size="sm" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setRoutineForm(null)}>New routine</Button>} />
        {routines.isPending ? <LoadingList rows={2} /> : routines.error ? <ErrorState error={routines.error} /> : routines.data.results.length === 0 ? (
          <EmptyState title="No routine yet">Set your usual workout days and time. Other days are rest days.</EmptyState>
        ) : (
          <ul className="flex flex-col gap-2">
            {routines.data.results.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{r.name} {!r.active && <Badge>Paused</Badge>}</p>
                  <p className="text-xs text-muted">{r.days.map((d) => WEEKDAYS_SHORT[d]).join(", ") || "No days"}{r.time ? ` · ${formatWallTime(r.time, prefs)}` : ""} · {r.duration_minutes} min{r.location ? ` · ${r.location}` : ""}{r.reminder_enabled ? " · reminder on" : ""}</p>
                </div>
                <Button size="sm" variant="soft" onClick={() => setLogForm({ routine: r })}>Log session</Button>
                <Button size="sm" variant="ghost" onClick={() => setRoutineForm(r)}>Edit</Button>
                <Button size="sm" variant="ghost" aria-label={`Delete ${r.name}`} onClick={() => setDeleting(r)}><Trash2 className="h-4 w-4" aria-hidden /></Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader title="Workout log" action={<Button size="sm" variant="secondary" onClick={() => setLogForm({})}>Log a workout</Button>} />
        {sessions.data?.results.length ? (
          <ul className="divide-y divide-line text-sm">
            {sessions.data.results.map((w) => (
              <li key={w.id} className="flex flex-wrap justify-between gap-2 py-2">
                <span>{formatDate(w.date, prefs, "weekday")} · {w.routine_name ?? w.workout_type}</span>
                <span className="text-muted">{w.status === "skipped" ? "Skipped" : `${minutesLabel(w.duration_minutes)}${w.status === "partial" ? " (partial)" : ""}`}{w.distance ? ` · ${w.distance} ${w.distance_unit}` : ""}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">No workouts logged yet.</p>}
      </Card>
      {routineForm !== undefined && <RoutineForm routine={routineForm} onClose={() => setRoutineForm(undefined)} />}
      {logForm && <LogWorkout routine={logForm.routine} onClose={() => setLogForm(null)} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} danger title={`Delete “${deleting?.name}”?`} confirmLabel="Delete"
        description="Logged sessions are kept in your history." onConfirm={() => deleting && mut.mutate(() => api.delete(`/fitness/routines/${deleting.id}/`), { onSuccess: () => setDeleting(null) })} />
    </div>
  );
}

function RoutineForm({ routine, onClose }: { routine: Routine | null; onClose: () => void }) {
  const mut = useFitnessMutation();
  const [v, setV] = useState({
    name: routine?.name ?? "", workout_type: routine?.workout_type ?? "Gym", days: routine?.days ?? [0, 2, 4], time: routine?.time?.slice(0, 5) ?? "18:00",
    duration_minutes: String(routine?.duration_minutes ?? 45), location: routine?.location ?? "", prep_buffer_minutes: String(routine?.prep_buffer_minutes ?? 15),
    reminder_enabled: routine?.reminder_enabled ?? true, active: routine?.active ?? true, notes: routine?.notes ?? "",
  });
  const [error, setError] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!v.name.trim()) return setError("Name the routine.");
    const body = { ...v, time: v.time || null, duration_minutes: Number(v.duration_minutes), prep_buffer_minutes: Number(v.prep_buffer_minutes) };
    mut.mutate(() => (routine ? api.patch(`/fitness/routines/${routine.id}/`, body) : api.post("/fitness/routines/", body)), { onSuccess: onClose, onError: (err) => setError((err as Error).message) });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={routine ? "Edit routine" : "New routine"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="routine-form" loading={mut.isPending}>Save</Button></>}>
      <form id="routine-form" onSubmit={submit} className="flex flex-col gap-3">
        <FormError message={error} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name">{({ id }) => <Input id={id} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder="Strength" autoFocus />}</Field>
          <Field label="Type">{({ id }) => <Input id={id} value={v.workout_type} onChange={(e) => setV({ ...v, workout_type: e.target.value })} />}</Field>
        </div>
        <DayPicker label="Workout days" value={v.days} onChange={(days) => setV({ ...v, days })} />
        <div className="grid grid-cols-3 gap-3">
          <Field label="Time" optional>{({ id }) => <Input id={id} type="time" value={v.time} onChange={(e) => setV({ ...v, time: e.target.value })} />}</Field>
          <Field label="Minutes">{({ id }) => <Input id={id} type="number" min={5} value={v.duration_minutes} onChange={(e) => setV({ ...v, duration_minutes: e.target.value })} />}</Field>
          <Field label="Prep / travel" hint="Remind this much earlier.">{({ id, describedBy }) => <Input id={id} type="number" min={0} aria-describedby={describedBy} value={v.prep_buffer_minutes} onChange={(e) => setV({ ...v, prep_buffer_minutes: e.target.value })} />}</Field>
        </div>
        <Field label="Location" optional>{({ id }) => <Input id={id} value={v.location} onChange={(e) => setV({ ...v, location: e.target.value })} />}</Field>
        <Switch label="Remind me before each workout" checked={v.reminder_enabled} onCheckedChange={(reminder_enabled) => setV({ ...v, reminder_enabled })} />
        <Switch label="Active" description="Pause a routine without losing its history." checked={v.active} onCheckedChange={(active) => setV({ ...v, active })} />
        <Field label="Notes" optional>{({ id }) => <Textarea id={id} rows={2} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />}</Field>
      </form>
    </Dialog>
  );
}

function LogWorkout({ routine, onClose }: { routine?: Routine; onClose: () => void }) {
  const { prefs } = useSession();
  const mut = useFitnessMutation();
  const toast = useToast();
  const [v, setV] = useState({
    date: todayIn(prefs.time_zone), workout_type: routine?.workout_type ?? "Walk", duration_minutes: String(routine?.duration_minutes ?? 30),
    status: "completed" as WorkoutSession["status"], distance: "", effort: "", notes: "", exercises: "",
  });
  const [error, setError] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const exercises = v.exercises.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
      const m = line.match(/^(.*?)(?:\s+(\d+)\s*x\s*(\d+))?(?:\s*@\s*([\d.]+))?$/i);
      return { name: (m?.[1] ?? line).slice(0, 80), sets: m?.[2] ? Number(m[2]) : null, reps: m?.[3] ? Number(m[3]) : null, weight: m?.[4] ? Number(m[4]) : null };
    });
    mut.mutate(() => api.post("/fitness/sessions/", {
      routine: routine?.id ?? null, date: v.date, workout_type: v.workout_type, duration_minutes: v.status === "skipped" ? 0 : Number(v.duration_minutes), status: v.status,
      distance: v.distance || null, effort: v.effort ? Number(v.effort) : null, notes: v.notes, exercises,
    }), { onSuccess: () => { toast.success(v.status === "skipped" ? "Noted — rest is part of training" : "Workout logged"); onClose(); }, onError: (err) => setError((err as Error).message) });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={routine ? `Log: ${routine.name}` : "Log a workout"}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="workout-form" loading={mut.isPending}>Save</Button></>}>
      <form id="workout-form" onSubmit={submit} className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><FormError message={error} /></div>
        <Field label="Date">{({ id }) => <Input id={id} type="date" max={todayIn(prefs.time_zone)} value={v.date} onChange={(e) => setV({ ...v, date: e.target.value })} />}</Field>
        <Field label="How did it go?">{({ id }) => <Select id={id} value={v.status} onChange={(e) => setV({ ...v, status: e.target.value as WorkoutSession["status"] })}><option value="completed">Completed</option><option value="partial">Partly done</option><option value="skipped">Skipped</option></Select>}</Field>
        {!routine && <Field label="Type">{({ id }) => <Input id={id} value={v.workout_type} onChange={(e) => setV({ ...v, workout_type: e.target.value })} />}</Field>}
        {v.status !== "skipped" && <Field label="Minutes">{({ id }) => <Input id={id} type="number" min={1} value={v.duration_minutes} onChange={(e) => setV({ ...v, duration_minutes: e.target.value })} />}</Field>}
        {v.status !== "skipped" && <Field label="Distance (km)" optional>{({ id }) => <Input id={id} type="number" step="0.01" min={0} value={v.distance} onChange={(e) => setV({ ...v, distance: e.target.value })} />}</Field>}
        {v.status !== "skipped" && <Field label="Effort (1–10)" optional>{({ id }) => <Input id={id} type="number" min={1} max={10} value={v.effort} onChange={(e) => setV({ ...v, effort: e.target.value })} />}</Field>}
        {v.status !== "skipped" && <Field label="Exercises" optional className="col-span-2" hint="One per line, e.g. “Squat 3x10 @40”.">{({ id, describedBy }) => <Textarea id={id} rows={3} aria-describedby={describedBy} value={v.exercises} onChange={(e) => setV({ ...v, exercises: e.target.value })} />}</Field>}
        <Field label="Notes" optional className="col-span-2">{({ id }) => <Textarea id={id} rows={2} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />}</Field>
      </form>
    </Dialog>
  );
}
