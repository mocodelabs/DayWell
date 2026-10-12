import { CalendarDays, Clock, Repeat, Sparkles, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useCreateTask } from "@/hooks/queries";
import { formatDate, formatWallTime, todayIn } from "@/lib/datetime";
import { parseQuickEntry } from "@/lib/quickparse";
import { describeRRule } from "@/lib/recurrence";
import { useSession } from "@/features/auth/session";
import { offsetLabel } from "./RecurrenceEditor";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { Field, FormError, Input } from "./ui/form";
import { useToast } from "./ui/Toast";

/**
 * One-line task entry. Shows exactly what was understood (date, time, reminder, repeat) before saving, and lets the
 * user correct the date/time. Ambiguous dates are never applied silently.
 */
export function QuickAddDialog({ open, onOpenChange, onOpenFull }: { open: boolean; onOpenChange: (o: boolean) => void; onOpenFull: (draft: { title: string; date: string; time: string }) => void }) {
  const { prefs } = useSession();
  const toast = useToast();
  const create = useCreateTask();
  const [text, setText] = useState("");
  const [dateOverride, setDateOverride] = useState<string | null>(null);
  const [timeOverride, setTimeOverride] = useState<string | null>(null);
  const [error, setError] = useState("");
  const today = todayIn(prefs.time_zone);
  const parsed = useMemo(() => parseQuickEntry(text, today), [text, today]);
  const date = dateOverride ?? parsed.date ?? "";
  const time = timeOverride ?? parsed.time ?? "";
  const reset = () => {
    setText("");
    setDateOverride(null);
    setTimeOverride(null);
    setError("");
  };

  const submit = async () => {
    if (!parsed.title) {
      setError("What would you like to do?");
      return;
    }
    if (parsed.rrule && !date) {
      setError("A repeating task needs a start date.");
      return;
    }
    try {
      await create.mutateAsync({
        title: parsed.title,
        scheduled_date: date || null,
        scheduled_time: date && time ? time : null,
        priority: parsed.priority ?? "normal",
        recurrence: parsed.rrule ?? undefined,
        reminders: parsed.reminderMinutes !== null && date && time ? [{ offset_minutes: parsed.reminderMinutes, anchor: "start" }] : [],
      });
      toast.success("Added", parsed.title);
      reset();
      onOpenChange(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const reminderNeedsTime = parsed.reminderMinutes !== null && !(date && time);
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
      title="Quick add"
      description="Try: “Call the supplier tomorrow at 10 am and remind me 15 minutes before”."
      footer={
        <>
          <Button variant="ghost" onClick={() => { onOpenFull({ title: parsed.title, date, time }); reset(); }}>More options</Button>
          <Button onClick={submit} loading={create.isPending} disabled={!text.trim()}>Add task</Button>
        </>
      }
    >
      <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="flex flex-col gap-4">
        <Field label="What do you need to do?">
          {({ id }) => <Input id={id} value={text} onChange={(e) => setText(e.target.value)} autoFocus autoComplete="off" placeholder="e.g. Gym every Monday at 6 pm" />}
        </Field>
        <FormError message={error} />
        {text.trim() && (
          <div className="rounded-[var(--radius-control)] border border-line bg-surface-2 p-3" aria-live="polite">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted"><Sparkles className="h-3.5 w-3.5" aria-hidden /> Here's what we understood</p>
            <p className="font-medium">{parsed.title || <span className="text-muted">(no title yet)</span>}</p>
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              <li className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-primary" aria-hidden />{date ? formatDate(date, prefs, "long") : "No date — goes to your inbox"}</li>
              <li className="flex items-center gap-2"><Clock className="h-4 w-4 text-primary" aria-hidden />{time ? formatWallTime(time, prefs) : "No time"}</li>
              {parsed.reminderMinutes !== null && <li className="flex items-center gap-2"><Clock className="h-4 w-4 text-amber" aria-hidden />Reminder: {offsetLabel(parsed.reminderMinutes)}{reminderNeedsTime ? " (needs a date and time)" : ""}</li>}
              {parsed.rrule && <li className="flex items-center gap-2"><Repeat className="h-4 w-4 text-primary" aria-hidden />{describeRRule(parsed.rrule)}</li>}
              {parsed.priority && <li className="text-muted">Priority: {parsed.priority}</li>}
            </ul>
            {parsed.notes.some((n) => n.includes("24-hour")) && <p className="mt-2 text-xs text-muted">{parsed.notes.find((n) => n.includes("24-hour"))}</p>}
            {parsed.ambiguous.map((a) => (
              <p key={a} className="mt-2 flex items-start gap-1.5 text-sm text-danger" role="alert"><TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{a}</p>
            ))}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Field label="Date">{({ id }) => <Input id={id} type="date" value={date} onChange={(e) => setDateOverride(e.target.value)} />}</Field>
              <Field label="Time">{({ id }) => <Input id={id} type="time" value={time} onChange={(e) => setTimeOverride(e.target.value)} />}</Field>
            </div>
          </div>
        )}
      </form>
    </Dialog>
  );
}
