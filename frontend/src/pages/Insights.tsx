import { BarChart3, ChevronLeft, ChevronRight, Info, Plus, Sparkles, Target, Trophy } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Badge, Card, CardHeader, EmptyState, ErrorState, LoadingList, PageHeader, ProgressBar, SegmentedControl } from "@/components/ui/feedback";
import { Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useGoalAction, useGoals, useHabits, useMonthly, useSaveGoal, useSaveWeeklyReview, useWeekly, useYearly } from "@/hooks/queries";
import { addDays, formatDate, minutesLabel, percent, startOfWeek, todayIn } from "@/lib/datetime";
import type { Goal, RangeStats } from "@/lib/types";

export default function Insights() {
  const { prefs } = useSession();
  const [tab, setTab] = useState<"week" | "month" | "year" | "goals">("week");
  return (
    <div>
      <PageHeader title="Insights" subtitle="What you did — from your real records, explained plainly. Missed days are information, never a verdict." />
      <div className="mb-5"><SegmentedControl label="Period" value={tab} onChange={setTab}
        options={[{ value: "week", label: "Week" }, { value: "month", label: "Month" }, { value: "year", label: "Year" }, ...(prefs.modules.goals ? [{ value: "goals" as const, label: "Goals" }] : [])]} /></div>
      {tab === "week" && <WeekView />}
      {tab === "month" && <MonthView />}
      {tab === "year" && <YearView />}
      {tab === "goals" && <Goals />}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return <div><dt className="text-xs text-muted">{label}</dt><dd className="text-xl font-semibold">{value}</dd>{sub && <dd className="text-xs text-muted">{sub}</dd>}</div>;
}

function Summary({ s }: { s: RangeStats }) {
  const { prefs } = useSession();
  const maxDay = Math.max(1, ...s.days.map((d) => Math.max(d.tasks_planned, d.completed_any_day)));
  return (
    <>
      <Card>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Task completion" value={percent(s.tasks.completion_rate)} sub={`${s.tasks.completed} of ${s.tasks.planned - s.tasks.cancelled} planned`} />
          <Stat label="Habit consistency" value={percent(s.habits.consistency)} sub={`${s.habits.done} of ${s.habits.scheduled} scheduled`} />
          <Stat label="Reading" value={minutesLabel(s.reading.minutes)} sub={s.reading.books_completed ? `${s.reading.books_completed} book(s) finished` : `${s.reading.sessions} sessions`} />
          <Stat label="Workouts" value={s.fitness.sessions} sub={minutesLabel(s.fitness.minutes)} />
        </dl>
        <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-4">
          <Stat label="Completed (any day)" value={s.tasks.completed_any_day} />
          <Stat label="Postponed" value={s.tasks.postponed} sub={s.tasks.rescheduled ? `${s.tasks.rescheduled} rescheduled` : undefined} />
          <Stat label="Still open" value={s.tasks.open_now} />
          <Stat label="Events" value={s.events.total} sub={s.events.attended ? `${s.events.attended} attended` : undefined} />
        </dl>
      </Card>
      {s.days.length <= 31 && (
        <Card>
          <CardHeader title="Day by day" icon={BarChart3} />
          <div className="overflow-x-auto">
            <ol className="flex h-36 min-w-[20rem] items-end gap-1" aria-label="Tasks planned and completed per day">
              {s.days.map((d) => (
                <li key={d.date} className="flex flex-1 flex-col items-center gap-1" aria-label={`${formatDate(d.date, prefs, "weekday")}: ${d.completed_any_day} completed, ${d.tasks_planned} planned, ${d.habits_done} habits`}>
                  <div className="flex h-28 w-full items-end justify-center gap-0.5">
                    <div className="w-1/2 rounded-t bg-sage" style={{ height: `${(d.tasks_planned / maxDay) * 100}%` }} />
                    <div className="w-1/2 rounded-t bg-primary" style={{ height: `${(d.completed_any_day / maxDay) * 100}%` }} />
                  </div>
                  {s.days.length <= 7 && <span className="text-[0.65rem] text-muted">{formatDate(d.date, prefs, "weekday").slice(0, 3)}</span>}
                </li>
              ))}
            </ol>
          </div>
          <p className="mt-2 text-xs text-muted"><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-sage align-middle" /> planned <span className="mr-1 ml-3 inline-block h-2.5 w-2.5 rounded-sm bg-primary align-middle" /> completed</p>
          {s.most_productive_days.length > 0 && <p className="mt-2 text-sm">Most productive: {s.most_productive_days.map((d) => `${formatDate(d.date, prefs, "weekday")} (${d.completed})`).join(", ")}</p>}
        </Card>
      )}
      {s.habits.items.length > 0 && (
        <Card>
          <CardHeader title="Habits" />
          <ul className="flex flex-col gap-3">
            {s.habits.items.map((h) => (
              <li key={h.id}>
                <div className="mb-1 flex justify-between text-sm"><span>{h.name}</span><span className="text-muted">{h.weekly_target ? `${h.weeks_met}/${h.weeks} weeks met` : `${h.done}/${h.scheduled - h.skipped}`} · {percent(h.rate)}</span></div>
                <ProgressBar value={h.rate} label={`${h.name} consistency`} />
              </li>
            ))}
          </ul>
        </Card>
      )}
      <details className="rounded-[var(--radius-card)] border border-line bg-surface p-4 text-sm">
        <summary className="flex cursor-pointer items-center gap-2 font-medium"><Info className="h-4 w-4" aria-hidden />How these numbers are calculated</summary>
        <dl className="mt-3 grid gap-2">
          {Object.entries(s.definitions).map(([k, v]) => <div key={k}><dt className="font-medium">{k.replaceAll("_", " ")}</dt><dd className="text-muted">{v}</dd></div>)}
          <div><dt className="font-medium">“—”</dt><dd className="text-muted">Shown instead of a percentage when nothing was planned or scheduled, so you never see a misleading 0%.</dd></div>
        </dl>
      </details>
    </>
  );
}

function WeekView() {
  const { prefs } = useSession();
  const [ws, setWs] = useState(() => startOfWeek(todayIn(prefs.time_zone), prefs.week_start));
  const w = useWeekly(ws);
  const save = useSaveWeeklyReview();
  const toast = useToast();
  const [review, setReview] = useState<Record<string, string> | null>(null);
  const thisWeek = startOfWeek(todayIn(prefs.time_zone), prefs.week_start);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Previous week" onClick={() => setWs(addDays(ws, -7))}><ChevronLeft className="h-5 w-5" aria-hidden /></Button>
        <p className="min-w-56 text-center font-medium">{formatDate(ws, prefs, "weekday")} – {formatDate(addDays(ws, 6), prefs, "weekday")}</p>
        <Button variant="ghost" size="icon" aria-label="Next week" disabled={ws >= thisWeek} onClick={() => setWs(addDays(ws, 7))}><ChevronRight className="h-5 w-5" aria-hidden /></Button>
      </div>
      {w.isPending ? <LoadingList rows={4} /> : w.error ? <ErrorState error={w.error} onRetry={() => w.refetch()} /> : !w.data.has_activity ? (
        <EmptyState icon={BarChart3} title="Nothing recorded this week yet">Once you plan tasks, track habits or log sessions, your week will appear here.</EmptyState>
      ) : (
        <>
          {w.data.accomplishments.length > 0 && (
            <Card className="bg-sage-soft/60">
              <CardHeader title="Wins" icon={Trophy} />
              <ul className="list-disc pl-5 text-sm">{w.data.accomplishments.map((a) => <li key={a}>{a}</li>)}</ul>
            </Card>
          )}
          <Summary s={w.data} />
          {w.data.suggestions.length > 0 && (
            <Card>
              <CardHeader title="Ideas for next week" icon={Sparkles} />
              <ul className="list-disc pl-5 text-sm">{w.data.suggestions.map((s) => <li key={s}>{s}</li>)}</ul>
            </Card>
          )}
        </>
      )}
      {w.data && (
        <Card>
          <CardHeader title="Weekly reflection" action={<Button size="sm" variant="soft" onClick={() => setReview({
            went_well: w.data.review?.went_well ?? "", challenges: w.data.review?.challenges ?? "", next_focus: w.data.review?.next_focus ?? "", wins: w.data.review?.wins ?? "", adjustments: w.data.review?.adjustments ?? "",
          })}>{w.data.review ? "Edit" : "Reflect"}</Button>} />
          {w.data.review ? (
            <dl className="grid gap-2 text-sm">
              {w.data.review.went_well && <div><dt className="font-medium">What went well</dt><dd className="whitespace-pre-wrap text-muted">{w.data.review.went_well}</dd></div>}
              {w.data.review.challenges && <div><dt className="font-medium">What was challenging</dt><dd className="whitespace-pre-wrap text-muted">{w.data.review.challenges}</dd></div>}
              {w.data.review.next_focus && <div><dt className="font-medium">Next week's focus</dt><dd className="whitespace-pre-wrap text-muted">{w.data.review.next_focus}</dd></div>}
            </dl>
          ) : <p className="text-sm text-muted">{w.data.reflection_questions.join(" ")}</p>}
        </Card>
      )}
      {review && (
        <Dialog open onOpenChange={(o) => !o && setReview(null)} title="Weekly reflection" size="lg"
          footer={<><Button variant="secondary" onClick={() => setReview(null)}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate({ week_start: ws, ...review }, { onSuccess: () => { toast.success("Reflection saved"); setReview(null); } })}>Save</Button></>}>
          <div className="flex flex-col gap-3">
            {[["went_well", "What went well this week?"], ["challenges", "What was challenging?"], ["next_focus", "What would you like to focus on next week?"], ["adjustments", "Anything to adjust?"]].map(([k, label]) => (
              <Field key={k} label={label}>{({ id }) => <Textarea id={id} rows={3} value={review[k]} onChange={(e) => setReview({ ...review, [k]: e.target.value })} />}</Field>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  );
}

function MonthView() {
  const { prefs } = useSession();
  const [month, setMonth] = useState(() => todayIn(prefs.time_zone).slice(0, 7));
  const m = useMonthly(month);
  const shift = (n: number) => {
    const [y, mo] = month.split("-").map(Number);
    const d = new Date(Date.UTC(y, mo - 1 + n, 1));
    setMonth(d.toISOString().slice(0, 7));
  };
  const current = todayIn(prefs.time_zone).slice(0, 7);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Previous month" onClick={() => shift(-1)}><ChevronLeft className="h-5 w-5" aria-hidden /></Button>
        <p className="min-w-40 text-center font-medium">{new Date(`${month}-15T12:00:00Z`).toLocaleDateString(prefs.locale, { month: "long", year: "numeric", timeZone: "UTC" })}</p>
        <Button variant="ghost" size="icon" aria-label="Next month" disabled={month >= current} onClick={() => shift(1)}><ChevronRight className="h-5 w-5" aria-hidden /></Button>
      </div>
      {m.isPending ? <LoadingList rows={4} /> : m.error ? <ErrorState error={m.error} /> : !m.data.has_activity ? <EmptyState title="Nothing recorded this month" /> : (
        <>
          {m.data.accomplishments.length > 0 && <Card className="bg-sage-soft/60"><CardHeader title="This month's accomplishments" icon={Trophy} /><ul className="list-disc pl-5 text-sm">{m.data.accomplishments.map((a) => <li key={a}>{a}</li>)}</ul></Card>}
          <Summary s={m.data} />
        </>
      )}
    </div>
  );
}

function YearView() {
  const { prefs } = useSession();
  const [year, setYear] = useState(() => Number(todayIn(prefs.time_zone).slice(0, 4)));
  const y = useYearly(year);
  const max = Math.max(1, ...(y.data?.months.map((m) => m.tasks_completed) ?? [1]));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Previous year" onClick={() => setYear(year - 1)}><ChevronLeft className="h-5 w-5" aria-hidden /></Button>
        <p className="min-w-20 text-center font-medium">{year}</p>
        <Button variant="ghost" size="icon" aria-label="Next year" disabled={year >= Number(todayIn(prefs.time_zone).slice(0, 4))} onClick={() => setYear(year + 1)}><ChevronRight className="h-5 w-5" aria-hidden /></Button>
      </div>
      {y.isPending ? <LoadingList rows={4} label="Calculating your year" /> : y.error ? <ErrorState error={y.error} /> : y.data.months.length === 0 ? <EmptyState title="No data for this year" /> : (
        <>
          <Card>
            <CardHeader title="Month by month" />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[32rem] text-sm">
                <thead><tr className="text-left text-xs text-muted"><th className="py-2 font-medium">Month</th><th className="font-medium">Tasks done</th><th className="font-medium">Completion</th><th className="font-medium">Habits</th><th className="font-medium">Reading</th><th className="font-medium">Books</th><th className="font-medium">Workouts</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {y.data.months.map((m) => (
                    <tr key={m.month}>
                      <th scope="row" className="py-2 text-left font-medium">{new Date(`${m.month}-15T12:00:00Z`).toLocaleDateString(prefs.locale, { month: "short", timeZone: "UTC" })}</th>
                      <td><span className="mr-2 inline-block h-2 rounded bg-primary align-middle" style={{ width: `${(m.tasks_completed / max) * 4}rem` }} aria-hidden />{m.tasks_completed}</td>
                      <td>{percent(m.task_completion_rate)}</td><td>{percent(m.habit_consistency)}</td><td>{minutesLabel(m.reading_minutes)}</td><td>{m.books_completed}</td><td>{m.workouts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {y.data.accomplishments.length > 0 && <Card className="bg-sage-soft/60"><CardHeader title="Your year so far" icon={Trophy} /><ul className="list-disc pl-5 text-sm">{y.data.accomplishments.map((a) => <li key={a}>{a}</li>)}</ul></Card>}
        </>
      )}
    </div>
  );
}

const METRICS: [string, string][] = [["manual", "I'll update it myself"], ["books_completed", "Books completed"], ["reading_minutes", "Reading minutes"], ["workout_sessions", "Workout sessions"],
  ["workout_minutes", "Workout minutes"], ["habit_completions", "Habit completions"], ["tasks_completed", "Tasks completed"]];

function Goals() {
  const { prefs } = useSession();
  const [status, setStatus] = useState("active");
  const goals = useGoals(status);
  const act = useGoalAction();
  const [form, setForm] = useState(false);
  const [checkIn, setCheckIn] = useState<Goal | null>(null);
  const [value, setValue] = useState("");
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between gap-2">
        <SegmentedControl label="Goal status" value={status} onChange={setStatus} options={[{ value: "active", label: "Active" }, { value: "completed", label: "Completed" }, { value: "archived", label: "Archived" }]} />
        <Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setForm(true)}>New goal</Button>
      </div>
      {goals.isPending ? <LoadingList /> : goals.error ? <ErrorState error={goals.error} /> : goals.data.results.length === 0 ? (
        <EmptyState icon={Target} title={`No ${status} goals`} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {goals.data.results.map((g) => (
            <Card key={g.id}>
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold">{g.title}</h3>
                {g.progress.reached && <Badge tone="primary">Reached</Badge>}
              </div>
              <p className="text-xs text-muted">{METRICS.find(([k]) => k === g.metric)?.[1]}{g.due_date ? ` · by ${formatDate(g.due_date, prefs)}` : ""}</p>
              <ProgressBar className="mt-3" value={g.progress.progress} label={`${g.title} progress`} />
              <p className="mt-1 text-sm">{Number(g.progress.value)} / {Number(g.progress.target)} {g.unit} · {percent(g.progress.progress)}
                {g.progress.expected_progress !== null && g.status === "active" && <span className="text-muted"> (time elapsed: {percent(g.progress.expected_progress)})</span>}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {g.metric === "manual" && g.status === "active" && <Button size="sm" variant="soft" onClick={() => { setCheckIn(g); setValue(String(Number(g.current_value))); }}>Update progress</Button>}
                {g.status === "active" && <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: g.id, action: "complete" })}>Mark achieved</Button>}
                {g.status === "active" ? <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: g.id, action: "archive" })}>Archive</Button>
                  : <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: g.id, action: "reactivate" })}>Reactivate</Button>}
              </div>
            </Card>
          ))}
        </div>
      )}
      {form && <GoalForm onClose={() => setForm(false)} />}
      {checkIn && (
        <Dialog open onOpenChange={(o) => !o && setCheckIn(null)} title={`Update “${checkIn.title}”`}
          footer={<Button loading={act.isPending} onClick={() => act.mutate({ id: checkIn.id, action: "check-ins", body: { value } }, { onSuccess: () => setCheckIn(null) })}>Save</Button>}>
          <Field label={`Current value (${checkIn.unit || "units"})`}>{({ id }) => <Input id={id} type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} />}</Field>
        </Dialog>
      )}
    </div>
  );
}

function GoalForm({ onClose }: { onClose: () => void }) {
  const { prefs } = useSession();
  const save = useSaveGoal();
  const habits = useHabits("active");
  const [v, setV] = useState({ title: "", metric: "manual", habit: "", target_value: "", unit: "", start_date: todayIn(prefs.time_zone), due_date: "", description: "" });
  const [error, setError] = useState("");
  const submit = () => save.mutate({ ...v, habit: v.habit ? Number(v.habit) : null, due_date: v.due_date || null } as never, { onSuccess: onClose, onError: (e) => setError((e as Error).message) });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="New goal" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={save.isPending}>Create goal</Button></>}>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><FormError message={error} /></div>
        <Field label="Goal" className="col-span-2">{({ id }) => <Input id={id} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} placeholder="Read 12 books this year" autoFocus />}</Field>
        <Field label="Measured by" className="col-span-2">{({ id }) => <Select id={id} value={v.metric} onChange={(e) => setV({ ...v, metric: e.target.value })}>{METRICS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        {v.metric === "habit_completions" && (
          <Field label="Habit" className="col-span-2">{({ id }) => <Select id={id} value={v.habit} onChange={(e) => setV({ ...v, habit: e.target.value })}><option value="">Choose…</option>{habits.data?.results.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}</Select>}</Field>
        )}
        <Field label="Target">{({ id }) => <Input id={id} type="number" min={0} step="any" value={v.target_value} onChange={(e) => setV({ ...v, target_value: e.target.value })} />}</Field>
        <Field label="Unit" optional>{({ id }) => <Input id={id} value={v.unit} onChange={(e) => setV({ ...v, unit: e.target.value })} />}</Field>
        <Field label="Starting">{({ id }) => <Input id={id} type="date" value={v.start_date} onChange={(e) => setV({ ...v, start_date: e.target.value })} />}</Field>
        <Field label="Due" optional>{({ id }) => <Input id={id} type="date" value={v.due_date} onChange={(e) => setV({ ...v, due_date: e.target.value })} />}</Field>
      </div>
    </Dialog>
  );
}
