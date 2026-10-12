import { Bell, BellOff, Check, Clock, Moon, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Badge, EmptyState, ErrorState, LoadingList, PageHeader, SegmentedControl } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useAlarmAction, useMarkAllRead, useMissedAlarms, useNotifications } from "@/hooks/queries";
import { formatDateTime, isoToZoned, todayIn, zonedToIso } from "@/lib/datetime";
import type { AlarmOccurrence, Delivery } from "@/lib/types";

const DELIVERY_LABEL: Record<Delivery["result"], string> = {
  pending: "pending", accepted: "sent (not yet confirmed)", delivered: "shown on your device", failed: "failed", expired: "device no longer subscribed",
};

export default function Notifications() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as "missed" | "history") || "history";
  const [category, setCategory] = useState("");
  const history = useNotifications({ category: category || undefined, page_size: 50 });
  const missed = useMissedAlarms();
  const readAll = useMarkAllRead();
  return (
    <div>
      <PageHeader title="Notifications" subtitle="Every reminder, what happened to it, and how it reached you."
        actions={tab === "history" ? <Button variant="secondary" size="sm" onClick={() => readAll.mutate()} loading={readAll.isPending}>Mark all read</Button> : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SegmentedControl label="Notification view" value={tab} onChange={(t) => setParams({ tab: t })}
          options={[{ value: "history", label: "History" }, { value: "missed", label: `Needs attention${missed.data?.length ? ` (${missed.data.length})` : ""}` }]} />
        {tab === "history" && (
          <Select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-auto">
            <option value="">All categories</option>
            {["tasks", "events", "habits", "reading", "fitness", "hydration", "sleep", "mindfulness", "affirmations", "briefing", "custom"].map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
        )}
      </div>
      {tab === "missed" ? (
        missed.isPending ? <LoadingList /> : missed.error ? <ErrorState error={missed.error} /> : missed.data.length === 0 ? (
          <EmptyState icon={Check} title="You're all caught up">Nothing was missed. Reminders that couldn't reach you will show up here — never as a flood of old alerts.</EmptyState>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted">These reminders passed while DayWell couldn't reach you or you weren't around. Choose what to do with each — nothing is marked complete automatically.</p>
            {missed.data.map((o) => <MissedRow key={o.id} occ={o} />)}
          </div>
        )
      ) : history.isPending ? <LoadingList /> : history.error ? <ErrorState error={history.error} /> : history.data.results.length === 0 ? (
        <EmptyState icon={Bell} title="No notifications yet">When reminders fire, you'll see them here with their delivery status.</EmptyState>
      ) : (
        <ul className="flex flex-col gap-2">{history.data.results.map((o) => <HistoryRow key={o.id} occ={o} />)}</ul>
      )}
    </div>
  );
}

function HistoryRow({ occ }: { occ: AlarmOccurrence }) {
  const { prefs } = useSession();
  const tone = occ.status === "completed" ? "primary" : occ.status === "missed" || occ.status === "failed" ? "warn" : "neutral";
  return (
    <li className={`rounded-xl border bg-surface p-3 ${occ.read_at ? "border-line" : "border-primary/40"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{!occ.read_at && <span className="sr-only">Unread: </span>}{occ.title}</p>
          {occ.body && <p className="text-sm text-muted">{occ.body}</p>}
        </div>
        <Badge tone={tone}>{occ.status_label}{occ.skip_reason ? ` · ${occ.skip_reason.replaceAll("_", " ")}` : ""}</Badge>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" aria-hidden />Scheduled {formatDateTime(occ.scheduled_for, prefs)}</span>
        <span>{occ.category}</span>
        {occ.silent && <span>Delivered quietly (quiet hours)</span>}
        {occ.audio_status && <span>Sound: {occ.audio_status === "played" ? "played" : occ.audio_status === "blocked" ? "blocked by the browser" : occ.audio_status}</span>}
        {occ.deliveries.map((d) => <span key={d.id}>{d.channel === "push" ? "Push" : "In-app"}: {DELIVERY_LABEL[d.result]}{d.kind === "escalation" ? " (repeat)" : ""}</span>)}
        {occ.snoozed_until && <span>Snoozed until {formatDateTime(occ.snoozed_until, prefs)}</span>}
      </div>
    </li>
  );
}

function MissedRow({ occ }: { occ: AlarmOccurrence }) {
  const { prefs } = useSession();
  const act = useAlarmAction();
  const toast = useToast();
  const [rescheduling, setRescheduling] = useState(false);
  const local = isoToZoned(new Date(Date.now() + 3600_000).toISOString(), prefs.time_zone);
  const [date, setDate] = useState(local.date);
  const [time, setTime] = useState(local.time);
  const run = (action: "complete" | "snooze" | "dismiss" | "keep" | "reschedule", body?: object, msg?: string) =>
    act.mutate({ id: occ.id, action, body }, { onSuccess: () => msg && toast.success(msg), onError: (e) => toast.error("That didn't work", (e as Error).message) });
  return (
    <div className="rounded-xl border border-terracotta/40 bg-surface p-3">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-terracotta" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{occ.title}</p>
          <p className="text-xs text-muted">Was due {formatDateTime(occ.scheduled_for, prefs)} · {occ.status === "missed" ? "couldn't be delivered on time" : occ.status === "failed" ? "delivery failed" : "not acted on"}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {occ.can_complete && <Button size="sm" icon={<Check className="h-4 w-4" aria-hidden />} onClick={() => run("complete", undefined, "Marked complete")}>Mark complete</Button>}
        <Button size="sm" variant="soft" icon={<Moon className="h-4 w-4" aria-hidden />} onClick={() => run("snooze", { minutes: occ.snooze_minutes }, "Snoozed")}>Snooze {occ.snooze_minutes} min</Button>
        <Button size="sm" variant="soft" onClick={() => setRescheduling(true)}>Reschedule</Button>
        {occ.linked?.type === "task" && <Button size="sm" variant="ghost" onClick={() => run("keep", undefined, "Kept — it stays on your overdue list")}>Keep overdue</Button>}
        <Button size="sm" variant="ghost" icon={<BellOff className="h-4 w-4" aria-hidden />} onClick={() => run("dismiss", undefined, "Dismissed")}>Dismiss</Button>
      </div>
      <Dialog open={rescheduling} onOpenChange={setRescheduling} title="Remind me again at…" size="sm"
        footer={<Button loading={act.isPending} onClick={() => { run("reschedule", { at: zonedToIso(date, time, prefs.time_zone) }, "Rescheduled"); setRescheduling(false); }}>Reschedule</Button>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date">{({ id }) => <Input id={id} type="date" min={todayIn(prefs.time_zone)} value={date} onChange={(e) => setDate(e.target.value)} />}</Field>
          <Field label="Time">{({ id }) => <Input id={id} type="time" value={time} onChange={(e) => setTime(e.target.value)} />}</Field>
        </div>
      </Dialog>
    </div>
  );
}
