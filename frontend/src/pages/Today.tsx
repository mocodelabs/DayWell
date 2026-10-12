import clsx from "clsx";
import {
  AlarmClock, BookOpen, CalendarDays, Check, Droplets, Dumbbell, Heart, ListTodo, MapPin, Moon, Plus, Sparkles, Sprout, Target, TriangleAlert, Video,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { HabitQuickCheck } from "@/components/HabitQuickCheck";
import { useQuickAdd } from "@/components/layout/QuickAddContext";
import { PlannerDialog } from "@/components/PlannerDialog";
import { TaskItem } from "@/components/TaskItem";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Badge, Card, CardHeader, EmptyState, ErrorState, ProgressBar, ProgressRing, Skeleton } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useAffirmationMutation, useAttendance, useDashboard, useTaskAction, useWellnessMutation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate, formatTime, formatWallTime, minutesLabel, relativeMinutes } from "@/lib/datetime";
import type { Dashboard, SectionKey } from "@/lib/types";

export default function Today() {
  const dash = useDashboard();
  const [planning, setPlanning] = useState(false);
  if (dash.isPending) return <TodaySkeleton />;
  if (dash.error) return <ErrorState error={dash.error} onRetry={() => dash.refetch()} />;
  const d = dash.data;
  const sections: Record<SectionKey, ReactNode> = {
    briefing: null, // always first, rendered as the greeting panel
    progress: <ProgressSection d={d} />,
    agenda: <AgendaSection d={d} onPlan={() => setPlanning(true)} />,
    priorities: <PrioritiesSection d={d} />,
    reminders: <RemindersSection d={d} />,
    habits: <HabitsSection d={d} />,
    affirmation: d.modules.affirmations ? <AffirmationSection d={d} /> : null,
    reading: d.modules.reading ? <ReadingSection d={d} /> : null,
    fitness: d.modules.fitness ? <FitnessSection d={d} /> : null,
    hydration: d.modules.hydration ? <HydrationSection d={d} /> : null,
    evening: d.evening ? <EveningSection d={d} /> : null,
  };
  const order = d.layout.filter((s) => s.visible && s.key !== "briefing" && sections[s.key]);
  return (
    <div className="flex flex-col gap-4">
      {d.layout.find((s) => s.key === "briefing")?.visible !== false && <GreetingPanel d={d} />}
      <div className="grid gap-4 md:grid-cols-2">
        {order.map((s) => (
          <div key={s.key} className={clsx(["agenda", "priorities", "evening"].includes(s.key) && "md:col-span-2")}>{sections[s.key]}</div>
        ))}
      </div>
      <p className="text-center text-xs text-muted">
        Arrange or hide these sections in <Link to="/settings/dashboard" className="underline">Settings → Today page</Link>.
      </p>
      <PlannerDialog open={planning} onOpenChange={setPlanning} date={d.local.date} />
    </div>
  );
}

function TodaySkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-live="polite">
      <span className="sr-only">Loading your day…</span>
      <Skeleton className="h-40 w-full" />
      <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-48" /><Skeleton className="h-48" /></div>
    </div>
  );
}

function GreetingPanel({ d }: { d: Dashboard }) {
  const { prefs } = useSession();
  const { openQuickAdd } = useQuickAdd();
  const detailed = d.briefing.style === "detailed";
  return (
    <section aria-labelledby="greeting" className="relative overflow-hidden rounded-[var(--radius-card)] bg-primary px-5 py-6 text-on-primary shadow-[var(--shadow-card)] sm:px-7">
      <div className="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full bg-amber/30" aria-hidden />
      <p className="text-sm opacity-90">{formatDate(d.local.date, prefs, "long")} · {formatTime(d.local.iso, prefs)}</p>
      <h1 id="greeting" className="mt-1 font-[family-name:var(--font-display)] text-2xl font-semibold sm:text-3xl">
        {d.greeting?.headline ?? "Today"}
      </h1>
      {d.greeting?.message && <p className="mt-1 max-w-2xl opacity-95">{d.greeting.message}</p>}
      <div className="mt-4 flex max-w-2xl flex-col gap-1.5 text-sm">
        <p>{d.briefing.schedule}</p>
        {d.briefing.conflicts && <p className="flex items-center gap-1.5"><TriangleAlert className="h-4 w-4" aria-hidden />{d.briefing.conflicts}</p>}
        {(detailed || !d.briefing.conflicts) && d.briefing.overdue && <p>{d.briefing.overdue}</p>}
        {d.briefing.getting_started && <p className="font-medium">{d.briefing.getting_started}</p>}
        {detailed && d.habits.total > 0 && <p>Habits today: {d.habits.done} of {d.habits.total} done.</p>}
        {detailed && d.affirmation && <p className="italic">“{d.affirmation.text}”</p>}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button onClick={openQuickAdd} className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-control)] bg-surface px-3 text-sm font-medium text-primary-strong hover:bg-sage-soft">
          <Plus className="h-4 w-4" aria-hidden /> Add something
        </button>
      </div>
    </section>
  );
}

function ProgressSection({ d }: { d: Dashboard }) {
  const p = d.progress;
  return (
    <Card aria-labelledby="progress-h">
      <CardHeader id="progress-h" title="Today's progress" icon={Target} />
      <ProgressRing value={p.overall} size={84} label={p.overall === null ? "Nothing planned yet" : "Of what you planned"}
        sublabel={`${p.tasks_done}/${p.tasks_total} tasks · ${p.habits_done}/${p.habits_total} habits`} />
      {p.events_total > 0 && <p className="mt-3 text-sm text-muted">{p.events_total} calendar item{p.events_total === 1 ? "" : "s"} today{p.events_attended ? `, ${p.events_attended} marked attended` : ""}.</p>}
      <p className="mt-2 text-xs text-muted">Progress counts only what was planned for today — rest days don't count against you.</p>
    </Card>
  );
}

function AgendaSection({ d, onPlan }: { d: Dashboard; onPlan: () => void }) {
  const { prefs } = useSession();
  const attendance = useAttendance();
  const now = Date.now();
  return (
    <Card aria-labelledby="agenda-h">
      <CardHeader id="agenda-h" title="Today's agenda" icon={CalendarDays}
        action={<div className="flex gap-2"><Button size="sm" variant="soft" onClick={onPlan}>Plan my day</Button><Link to="/calendar" className="inline-flex h-9 items-center rounded-[var(--radius-control)] px-3 text-sm font-medium text-primary hover:bg-sage-soft">Calendar</Link></div>} />
      {d.agenda.length === 0 ? (
        <EmptyState icon={CalendarDays} title="Nothing on the calendar today">Add an appointment or give a task a time and it will show up here.</EmptyState>
      ) : (
        <ol className="flex flex-col gap-2">
          {d.agenda.map((a) => {
            const isNext = d.next_up && d.next_up.id === a.id && d.next_up.type === a.type && d.next_up.key === a.key;
            const past = !a.all_day && new Date(a.end).getTime() < now;
            return (
              <li key={`${a.type}-${a.id}-${a.key ?? ""}`}
                className={clsx("flex items-start gap-3 rounded-xl border px-3 py-2.5", isNext ? "border-primary bg-sage-soft" : "border-line bg-surface", past && "opacity-70")}>
                <div className="w-16 shrink-0 text-sm">
                  {a.all_day ? <span className="text-muted">All day</span> : <><p className="font-semibold">{formatTime(a.start, prefs)}</p><p className="text-xs text-muted">{formatTime(a.end, prefs)}</p></>}
                </div>
                <div className="min-w-0 flex-1">
                  <p className={clsx("font-medium", a.status === "completed" && "text-muted line-through")}>{a.title}</p>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                    {isNext && <Badge tone="primary">Up next · {relativeMinutes(a.start, now)}</Badge>}
                    <span>{a.type === "event" ? "Appointment" : "Task"}</span>
                    {a.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" aria-hidden />{a.location}</span>}
                    {a.meeting_url && <a href={a.meeting_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline"><Video className="h-3 w-3" aria-hidden />Join</a>}
                    {a.attendance && <span>{a.attendance === "attended" ? "Attended" : a.attendance}</span>}
                  </div>
                </div>
                {a.type === "event" && past && !a.attendance && (
                  <Button size="sm" variant="ghost" icon={<Check className="h-4 w-4" aria-hidden />}
                    onClick={() => attendance.mutate({ id: a.id, key: a.is_recurring ? a.key : undefined, attendance: "attended" })}>Attended</Button>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

function PrioritiesSection({ d }: { d: Dashboard }) {
  const { openTaskForm } = useQuickAdd();
  const others = d.tasks_today.filter((t) => !d.priorities.some((p) => p.id === t.id));
  return (
    <Card aria-labelledby="prio-h">
      <CardHeader id="prio-h" title="Top priorities" icon={ListTodo}
        action={<Link to="/tasks" className="inline-flex min-h-9 min-w-9 items-center justify-center px-1 text-sm font-medium text-primary hover:underline">All tasks</Link>} />
      {d.priorities.length === 0 && others.length === 0 ? (
        <EmptyState icon={ListTodo} title="No tasks for today" action={<Button size="sm" onClick={() => openTaskForm()}>Add a task</Button>}>
          A clear list can be a gift. Add something when you're ready.
        </EmptyState>
      ) : (
        <>
          {d.priorities.length > 0 && <p className="mb-2 text-xs text-muted">Suggested focus — overdue first, then priority and deadlines.</p>}
          <div className="flex flex-col gap-2">{d.priorities.map((t) => <TaskItem key={t.id} task={t} showDate={t.is_overdue} />)}</div>
          {others.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm font-medium text-muted">Also today ({others.length})</summary>
              <div className="mt-2 flex flex-col gap-2">{others.map((t) => <TaskItem key={t.id} task={t} />)}</div>
            </details>
          )}
          {d.overdue.count > d.priorities.filter((p) => p.is_overdue).length && (
            <Link to="/tasks?view=overdue" className="mt-3 inline-block text-sm text-primary hover:underline">See all {d.overdue.count} overdue tasks</Link>
          )}
        </>
      )}
    </Card>
  );
}

function RemindersSection({ d }: { d: Dashboard }) {
  const { prefs } = useSession();
  const r = d.reminders;
  return (
    <Card aria-labelledby="rem-h">
      <CardHeader id="rem-h" title="Reminders" icon={AlarmClock} action={<Link to="/reminders" className="inline-flex min-h-9 min-w-9 items-center justify-center px-1 text-sm font-medium text-primary hover:underline">Manage</Link>} />
      {r.missed > 0 && (
        <Link to="/notifications?tab=missed" className="mb-3 flex items-center gap-2 rounded-xl bg-terracotta-soft px-3 py-2 text-sm hover:underline">
          <TriangleAlert className="h-4 w-4" aria-hidden /> {r.missed} missed reminder{r.missed === 1 ? "" : "s"} to review
        </Link>
      )}
      {r.upcoming.length === 0 ? (
        <p className="text-sm text-muted">No more reminders today.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {r.upcoming.map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate">{u.title}</span>
              <span className="shrink-0 text-muted">{formatTime(u.fire_at, prefs)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function HabitsSection({ d }: { d: Dashboard }) {
  return (
    <Card aria-labelledby="habits-h">
      <CardHeader id="habits-h" title="Habits" icon={Sprout} action={<span className="text-sm text-muted">{d.habits.done}/{d.habits.total}</span>} />
      {d.habits.items.length === 0 ? (
        <EmptyState icon={Sprout} title="No habits scheduled today" action={<Link to="/habits" className="inline-flex min-h-9 min-w-9 items-center justify-center px-1 text-sm font-medium text-primary hover:underline">Set up a habit</Link>} />
      ) : (
        <div className="flex flex-col gap-2">{d.habits.items.map((h) => <HabitQuickCheck key={h.id} habit={h} />)}</div>
      )}
    </Card>
  );
}

function AffirmationSection({ d }: { d: Dashboard }) {
  const mut = useAffirmationMutation();
  const a = d.affirmation;
  if (!a) return null;
  return (
    <Card aria-labelledby="aff-h" className="bg-amber-soft/50">
      <CardHeader id="aff-h" title="Today's affirmation" icon={Heart} />
      <blockquote className="font-[family-name:var(--font-display)] text-lg leading-relaxed">“{a.text}”</blockquote>
      <div className="mt-3 flex flex-wrap gap-2">
        {a.acknowledged ? <Badge tone="primary"><Check className="h-3 w-3" aria-hidden /> Taken to heart</Badge> : (
          <Button size="sm" variant="secondary" onClick={() => mut.mutate(() => api.post(`/affirmations/daily/${a.id}/acknowledge/`))}>I've read this</Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(a.text)}>Copy</Button>
      </div>
    </Card>
  );
}

function ReadingSection({ d }: { d: Dashboard }) {
  const r = d.reading!;
  const book = r.current_book;
  return (
    <Card aria-labelledby="read-h">
      <CardHeader id="read-h" title="Reading" icon={BookOpen} action={<Link to="/growth/reading" className="inline-flex min-h-9 min-w-9 items-center justify-center px-1 text-sm font-medium text-primary hover:underline">Open</Link>} />
      {book ? (
        <>
          <p className="font-medium">{book.title}</p>
          {book.author && <p className="text-sm text-muted">{book.author}</p>}
          {book.total_pages ? <ProgressBar className="mt-2" value={book.current_page / book.total_pages} label={`${book.title}: page ${book.current_page} of ${book.total_pages}`} /> : null}
          <p className="mt-2 text-sm text-muted">
            {r.minutes_today ? `${minutesLabel(r.minutes_today)} read today` : "Not read yet today"}
            {book.daily_goal_minutes ? ` · goal ${book.daily_goal_minutes} min` : ""}
            {r.streak.current > 1 ? ` · ${r.streak.current}-day streak` : ""}
          </p>
          {r.running_session && <Badge tone="amber" className="mt-2">Timer running</Badge>}
        </>
      ) : (
        <p className="text-sm text-muted">No book in progress. <Link to="/growth/reading" className="text-primary underline">Add one</Link>.</p>
      )}
    </Card>
  );
}

function FitnessSection({ d }: { d: Dashboard }) {
  const { prefs } = useSession();
  const plan = d.fitness!.plan;
  return (
    <Card aria-labelledby="fit-h">
      <CardHeader id="fit-h" title="Movement" icon={Dumbbell} action={<Link to="/growth/fitness" className="inline-flex min-h-9 min-w-9 items-center justify-center px-1 text-sm font-medium text-primary hover:underline">Log</Link>} />
      {plan.length === 0 ? <p className="text-sm text-muted">Rest day — recovery is part of the plan.</p> : (
        <ul className="flex flex-col gap-2">
          {plan.map((p) => (
            <li key={p.routine_id} className="flex items-center justify-between gap-2 text-sm">
              <span><span className="font-medium">{p.name}</span>{p.time ? ` · ${formatWallTime(p.time, prefs)}` : ""}{p.location ? ` · ${p.location}` : ""}</span>
              {p.logged_status ? <Badge tone="primary">{p.logged_status === "skipped" ? "Skipped" : "Logged"}</Badge> : <span className="text-muted">{p.duration_minutes} min</span>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function HydrationSection({ d }: { d: Dashboard }) {
  const h = d.hydration!;
  const mut = useWellnessMutation();
  const toast = useToast();
  const unitLabel = h.unit === "glass" ? "glasses" : h.unit;
  const add = () => mut.mutate(() => api.post("/wellness/water/", { amount: h.unit === "ml" ? h.glass_ml : 1 }), { onError: (e) => toast.error("Couldn't log water", (e as Error).message) });
  return (
    <Card aria-labelledby="water-h">
      <CardHeader id="water-h" title="Hydration" icon={Droplets} />
      <p className="text-sm"><span className="text-xl font-semibold">{h.total}</span> / {h.target} {unitLabel}</p>
      <ProgressBar className="mt-2" value={h.progress} label="Water today" />
      <Button className="mt-3" size="sm" variant="soft" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={add} loading={mut.isPending}>
        Add a glass{h.unit === "ml" ? ` (${h.glass_ml} ml)` : ""}
      </Button>
    </Card>
  );
}

function EveningSection({ d }: { d: Dashboard }) {
  const ev = d.evening!;
  const act = useTaskAction();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const moveAll = async () => {
    try {
      for (const t of ev.remaining) await act.mutateAsync({ id: t.id, action: "postpone", body: { preset: "tomorrow" } });
      toast.success("Moved to tomorrow", `${ev.remaining.length} task${ev.remaining.length === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error("Couldn't move everything", (e as Error).message);
    } finally {
      setConfirm(false);
    }
  };
  return (
    <Card aria-labelledby="eve-h" className="bg-sage-soft/60">
      <CardHeader id="eve-h" title={ev.headline} icon={Moon} />
      <p>{ev.message}</p>
      {ev.remaining.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setConfirm(true)}>Move {ev.remaining.length} to tomorrow</Button>
          <Link to="/tasks" className="text-sm text-primary hover:underline">Review them</Link>
        </div>
      )}
      <Link to="/insights" className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"><Sparkles className="h-4 w-4" aria-hidden />See your week</Link>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Move to tomorrow?" confirmLabel="Move them"
        description={`These will be postponed to tomorrow: ${ev.remaining.map((t) => t.title).join(", ")}.`} onConfirm={moveAll} loading={act.isPending} />
    </Card>
  );
}
