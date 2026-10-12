import { zodResolver } from "@hookform/resolvers/zod";
import clsx from "clsx";
import { Archive, ChevronLeft, ChevronRight, Flame, Pause, Pencil, Play, Plus, Sprout, Trash2 } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { HabitQuickCheck } from "@/components/HabitQuickCheck";
import { RecurrenceEditor } from "@/components/RecurrenceEditor";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Badge, Card, EmptyState, ErrorState, LoadingList, PageHeader, SegmentedControl } from "@/components/ui/feedback";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useDeleteHabit, useHabitAction, useHabitHistory, useHabits, useHabitsToday, useSaveHabit } from "@/hooks/queries";
import { applyServerErrors } from "@/lib/api";
import { addDays, formatDate, percent, todayIn, WEEKDAYS_SHORT, weekdayOf } from "@/lib/datetime";
import { describeRRule } from "@/lib/recurrence";
import type { Habit, HabitState } from "@/lib/types";

export default function Habits() {
  const { prefs } = useSession();
  const today = todayIn(prefs.time_zone);
  const [date, setDate] = useState(today);
  const [tab, setTab] = useState<"today" | "manage">("today");
  const [editing, setEditing] = useState<Habit | null | undefined>(undefined);
  const checklist = useHabitsToday(date);
  return (
    <div>
      <PageHeader title="Habits" subtitle="Small, steady routines. Rest days are part of the plan."
        actions={<Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setEditing(null)}>New habit</Button>} />
      <div className="mb-4"><SegmentedControl label="Habit view" value={tab} onChange={setTab} options={[{ value: "today", label: "Checklist" }, { value: "manage", label: "All habits" }]} /></div>
      {tab === "today" ? (
        <>
          <div className="mb-3 flex items-center gap-2">
            <Button variant="ghost" size="icon" aria-label="Previous day" onClick={() => setDate(addDays(date, -1))}><ChevronLeft className="h-5 w-5" aria-hidden /></Button>
            <p className="min-w-44 text-center font-medium">{date === today ? "Today" : formatDate(date, prefs, "long")}</p>
            <Button variant="ghost" size="icon" aria-label="Next day" disabled={date >= today} onClick={() => setDate(addDays(date, 1))}><ChevronRight className="h-5 w-5" aria-hidden /></Button>
            {date !== today && <Button size="sm" variant="soft" onClick={() => setDate(today)}>Back to today</Button>}
          </div>
          {checklist.isPending ? <LoadingList rows={4} /> : checklist.error ? <ErrorState error={checklist.error} onRetry={() => checklist.refetch()} /> :
            checklist.data.items.length === 0 ? (
              <EmptyState icon={Sprout} title="No habits yet" action={<Button size="sm" onClick={() => setEditing(null)}>Create your first habit</Button>}>
                Try something small — a glass of water, a short walk, five minutes of reading.
              </EmptyState>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">{checklist.data.items.map((s) => <HabitCard key={s.habit.id} state={s} onEdit={() => setEditing(s.habit)} />)}</div>
            )}
        </>
      ) : (
        <ManageHabits onEdit={setEditing} />
      )}
      {editing !== undefined && <HabitForm habit={editing} onClose={() => setEditing(undefined)} />}
    </div>
  );
}

function HabitCard({ state, onEdit }: { state: HabitState; onEdit: () => void }) {
  const h = state.habit;
  const act = useHabitAction();
  const c = state.completion;
  const quick = { id: h.id, name: h.name, icon: h.icon, color: h.color, target_type: h.target_type, target_value: h.target_value, unit: h.unit,
    value: c?.value ?? "0", status: c?.status ?? null, times_per_week: h.times_per_week };
  return (
    <Card className={clsx(!state.scheduled && "opacity-80")}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{h.name}</h2>
          <p className="text-xs text-muted">{h.times_per_week ? `${h.times_per_week}× a week, any days` : describeRRule(h.schedule_rule)}{!state.scheduled ? " · not scheduled today" : ""}</p>
        </div>
        <Button variant="ghost" size="icon" aria-label={`Edit ${h.name}`} onClick={onEdit}><Pencil className="h-4 w-4" aria-hidden /></Button>
      </div>
      <HabitQuickCheck habit={quick} date={state.date} />
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        {state.streak && state.streak.current > 0 && <Badge tone="amber"><Flame className="h-3 w-3" aria-hidden />{state.streak.current} {state.streak.unit === "weeks" ? "week" : "day"}{state.streak.current === 1 ? "" : "s"}</Badge>}
        <span>This week: {state.week.weekly_target ? `${state.week.done}/${state.week.weekly_target}` : `${state.week.done}/${state.week.scheduled - state.week.skipped}`}</span>
        {c?.status !== "skipped" && !c && state.scheduled && (
          <button className="min-h-6 px-1 underline" onClick={() => act.mutate({ id: h.id, action: "complete", body: { date: state.date, status: "skipped" } })}>Take a rest day</button>
        )}
        {c?.status === "skipped" && <span>Rest day — that's fine.</span>}
      </div>
    </Card>
  );
}

function ManageHabits({ onEdit }: { onEdit: (h: Habit) => void }) {
  const [status, setStatus] = useState("active");
  const habits = useHabits(status);
  const act = useHabitAction();
  const del = useDeleteHabit();
  const toast = useToast();
  const [confirm, setConfirm] = useState<Habit | null>(null);
  const [history, setHistory] = useState<Habit | null>(null);
  return (
    <>
      <div className="mb-3"><SegmentedControl label="Status" value={status} onChange={setStatus} options={[{ value: "active", label: "Active" }, { value: "paused", label: "Paused" }, { value: "archived", label: "Archived" }]} /></div>
      {habits.isPending ? <LoadingList /> : habits.error ? <ErrorState error={habits.error} /> : habits.data.results.length === 0 ? (
        <EmptyState icon={Sprout} title={`No ${status} habits`} />
      ) : (
        <ul className="flex flex-col gap-2">
          {habits.data.results.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{h.name}</p>
                <p className="text-xs text-muted">{h.times_per_week ? `${h.times_per_week}× a week` : describeRRule(h.schedule_rule)} · {h.target_type === "binary" ? "done / not done" : `${h.target_value} ${h.unit}`}{h.reminder_time ? ` · reminder ${h.reminder_time.slice(0, 5)}` : ""}</p>
              </div>
              <Button size="sm" variant="ghost" onClick={() => setHistory(h)}>History</Button>
              <Button size="sm" variant="ghost" icon={<Pencil className="h-4 w-4" aria-hidden />} onClick={() => onEdit(h)}>Edit</Button>
              {h.status === "active" ? (
                <Button size="sm" variant="ghost" icon={<Pause className="h-4 w-4" aria-hidden />} onClick={() => act.mutate({ id: h.id, action: "pause" }, { onSuccess: () => toast.info("Paused", "History is kept. Resume any time.") })}>Pause</Button>
              ) : (
                <Button size="sm" variant="ghost" icon={<Play className="h-4 w-4" aria-hidden />} onClick={() => act.mutate({ id: h.id, action: "resume" })}>Resume</Button>
              )}
              {h.status !== "archived" && <Button size="sm" variant="ghost" icon={<Archive className="h-4 w-4" aria-hidden />} onClick={() => act.mutate({ id: h.id, action: "archive" })}>Archive</Button>}
              <Button size="sm" variant="ghost" icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={() => setConfirm(h)}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)} danger title={`Delete “${confirm?.name}”?`}
        description="This permanently removes the habit and all of its history. To keep the history, archive or pause it instead." confirmLabel="Delete forever"
        loading={del.isPending} onConfirm={() => confirm && del.mutate(confirm.id, { onSuccess: () => setConfirm(null) })} />
      {history && <HabitHistory habit={history} onClose={() => setHistory(null)} />}
    </>
  );
}

function HabitHistory({ habit, onClose }: { habit: Habit; onClose: () => void }) {
  const { prefs } = useSession();
  const end = todayIn(prefs.time_zone);
  const start = addDays(end, -55);
  const h = useHabitHistory(habit.id, start, end);
  const done = new Map((h.data?.completions ?? []).filter(Boolean).map((c) => [c!.date, c!.status]));
  const scheduled = new Set(h.data?.scheduled_dates ?? []);
  const first = addDays(start, -weekdayOf(start));
  const days = Array.from({ length: 63 }, (_, i) => addDays(first, i)).filter((d) => d <= end);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`${habit.name} — last 8 weeks`}>
      {h.isPending ? <LoadingList rows={2} /> : h.data && (
        <>
          <div className="grid grid-cols-7 gap-1.5 text-center text-xs text-muted" aria-hidden>{WEEKDAYS_SHORT.map((d) => <span key={d}>{d}</span>)}</div>
          <ol className="mt-1 grid grid-cols-7 gap-1.5" aria-label="Daily history">
            {days.map((d) => {
              const s = done.get(d);
              const label = `${formatDate(d, prefs, "weekday")}: ${s === "done" ? "done" : s === "partial" ? "partly done" : s === "skipped" ? "rest day" : scheduled.has(d) ? "not done" : "not scheduled"}`;
              return (
                <li key={d} title={label} aria-label={label}
                  className={clsx("grid aspect-square place-items-center rounded-md text-[0.65rem]", d < start && "invisible",
                    s === "done" ? "bg-primary text-on-primary" : s === "partial" ? "bg-sage text-ink" : s === "skipped" ? "bg-amber-soft text-ink" : scheduled.has(d) ? "border border-line bg-surface" : "bg-surface-2")}>
                  {s === "done" ? "✓" : s === "skipped" ? "–" : Number(d.slice(8))}
                </li>
              );
            })}
          </ol>
          <p className="mt-3 text-sm">Completion: <strong>{percent(h.data.progress.rate)}</strong> ({h.data.progress.done} done of {h.data.progress.scheduled - h.data.progress.skipped} scheduled; rest days excluded).</p>
        </>
      )}
    </Dialog>
  );
}

const habitSchema = z.object({
  name: z.string().trim().min(1, "Give the habit a name.").max(100),
  description: z.string().max(1000),
  category: z.string(),
  target_type: z.enum(["binary", "count", "duration", "numeric"]),
  target_value: z.string(),
  unit: z.string().max(20),
  flexible: z.boolean(),
  times_per_week: z.string(),
  reminder_time: z.string(),
  streaks_enabled: z.boolean(),
}).refine((v) => v.target_type === "binary" || Number(v.target_value) > 0, { path: ["target_value"], message: "Set a target greater than zero." });

function HabitForm({ habit, onClose }: { habit: Habit | null; onClose: () => void }) {
  const save = useSaveHabit();
  const toast = useToast();
  const [rule, setRule] = useState(habit?.schedule_rule ?? "FREQ=DAILY");
  const [error, setError] = useState("");
  const { register, handleSubmit, control, watch, setError: setFieldError, formState: { errors } } = useForm<z.infer<typeof habitSchema>>({
    resolver: zodResolver(habitSchema),
    defaultValues: {
      name: habit?.name ?? "", description: habit?.description ?? "", category: habit?.category ?? "health", target_type: habit?.target_type ?? "binary",
      target_value: habit ? String(Number(habit.target_value)) : "1", unit: habit?.unit ?? "", flexible: !!habit?.times_per_week,
      times_per_week: String(habit?.times_per_week ?? 3), reminder_time: habit?.reminder_time?.slice(0, 5) ?? "", streaks_enabled: habit?.streaks_enabled ?? true,
    },
  });
  const type = watch("target_type");
  const flexible = watch("flexible");
  const onSubmit = handleSubmit(async (v) => {
    setError("");
    try {
      await save.mutateAsync({
        id: habit?.id, name: v.name, description: v.description, category: v.category, target_type: v.target_type,
        target_value: v.target_type === "binary" ? "1" : v.target_value, unit: v.unit, schedule_rule: flexible ? "FREQ=DAILY" : rule || "FREQ=DAILY",
        times_per_week: flexible ? Number(v.times_per_week) : null, reminder_time: v.reminder_time || null, streaks_enabled: v.streaks_enabled,
      });
      toast.success(habit ? "Habit updated" : "Habit created");
      onClose();
    } catch (e) {
      setError(applyServerErrors(e, setFieldError, ["name", "target_value", "unit", "reminder_time"]));
    }
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={habit ? "Edit habit" : "New habit"} size="lg"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="habit-form" loading={save.isPending}>{habit ? "Save" : "Create habit"}</Button></>}>
      <form id="habit-form" onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FormError message={error} />
        <Field label="Name" error={errors.name?.message}>{({ id, invalid }) => <Input id={id} autoFocus aria-invalid={invalid} placeholder="e.g. Stretch, Drink water, Call family" {...register("name")} />}</Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Category">
            {({ id }) => (
              <Select id={id} {...register("category")}>
                {[["health", "Health"], ["fitness", "Fitness"], ["hydration", "Hydration"], ["reading", "Reading"], ["learning", "Learning"], ["mindfulness", "Mindfulness"],
                  ["sleep", "Sleep"], ["social", "Relationships"], ["home", "Home"], ["work", "Work"], ["other", "Other"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Target">
            {({ id }) => (
              <Select id={id} {...register("target_type")}>
                <option value="binary">Done / not done</option><option value="count">A count</option><option value="duration">Minutes</option><option value="numeric">An amount</option>
              </Select>
            )}
          </Field>
          {type !== "binary" && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Goal" error={errors.target_value?.message}>{({ id, invalid }) => <Input id={id} type="number" min={0} step="any" aria-invalid={invalid} {...register("target_value")} />}</Field>
              <Field label="Unit" optional>{({ id }) => <Input id={id} placeholder={type === "duration" ? "min" : "glasses"} {...register("unit")} />}</Field>
            </div>
          )}
        </div>
        <Controller control={control} name="flexible" render={({ field }) => <Checkbox checked={field.value} onChange={field.onChange} label="Flexible: a number of times per week, any days" />} />
        {flexible ? (
          <Field label="Times per week">{({ id }) => <Select id={id} {...register("times_per_week")}>{[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}</option>)}</Select>}</Field>
        ) : (
          <RecurrenceEditor value={rule} onChange={(r) => setRule(r || "FREQ=DAILY")} />
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Reminder" optional hint="Skipped automatically once you've done it that day.">{({ id, describedBy }) => <Input id={id} type="time" aria-describedby={describedBy} {...register("reminder_time")} />}</Field>
          <div className="flex items-end pb-2"><Controller control={control} name="streaks_enabled" render={({ field }) => <Checkbox checked={field.value} onChange={field.onChange} label="Show streaks" />} /></div>
        </div>
        <Field label="Why it matters to you" optional>{({ id }) => <Textarea id={id} rows={2} {...register("description")} />}</Field>
      </form>
    </Dialog>
  );
}
