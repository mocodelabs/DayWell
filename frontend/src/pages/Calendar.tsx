import type { DateSelectArg, DatesSetArg, EventClickArg, EventDropArg, EventInput } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin, { type EventResizeDoneArg } from "@fullcalendar/interaction";
import luxonPlugin from "@fullcalendar/luxon3";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { ChevronLeft, ChevronRight, Download, MapPin, Pencil, Plus, Search, Trash2, TriangleAlert, Upload, Video } from "lucide-react";
import { DateTime } from "luxon";
import { useCallback, useMemo, useRef, useState } from "react";
import { EventForm } from "@/components/EventForm";
import { useQuickAdd } from "@/components/layout/QuickAddContext";
import { Button } from "@/components/ui/Button";
import { Dialog, ScopeDialog } from "@/components/ui/Dialog";
import { Badge, ErrorState, PageHeader, SegmentedControl } from "@/components/ui/feedback";
import { Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import {
  useAttendance, useCancelOccurrence, useChangeOccurrence, useDeleteEvent, useEvent, useOccurrences, useSaveEvent, useTasks, useUpdateTask,
} from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDateTime, formatTime } from "@/lib/datetime";
import { describeRRule } from "@/lib/recurrence";
import type { Occurrence, Task } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  forest: "#466B52", sage: "#7f9e7a", terracotta: "#C77B61", amber: "#b98a3e", sky: "#4f7ea8", plum: "#8a5a83", slate: "#5b6670", rose: "#b5606f",
};

export default function Calendar() {
  const { prefs } = useSession();
  const toast = useToast();
  const { openTaskForm } = useQuickAdd();
  const calRef = useRef<FullCalendar>(null);
  const [range, setRange] = useState<{ start: string; end: string; startDate: string; endDate: string } | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Occurrence | null>(null);
  const [form, setForm] = useState<{ eventId?: number; occurrence?: Occurrence | null; defaults?: { start_date: string; start_time?: string; end_time?: string; all_day?: boolean } } | null>(null);
  const [pendingMove, setPendingMove] = useState<{ info: EventDropArg | EventResizeDoneArg; occ: Occurrence } | null>(null);
  const occ = useOccurrences(range?.start ?? "", range?.end ?? "", q || undefined);
  const tasks = useTasks({ date_from: range?.startDate, date_to: range?.endDate, page_size: 200, status: "pending,in_progress,postponed,completed" }, !!range);
  const saveEvent = useSaveEvent();
  const changeOcc = useChangeOccurrence();
  const updateTask = useUpdateTask();
  const editEvent = useEvent(form?.eventId ?? null);

  const events: EventInput[] = useMemo(() => {
    const out: EventInput[] = (occ.data?.results ?? []).map((o) => ({
      id: `e:${o.event_id}:${o.key}`, title: o.title, start: o.all_day ? o.local_start.slice(0, 10) : o.start,
      end: o.all_day ? DateTime.fromISO(o.local_end.slice(0, 10)).plus({ days: 1 }).toISODate()! : o.end, allDay: o.all_day,
      backgroundColor: o.color ? CATEGORY_COLORS[o.color] : undefined, borderColor: o.color ? CATEGORY_COLORS[o.color] : undefined,
      classNames: [o.attendance ? "dw-event-attended" : "", o.status === "tentative" ? "opacity-70" : ""],
      extendedProps: { kind: "event", occ: o },
    }));
    if (!q) {
      for (const t of tasks.data?.results ?? []) {
        if (!t.scheduled_date || t.status === "cancelled") continue;
        out.push({
          id: `t:${t.id}`, title: `${t.status === "completed" ? "✓ " : "☐ "}${t.title}`,
          start: t.scheduled_at ?? t.scheduled_date, end: t.scheduled_at ? new Date(new Date(t.scheduled_at).getTime() + (t.duration_minutes ?? 30) * 60000).toISOString() : undefined,
          allDay: !t.scheduled_at, classNames: ["dw-event-task"], extendedProps: { kind: "task", task: t },
        });
      }
    }
    return out;
  }, [occ.data, tasks.data, q]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [title, setTitle] = useState("");
  const [viewType, setViewType] = useState<string>(window.innerWidth < 640 ? "timeGridDay" : "timeGridWeek");
  const unit = viewType === "dayGridMonth" ? "month" : viewType === "timeGridDay" ? "day" : "week";

  /** Scroll our own scroll region (outside FullCalendar's grid) so the working day starts at the top. */
  const scrollToWorkStart = useCallback(() => {
    const box = scrollRef.current;
    const slot = box?.querySelector<HTMLElement>(`.fc-timegrid-slot-label[data-time="${prefs.work_start.slice(0, 5)}:00"]`);
    const header = box?.querySelector<HTMLElement>(".fc-col-header");
    if (box && slot) box.scrollTop = slot.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - (header?.offsetHeight ?? 0);
    // FullCalendar's icons are decorative (our toolbar labels the buttons); keep them out of the accessibility tree.
    box?.querySelectorAll(".fc-icon").forEach((el) => el.setAttribute("aria-hidden", "true"));
  }, [prefs.work_start]);

  const onDatesSet = (arg: DatesSetArg) => {
    setTitle(arg.view.title);
    setViewType(arg.view.type);
    const startDate = DateTime.fromJSDate(arg.start, { zone: prefs.time_zone }).toISODate()!;
    const endDate = DateTime.fromJSDate(arg.end, { zone: prefs.time_zone }).minus({ days: 1 }).toISODate()!;
    setRange({ start: arg.start.toISOString(), end: arg.end.toISOString(), startDate, endDate });
  };

  const onSelect = (arg: DateSelectArg) => {
    const s = DateTime.fromJSDate(arg.start, { zone: prefs.time_zone });
    const e = DateTime.fromJSDate(arg.end, { zone: prefs.time_zone });
    setForm({ defaults: arg.allDay ? { start_date: s.toISODate()!, all_day: true } : { start_date: s.toISODate()!, start_time: s.toFormat("HH:mm"), end_time: e.toFormat("HH:mm") } });
    calRef.current?.getApi().unselect();
  };

  const onClick = (arg: EventClickArg) => {
    const p = arg.event.extendedProps as { kind: string; occ?: Occurrence; task?: Task };
    if (p.kind === "event" && p.occ) setSelected(p.occ);
    if (p.kind === "task" && p.task) openTaskForm({ task: p.task });
  };

  const moveTask = async (info: EventDropArg, task: Task) => {
    const s = DateTime.fromJSDate(info.event.start!, { zone: prefs.time_zone });
    try {
      await updateTask.mutateAsync({ id: task.id, scope: "this", scheduled_date: s.toISODate()!, scheduled_time: info.event.allDay ? null : s.toFormat("HH:mm") });
      toast.success("Task moved", task.title);
    } catch (e) {
      info.revert();
      toast.error("Couldn't move the task", (e as Error).message);
    }
  };

  const applyMove = async (info: EventDropArg | EventResizeDoneArg, o: Occurrence, scope: "this" | "series") => {
    const zone = o.time_zone;
    const s = DateTime.fromJSDate(info.event.start!, { zone });
    const e = info.event.end ? DateTime.fromJSDate(info.event.end, { zone }) : s.plus({ hours: 1 });
    try {
      if (o.is_recurring && scope === "this") {
        await changeOcc.mutateAsync({ id: o.event_id, key: o.key, start_date: s.toISODate(), start_time: o.all_day ? null : s.toFormat("HH:mm"),
          end_date: (o.all_day ? e.minus({ days: 1 }) : e).toISODate(), end_time: o.all_day ? null : e.toFormat("HH:mm") });
      } else {
        const ev = await api.get<{ start_date: string; start_time: string | null; end_date: string; end_time: string | null }>(`/calendar/events/${o.event_id}/`);
        // Shift the series by the same wall-clock delta the occurrence moved.
        const oldStart = DateTime.fromISO(o.local_start, { zone });
        const delta = s.diff(oldStart);
        const span = e.diff(s);
        const base = DateTime.fromISO(`${ev.start_date}T${(ev.start_time ?? "00:00").slice(0, 5)}`, { zone }).plus(delta);
        const end = base.plus(span);
        await saveEvent.mutateAsync({ id: o.event_id, start_date: base.toISODate()!, start_time: o.all_day ? null : base.toFormat("HH:mm"),
          end_date: (o.all_day ? end.minus({ days: 1 }) : end).toISODate()!, end_time: o.all_day ? null : end.toFormat("HH:mm") });
      }
      toast.success("Rescheduled", o.title);
    } catch (err) {
      info.revert();
      toast.error("Couldn't reschedule", (err as Error).message);
    }
  };

  const onDrop = (info: EventDropArg | EventResizeDoneArg) => {
    const p = info.event.extendedProps as { kind: string; occ?: Occurrence; task?: Task };
    if (p.kind === "task" && p.task) return void moveTask(info as EventDropArg, p.task);
    if (!p.occ) return info.revert();
    if (p.occ.is_recurring) setPendingMove({ info, occ: p.occ });
    else void applyMove(info, p.occ, "series");
  };

  const exportIcs = () => window.open("/api/v1/calendar/events/export/", "_blank");
  const importIcs = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await api.upload<{ created: number; skipped: number; errors: string[] }>("/calendar/events/import/", fd);
      toast.success(`Imported ${res.created} event${res.created === 1 ? "" : "s"}`, res.skipped ? `${res.skipped} already existed.` : res.errors[0]);
      occ.refetch();
    } catch (e) {
      toast.error("Import failed", (e as Error).message);
    }
  };

  const conflicts = occ.data?.conflicts ?? [];
  return (
    <div>
      <PageHeader title="Calendar" subtitle={`Times shown in ${prefs.time_zone}. Appointments are solid; tasks are amber.`}
        actions={
          <>
            <Button variant="secondary" size="sm" icon={<Download className="h-4 w-4" aria-hidden />} onClick={exportIcs}>Export</Button>
            <label className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm font-medium hover:bg-sage-soft">
              <Upload className="h-4 w-4" aria-hidden /> Import .ics
              <input type="file" accept=".ics,text/calendar" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void importIcs(f); e.target.value = ""; }} />
            </label>
            <Button size="sm" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setForm({ defaults: { start_date: DateTime.now().setZone(prefs.time_zone).toISODate()! } })}>New event</Button>
          </>
        } />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative w-full sm:w-72">
          <span className="sr-only">Search events</span>
          <Search className="pointer-events-none absolute top-3 left-3 h-5 w-5 text-muted" aria-hidden />
          <Input type="search" placeholder="Search events" value={q} onChange={(e) => setQ(e.target.value)} className="pl-10" />
        </label>
        {occ.isFetching && <span className="text-sm text-muted" role="status">Updating…</span>}
      </div>
      {conflicts.length > 0 && (
        <div role="status" className="mb-3 flex items-start gap-2 rounded-xl bg-terracotta-soft px-3 py-2 text-sm">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{conflicts.length} overlap{conflicts.length === 1 ? "" : "s"} in this view — e.g. “{conflicts[0].a.title}” and “{conflicts[0].b.title}” at {formatTime(conflicts[0].b.start, prefs)}.</span>
        </div>
      )}
      {occ.error && <ErrorState error={occ.error} onRetry={() => occ.refetch()} compact />}
      <div className="rounded-[var(--radius-card)] border border-line bg-surface p-2 shadow-[var(--shadow-card)] sm:p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button variant="secondary" size="icon" aria-label={`Previous ${unit}`} onClick={() => calRef.current?.getApi().prev()}><ChevronLeft className="h-5 w-5" aria-hidden /></Button>
            <Button variant="secondary" size="icon" aria-label={`Next ${unit}`} onClick={() => calRef.current?.getApi().next()}><ChevronRight className="h-5 w-5" aria-hidden /></Button>
            <Button variant="secondary" size="sm" onClick={() => calRef.current?.getApi().today()}>Today</Button>
          </div>
          <h2 className="text-base font-semibold" aria-live="polite">{title}</h2>
          <SegmentedControl label="Calendar view" value={viewType} onChange={(v) => calRef.current?.getApi().changeView(v)}
            options={[{ value: "dayGridMonth", label: "Month" }, { value: "timeGridWeek", label: "Week" }, { value: "timeGridDay", label: "Day" }]} />
        </div>
        {/* Our own scroll region: outside FullCalendar's grid, so it can be focusable and named without breaking grid roles. */}
        <div ref={scrollRef} role="region" aria-label={`Calendar, ${title}`} tabIndex={0} className="max-h-[70vh] overflow-y-auto rounded-lg">
          <FullCalendar
            ref={calRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin, luxonPlugin]}
            initialView={viewType}
            headerToolbar={false}
            timeZone={prefs.time_zone}
            firstDay={(prefs.week_start + 1) % 7}
            eventTimeFormat={{ hour: "numeric", minute: "2-digit", hour12: prefs.time_format === "12h" }}
            slotLabelFormat={{ hour: "numeric", minute: "2-digit", hour12: prefs.time_format === "12h" }}
            nowIndicator
            selectable
            selectMirror
            editable
            eventResizableFromStart={false}
            dayMaxEvents
            height="auto"
            stickyHeaderDates
            events={events}
            datesSet={onDatesSet}
            select={onSelect}
            eventClick={onClick}
            eventDrop={onDrop}
            eventResize={onDrop}
            viewDidMount={() => window.setTimeout(scrollToWorkStart, 0)}
          />
        </div>
      </div>
      <OccurrenceDialog occ={selected} onClose={() => setSelected(null)} onEdit={(o) => { setSelected(null); setForm({ eventId: o.event_id, occurrence: o }); }} />
      {form && (!form.eventId || editEvent.data) && (
        <EventForm open onOpenChange={(o) => !o && setForm(null)} event={form.eventId ? editEvent.data : null} occurrence={form.occurrence} defaults={form.defaults} />
      )}
      <ScopeDialog open={!!pendingMove} onOpenChange={(o) => { if (!o) { pendingMove?.info.revert(); setPendingMove(null); } }} action="move"
        onChoose={(scope) => { const m = pendingMove!; setPendingMove(null); void applyMove(m.info, m.occ, scope); }} />
    </div>
  );
}

function OccurrenceDialog({ occ, onClose, onEdit }: { occ: Occurrence | null; onClose: () => void; onEdit: (o: Occurrence) => void }) {
  const { prefs } = useSession();
  const toast = useToast();
  const attendance = useAttendance();
  const cancelOcc = useCancelOccurrence();
  const del = useDeleteEvent();
  const [scopeOpen, setScopeOpen] = useState(false);
  if (!occ) return null;
  const remove = async (scope: "this" | "series") => {
    try {
      if (occ.is_recurring && scope === "this") await cancelOcc.mutateAsync({ id: occ.event_id, key: occ.key });
      else await del.mutateAsync(occ.event_id);
      toast.success(scope === "this" && occ.is_recurring ? "Occurrence removed" : "Event deleted");
      onClose();
    } catch (e) {
      toast.error("Couldn't delete", (e as Error).message);
    }
  };
  const mark = (value: string) =>
    attendance.mutate({ id: occ.event_id, key: occ.is_recurring ? occ.key : undefined, attendance: value }, {
      onSuccess: () => { toast.success("Saved"); onClose(); },
      onError: (e) => toast.error("Couldn't save", (e as Error).message),
    });
  const past = new Date(occ.end).getTime() < Date.now();
  return (
    <>
      <Dialog open onOpenChange={(o) => !o && onClose()} title={occ.title}
        description={occ.all_day ? `All day · ${occ.local_start.slice(0, 10)}` : `${formatDateTime(occ.start, prefs)} – ${formatTime(occ.end, prefs)}`}
        footer={<>
          <Button variant="ghost" icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={() => (occ.is_recurring ? setScopeOpen(true) : void remove("series"))} loading={del.isPending || cancelOcc.isPending}>Delete</Button>
          <Button icon={<Pencil className="h-4 w-4" aria-hidden />} onClick={() => onEdit(occ)}>Edit</Button>
        </>}>
        <div className="flex flex-col gap-3 text-sm">
          {occ.is_recurring && <p className="text-muted">{describeRRule(occ.rrule)}{occ.is_exception ? " · this occurrence was changed" : ""}</p>}
          {occ.location && <p className="flex items-center gap-2"><MapPin className="h-4 w-4 text-muted" aria-hidden />{occ.location}</p>}
          {occ.meeting_url && <a className="flex items-center gap-2 text-primary underline" href={occ.meeting_url} target="_blank" rel="noreferrer noopener"><Video className="h-4 w-4" aria-hidden />Join meeting</a>}
          {occ.description && <p className="whitespace-pre-wrap">{occ.description}</p>}
          {occ.status !== "confirmed" && <Badge tone="amber">{occ.status}</Badge>}
          <div className="border-t border-line pt-3">
            <p className="mb-2 font-medium">{past ? "How did it go?" : "Attendance"}</p>
            <div className="flex flex-wrap gap-2">
              {[["attended", "Attended"], ["completed", "Completed"], ["missed", "Missed"], ["", "Clear"]].map(([v, label]) => (
                <Button key={label} size="sm" variant={occ.attendance === v && v ? "primary" : "soft"} aria-pressed={occ.attendance === v} onClick={() => mark(v)}>{label}</Button>
              ))}
            </div>
          </div>
        </div>
      </Dialog>
      <ScopeDialog open={scopeOpen} onOpenChange={setScopeOpen} action="delete" onChoose={(scope) => { setScopeOpen(false); void remove(scope); }} />
    </>
  );
}
