import { AlarmClock, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { offsetLabel, RecurrenceEditor } from "@/components/RecurrenceEditor";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Badge, EmptyState, ErrorState, LoadingList, PageHeader, SegmentedControl } from "@/components/ui/feedback";
import { Field, FormError, Input, Select, Switch } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useDeleteReminder, useReminders, useSaveReminder } from "@/hooks/queries";
import { applyServerErrors } from "@/lib/api";
import { SOUND_LABELS, SOUNDS } from "@/lib/audio";
import { formatDateTime, todayIn } from "@/lib/datetime";
import { describeRRule } from "@/lib/recurrence";
import type { Reminder } from "@/lib/types";

const CATEGORIES = ["custom", "tasks", "habits", "reading", "fitness", "hydration", "sleep", "mindfulness", "affirmations", "admin"];

export default function Reminders() {
  const { prefs } = useSession();
  const [kind, setKind] = useState<"absolute" | "relative">("absolute");
  const list = useReminders({ kind });
  const del = useDeleteReminder();
  const save = useSaveReminder();
  const [editing, setEditing] = useState<Reminder | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<Reminder | null>(null);
  return (
    <div>
      <PageHeader title="Reminders" subtitle="Set reminders at a time of your choosing. Reminders for tasks and events are set on the task or event itself."
        actions={<Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setEditing(null)}>New reminder</Button>} />
      <div className="mb-4"><SegmentedControl label="Reminder type" value={kind} onChange={setKind} options={[{ value: "absolute", label: "Scheduled" }, { value: "relative", label: "On tasks & events" }]} /></div>
      {list.isPending ? <LoadingList /> : list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : list.data.results.length === 0 ? (
        <EmptyState icon={AlarmClock} title="No reminders here" action={kind === "absolute" ? <Button size="sm" onClick={() => setEditing(null)}>Create a reminder</Button> : undefined}>
          {kind === "relative" ? "Add a reminder when you create a task or calendar event." : "Bedtime, medication, a weekly call — anything you'd like a nudge for."}
        </EmptyState>
      ) : (
        <ul className="flex flex-col gap-2">
          {list.data.results.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3">
              <AlarmClock className={`h-5 w-5 ${r.enabled ? "text-primary" : "text-muted"}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{r.title} {!r.enabled && <Badge>Off</Badge>} {r.bypass_quiet_hours && <Badge tone="amber">Breaks quiet hours</Badge>}</p>
                <p className="text-xs text-muted">
                  {r.kind === "relative" ? `${offsetLabel(r.offset_minutes)} the ${r.anchor === "deadline" ? "deadline" : "start"} · ${r.linked?.type.replace("_", " ")}` : `${describeRRule(r.rrule)} at ${r.dtstart_time?.slice(0, 5)}`}
                  {" · "}{r.category}{r.next_fire_at ? ` · next ${formatDateTime(r.next_fire_at, prefs)}` : ""}
                </p>
              </div>
              {r.kind === "absolute" ? (
                <>
                  <Switch label={<span className="sr-only">Enabled</span>} checked={r.enabled} onCheckedChange={(enabled) => save.mutate({ id: r.id, enabled })} />
                  <Button size="icon" variant="ghost" aria-label={`Edit ${r.title}`} onClick={() => setEditing(r)}><Pencil className="h-4 w-4" aria-hidden /></Button>
                  <Button size="icon" variant="ghost" aria-label={`Delete ${r.title}`} onClick={() => setDeleting(r)}><Trash2 className="h-4 w-4" aria-hidden /></Button>
                </>
              ) : (
                <Link className="text-sm text-primary hover:underline" to={r.linked?.type === "event" ? "/calendar" : "/tasks"}>Open</Link>
              )}
            </li>
          ))}
        </ul>
      )}
      {editing !== undefined && <ReminderForm reminder={editing} onClose={() => setEditing(undefined)} />}
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} danger title={`Delete “${deleting?.title}”?`} confirmLabel="Delete"
        description="Future alerts are cancelled. Past alerts stay in your notification history." loading={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })} />
    </div>
  );
}

function ReminderForm({ reminder, onClose }: { reminder: Reminder | null; onClose: () => void }) {
  const { prefs } = useSession();
  const save = useSaveReminder();
  const toast = useToast();
  const [v, setV] = useState({
    title: reminder?.title ?? "", message: reminder?.message ?? "", category: reminder?.category ?? "custom", priority: reminder?.priority ?? "normal",
    dtstart_date: reminder?.dtstart_date ?? todayIn(prefs.time_zone), dtstart_time: reminder?.dtstart_time?.slice(0, 5) ?? "09:00", rrule: reminder?.rrule ?? "",
    sound: reminder?.sound ?? "", snooze_minutes: reminder?.snooze_minutes ? String(reminder.snooze_minutes) : "", bypass_quiet_hours: reminder?.bypass_quiet_hours ?? false,
    repeat_until_ack: reminder?.repeat_until_ack ?? false, repeat_every_minutes: String(reminder?.repeat_every_minutes ?? 5),
  });
  const [error, setError] = useState("");
  const submit = async () => {
    setError("");
    try {
      await save.mutateAsync({ id: reminder?.id, ...v, snooze_minutes: v.snooze_minutes ? Number(v.snooze_minutes) : null, repeat_every_minutes: Number(v.repeat_every_minutes) } as never);
      toast.success(reminder ? "Reminder updated" : "Reminder set");
      onClose();
    } catch (e) {
      setError(applyServerErrors(e, () => undefined, []));
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={reminder ? "Edit reminder" : "New reminder"} size="lg"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={save.isPending}>Save</Button></>}>
      <div className="flex flex-col gap-3">
        <FormError message={error} />
        <Field label="Title">{({ id }) => <Input id={id} autoFocus value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} placeholder="Take vitamins" />}</Field>
        <Field label="Message" optional>{({ id }) => <Input id={id} value={v.message} onChange={(e) => setV({ ...v, message: e.target.value })} />}</Field>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Starting">{({ id }) => <Input id={id} type="date" value={v.dtstart_date} onChange={(e) => setV({ ...v, dtstart_date: e.target.value })} />}</Field>
          <Field label="Time">{({ id }) => <Input id={id} type="time" value={v.dtstart_time} onChange={(e) => setV({ ...v, dtstart_time: e.target.value })} />}</Field>
          <Field label="Category">{({ id }) => <Select id={id} value={v.category} onChange={(e) => setV({ ...v, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}</Select>}</Field>
          <Field label="Sound">{({ id }) => <Select id={id} value={v.sound} onChange={(e) => setV({ ...v, sound: e.target.value })}><option value="">Default</option>{SOUNDS.map((s) => <option key={s} value={s}>{SOUND_LABELS[s]}</option>)}</Select>}</Field>
        </div>
        <RecurrenceEditor value={v.rrule} onChange={(rrule) => setV({ ...v, rrule })} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Snooze length (min)" optional>{({ id }) => <Input id={id} type="number" min={1} max={240} value={v.snooze_minutes} onChange={(e) => setV({ ...v, snooze_minutes: e.target.value })} placeholder="Category default" />}</Field>
          <Field label="Priority">{({ id }) => <Select id={id} value={v.priority} onChange={(e) => setV({ ...v, priority: e.target.value as Reminder["priority"] })}><option value="normal">Normal</option><option value="high">High</option><option value="critical">Critical</option></Select>}</Field>
        </div>
        <Switch label="Allowed during quiet hours" description="Only for things that truly can't wait." checked={v.bypass_quiet_hours} onCheckedChange={(bypass_quiet_hours) => setV({ ...v, bypass_quiet_hours })} />
        <Switch label="Keep reminding until I respond" description="Repeats up to 3 times if you don't snooze, dismiss or complete it." checked={v.repeat_until_ack} onCheckedChange={(repeat_until_ack) => setV({ ...v, repeat_until_ack })} />
        {v.repeat_until_ack && <Field label="Repeat every (min)">{({ id }) => <Input id={id} type="number" min={1} max={60} value={v.repeat_every_minutes} onChange={(e) => setV({ ...v, repeat_every_minutes: e.target.value })} className="w-28" />}</Field>}
      </div>
    </Dialog>
  );
}
