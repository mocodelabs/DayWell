import clsx from "clsx";
import { CalendarClock, CheckSquare, Inbox, Link2, Pencil, Play, Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuickAdd } from "@/components/layout/QuickAddContext";
import { TaskItem, STATUS_LABEL } from "@/components/TaskItem";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog, ScopeDialog } from "@/components/ui/Dialog";
import { Badge, EmptyState, ErrorState, LoadingList, PageHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useAddSubtask, useCategories, useDeleteTask, useSubtaskToggle, useTask, useTaskAction, useTasks } from "@/hooks/queries";
import { addDays, formatDate, formatDateTime, formatWallTime, todayIn } from "@/lib/datetime";
import { describeRRule } from "@/lib/recurrence";
import type { Task } from "@/lib/types";

type View = "today" | "upcoming" | "inbox" | "overdue" | "all" | "done" | "matrix" | "admin";
const VIEWS: { key: View; label: string }[] = [
  { key: "today", label: "Today" }, { key: "upcoming", label: "Upcoming" }, { key: "inbox", label: "Inbox" }, { key: "overdue", label: "Overdue" },
  { key: "all", label: "All open" }, { key: "done", label: "Done" }, { key: "matrix", label: "Priority matrix" },
];

export default function Tasks() {
  const { prefs } = useSession();
  const { openTaskForm } = useQuickAdd();
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as View) || "today";
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState("");
  const [category, setCategory] = useState("");
  const [pageSize, setPageSize] = useState(50);
  const [openId, setOpenId] = useState<number | null>(null);
  const today = todayIn(prefs.time_zone);
  const categories = useCategories();

  const query = useMemo(() => {
    const base: Record<string, string | number | boolean | undefined> = { search: search || undefined, priority: priority || undefined, category: category || undefined, page_size: pageSize };
    switch (view) {
      case "today": return { ...base, date_from: today, date_to: today, status: "pending,in_progress,postponed,completed" };
      case "upcoming": return { ...base, date_from: addDays(today, 1), date_to: addDays(today, 30), open: true };
      case "inbox": return { ...base, inbox: true, open: true };
      case "overdue": return { ...base, overdue: true };
      case "done": return { ...base, status: "completed", ordering: "-completed_at" };
      case "admin": return { ...base, admin: true, open: true };
      default: return { ...base, open: true };
    }
  }, [view, search, priority, category, pageSize, today]);
  const tasks = useTasks(query);
  const list = useMemo(() => tasks.data?.results ?? [], [tasks.data]);

  const grouped = useMemo(() => {
    if (view !== "upcoming") return null;
    const m = new Map<string, Task[]>();
    list.forEach((t) => m.set(t.scheduled_date ?? "", [...(m.get(t.scheduled_date ?? "") ?? []), t]));
    return [...m.entries()];
  }, [list, view]);

  return (
    <div>
      <PageHeader title="Tasks" subtitle="Everything you've planned, in one calm list." actions={<Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => openTaskForm()}>New task</Button>} />
      <div className="mb-4 flex gap-1 overflow-x-auto pb-1" role="tablist" aria-label="Task views">
        {[...VIEWS, ...(prefs.modules.admin ? [{ key: "admin" as View, label: "Personal admin" }] : [])].map((v) => (
          <button key={v.key} role="tab" aria-selected={view === v.key} onClick={() => setParams({ view: v.key })}
            className={clsx("shrink-0 rounded-full px-3.5 py-1.5 text-sm font-medium", view === v.key ? "bg-primary text-on-primary" : "bg-surface text-muted hover:text-ink border border-line")}>
            {v.label}
          </button>
        ))}
      </div>
      <div className="mb-4 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <label className="relative">
          <span className="sr-only">Search tasks</span>
          <Search className="pointer-events-none absolute top-3 left-3 h-5 w-5 text-muted" aria-hidden />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tasks" className="pl-10" type="search" />
        </label>
        <Select aria-label="Filter by priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">Any priority</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option>
        </Select>
        <Select aria-label="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </div>

      {view === "admin" && <AdminTemplates />}
      <section role="tabpanel" aria-label={VIEWS.find((v) => v.key === view)?.label}>
        {tasks.isPending ? <LoadingList rows={5} label="Loading tasks" /> : tasks.error ? <ErrorState error={tasks.error} onRetry={() => tasks.refetch()} /> : list.length === 0 ? (
          <EmptyState icon={view === "inbox" ? Inbox : CheckSquare} title={{
            today: "Nothing planned for today", upcoming: "Nothing coming up in the next 30 days", inbox: "Your inbox is clear", overdue: "Nothing overdue — nice and tidy",
            all: "No open tasks", done: "No completed tasks yet", matrix: "No open tasks to sort", admin: "No chores, errands or bills waiting",
          }[view]} action={view !== "done" && view !== "overdue" ? <Button size="sm" onClick={() => openTaskForm({ defaults: view === "today" ? { scheduled_date: today } : {} })}>Add a task</Button> : undefined}>
            {view === "inbox" ? "Tasks without a date land here." : undefined}
          </EmptyState>
        ) : view === "matrix" ? (
          <Matrix tasks={list} onOpen={setOpenId} />
        ) : grouped ? (
          <div className="flex flex-col gap-5">
            {grouped.map(([date, items]) => (
              <div key={date}>
                <h2 className="mb-2 text-sm font-semibold text-muted">{date ? formatDate(date, prefs, "long") : "No date"}</h2>
                <div className="flex flex-col gap-2">{items.map((t) => <TaskItem key={t.id} task={asItem(t)} onOpen={() => setOpenId(t.id)} />)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-2">{list.map((t) => <TaskItem key={t.id} task={asItem(t)} showDate={view !== "today"} onOpen={() => setOpenId(t.id)} />)}</div>
        )}
        {tasks.data?.next && <div className="mt-4 text-center"><Button variant="secondary" onClick={() => setPageSize((n) => Math.min(200, n + 50))} loading={tasks.isFetching}>Show more</Button></div>}
      </section>
      <TaskDetail id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function asItem(t: Task) {
  return { ...t, is_recurring: !!t.series, hasReminder: t.reminders.length > 0 };
}

function Matrix({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: number) => void }) {
  const quads = [
    { key: "do", title: "Urgent & important", hint: "Do these first" },
    { key: "schedule", title: "Important, not urgent", hint: "Give these a time" },
    { key: "delegate", title: "Urgent, less important", hint: "Keep them quick or hand them off" },
    { key: "later", title: "Neither", hint: "Later — or let them go" },
  ] as const;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {quads.map((q) => {
        const items = tasks.filter((t) => t.quadrant === q.key);
        return (
          <section key={q.key} aria-label={q.title} className="rounded-[var(--radius-card)] border border-line bg-surface-2 p-3">
            <h2 className="font-semibold">{q.title} <span className="text-sm font-normal text-muted">({items.length})</span></h2>
            <p className="mb-2 text-xs text-muted">{q.hint}</p>
            <div className="flex flex-col gap-2">{items.map((t) => <TaskItem key={t.id} task={asItem(t)} showDate onOpen={() => onOpen(t.id)} />)}</div>
          </section>
        );
      })}
      <p className="text-xs text-muted md:col-span-2">Urgent = “urgent” priority or a deadline within 48 hours. Important = marked important, or high/urgent priority.</p>
    </div>
  );
}

function TaskDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { prefs } = useSession();
  const task = useTask(id);
  const act = useTaskAction();
  const del = useDeleteTask();
  const toggleSub = useSubtaskToggle();
  const addSub = useAddSubtask();
  const toast = useToast();
  const { openTaskForm } = useQuickAdd();
  const [newSub, setNewSub] = useState("");
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [postponeDate, setPostponeDate] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);
  const t = task.data;

  const run = async (action: "complete" | "reopen" | "start" | "cancel" | "postpone", body?: object, msg?: string) => {
    try {
      await act.mutateAsync({ id: id!, action, body });
      if (msg) toast.success(msg);
      setPostponeOpen(false);
    } catch (e) {
      toast.error("That didn't work", (e as Error).message);
    }
  };
  const remove = async (scope: "this" | "series") => {
    try {
      await del.mutateAsync({ id: id!, scope });
      toast.success(scope === "series" ? "Series deleted (completed ones are kept in your history)" : "Task deleted");
      onClose();
    } catch (e) {
      toast.error("Couldn't delete", (e as Error).message);
    }
  };

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()} title={t?.title ?? "Task"} size="lg"
      description={t ? `${STATUS_LABEL[t.status]}${t.series_rule ? ` · ${describeRRule(t.series_rule)}` : ""}` : undefined}
      footer={t && (
        <>
          <Button variant="ghost" icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={() => (t.series ? setScopeOpen(true) : setConfirmDelete(true))}>Delete</Button>
          <Button variant="secondary" icon={<Pencil className="h-4 w-4" aria-hidden />} onClick={() => { onClose(); openTaskForm({ task: t }); }}>Edit</Button>
          {t.status === "completed" || t.status === "cancelled"
            ? <Button onClick={() => run("reopen", undefined, "Reopened")}>Reopen</Button>
            : <Button onClick={() => run("complete", undefined, "Completed — well done")}>Mark complete</Button>}
        </>
      )}>
      {task.isPending ? <LoadingList rows={3} /> : task.error ? <ErrorState error={task.error} onRetry={() => task.refetch()} /> : t && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <Badge>{t.priority} priority</Badge>
            {t.important && <Badge tone="primary">Important</Badge>}
            {t.is_overdue && <Badge tone="warn">Overdue</Badge>}
            {t.tags.map((tag) => <Badge key={tag}>#{tag}</Badge>)}
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-muted">When</dt><dd>{t.scheduled_date ? `${formatDate(t.scheduled_date, prefs, "long")}${t.scheduled_time ? `, ${formatWallTime(t.scheduled_time, prefs)}` : ""}` : "No date (inbox)"}</dd></div>
            <div><dt className="text-muted">Deadline</dt><dd>{t.deadline ? formatDateTime(t.deadline, prefs) : "—"}</dd></div>
            <div><dt className="text-muted">Estimated</dt><dd>{t.duration_minutes ? `${t.duration_minutes} min` : "—"}</dd></div>
            <div><dt className="text-muted">Reminders</dt><dd>{t.reminders.length ? t.reminders.map((r) => `${r.offset_minutes} min before ${r.anchor}`).join(", ") : "None"}</dd></div>
            {t.postponed_count > 0 && <div><dt className="text-muted">Postponed</dt><dd>{t.postponed_count}×</dd></div>}
            {t.completed_at && <div><dt className="text-muted">Completed</dt><dd>{formatDateTime(t.completed_at, prefs)}</dd></div>}
          </dl>
          {t.description && <p className="whitespace-pre-wrap text-sm">{t.description}</p>}
          {t.link_url && <a href={t.link_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-sm text-primary underline"><Link2 className="h-4 w-4" aria-hidden />{t.link_url}</a>}
          <div>
            <h3 className="mb-2 text-sm font-semibold">Checklist</h3>
            <ul className="flex flex-col gap-1">
              {t.subtasks.map((s) => (
                <li key={s.id}>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" className="h-5 w-5 accent-[var(--color-primary)]" checked={s.done} onChange={(e) => toggleSub.mutate({ taskId: t.id, id: s.id, done: e.target.checked })} />
                    <span className={clsx(s.done && "text-muted line-through")}>{s.title}</span>
                  </label>
                </li>
              ))}
            </ul>
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (newSub.trim()) addSub.mutate({ taskId: t.id, title: newSub.trim() }, { onSuccess: () => setNewSub("") }); }}>
              <Input aria-label="New checklist item" placeholder="Add an item" value={newSub} onChange={(e) => setNewSub(e.target.value)} />
              <Button type="submit" variant="secondary" loading={addSub.isPending}>Add</Button>
            </form>
          </div>
          {t.notes && <div><h3 className="mb-1 text-sm font-semibold">Notes</h3><p className="whitespace-pre-wrap text-sm">{t.notes}</p></div>}
          {t.status !== "completed" && t.status !== "cancelled" && (
            <div className="flex flex-wrap gap-2 border-t border-line pt-3">
              {t.status !== "in_progress" && <Button size="sm" variant="soft" icon={<Play className="h-4 w-4" aria-hidden />} onClick={() => run("start", undefined, "Started")}>Start</Button>}
              <Button size="sm" variant="soft" onClick={() => run("postpone", { preset: "tomorrow" }, "Moved to tomorrow")}>Tomorrow</Button>
              <Button size="sm" variant="soft" onClick={() => run("postpone", { preset: "next_week" }, "Moved to next week")}>Next week</Button>
              <Button size="sm" variant="soft" icon={<CalendarClock className="h-4 w-4" aria-hidden />} onClick={() => setPostponeOpen((v) => !v)}>Pick a date</Button>
              <Button size="sm" variant="ghost" icon={<X className="h-4 w-4" aria-hidden />} onClick={() => run("cancel", undefined, "Cancelled")}>Cancel task</Button>
            </div>
          )}
          {postponeOpen && (
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (postponeDate) void run("postpone", { to_date: postponeDate }, "Rescheduled"); }}>
              <Field label="New date">{({ id: fid }) => <Input id={fid} type="date" min={todayIn(prefs.time_zone)} value={postponeDate} onChange={(e) => setPostponeDate(e.target.value)} />}</Field>
              <Button type="submit" loading={act.isPending}>Move</Button>
            </form>
          )}
        </div>
      )}
      <ConfirmDialog open={confirmDelete} onOpenChange={setConfirmDelete} danger title="Delete this task?" description="This can't be undone." confirmLabel="Delete" onConfirm={() => remove("this")} loading={del.isPending} />
      <ScopeDialog open={scopeOpen} onOpenChange={setScopeOpen} action="delete" onChoose={(scope) => { setScopeOpen(false); void remove(scope); }} />
    </Dialog>
  );
}

/** Personal-admin quick templates: real tasks in the module's categories, with deadlines and reminders where useful. */
function AdminTemplates() {
  const { prefs } = useSession();
  const { openTaskForm } = useQuickAdd();
  const categories = useCategories();
  const cat = (name: string) => categories.data?.find((c) => c.name === name)?.id ?? null;
  const in3 = addDays(todayIn(prefs.time_zone), 3);
  const templates = [
    { label: "Bill due", defaults: { title: "Pay ", category: cat("Bills & renewals"), scheduled_date: in3, priority: "high" as const } },
    { label: "Renewal", defaults: { title: "Renew ", category: cat("Bills & renewals"), scheduled_date: in3 } },
    { label: "Chore", defaults: { title: "", category: cat("Home & chores"), scheduled_date: todayIn(prefs.time_zone) } },
    { label: "Errand", defaults: { title: "", category: cat("Errands") } },
    { label: "Shopping list", defaults: { title: "Shopping", category: cat("Shopping") } },
  ];
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Add personal admin">
      <span className="text-sm text-muted">Add:</span>
      {templates.map((t) => (
        <Button key={t.label} size="sm" variant="soft" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => openTaskForm({ defaults: t.defaults })}>{t.label}</Button>
      ))}
    </div>
  );
}
