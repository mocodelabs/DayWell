import { Lock, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useApplyPlan, usePlanner } from "@/hooks/queries";
import { formatTime, minutesLabel } from "@/lib/datetime";
import { useSession } from "@/features/auth/session";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";
import { ErrorState, LoadingList } from "./ui/feedback";
import { Checkbox } from "./ui/form";
import { useToast } from "./ui/Toast";

/** Suggests slots for flexible tasks around fixed commitments. Every suggestion must be accepted individually. */
export function PlannerDialog({ open, onOpenChange, date }: { open: boolean; onOpenChange: (o: boolean) => void; date: string }) {
  const { prefs } = useSession();
  const toast = useToast();
  const plan = usePlanner(date, open);
  const apply = useApplyPlan();
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  useEffect(() => setAccepted(new Set()), [plan.data]);
  const data = plan.data;
  const submit = async () => {
    if (!data) return;
    const items = data.suggestions.filter((s) => accepted.has(s.task_id)).map((s) => ({ task_id: s.task_id, start_time: s.start_time }));
    try {
      await apply.mutateAsync({ date, items });
      toast.success(`Scheduled ${items.length} task${items.length === 1 ? "" : "s"}`);
      onOpenChange(false);
    } catch (e) {
      toast.error("Couldn't apply the plan", (e as Error).message);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Plan my day" description="Suggestions only — nothing changes until you accept it." size="lg"
      footer={<><Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button><Button onClick={submit} disabled={!accepted.size} loading={apply.isPending}>Schedule {accepted.size || ""} selected</Button></>}>
      {plan.isPending && <LoadingList rows={3} label="Working out a plan" />}
      {plan.error && <ErrorState error={plan.error} onRetry={() => plan.refetch()} />}
      {data && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">
            Planning between {formatTime(data.window.start, prefs)} and {formatTime(data.window.end, prefs)}.
            {" "}Free time: {minutesLabel(data.free_minutes)} · flexible tasks need {minutesLabel(data.needed_minutes)}.
          </p>
          {data.overloaded && (
            <p className="flex items-start gap-2 rounded-xl bg-terracotta-soft p-3 text-sm" role="status">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              Today looks fuller than the time available. It's okay to move something to another day.
            </p>
          )}
          {data.fixed.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-sm font-semibold">Fixed (won't be moved)</h3>
              <ul className="flex flex-col gap-1 text-sm">
                {data.fixed.map((f, i) => (
                  <li key={i} className="flex items-center gap-2 text-muted"><Lock className="h-3.5 w-3.5" aria-hidden />{formatTime(f.start, prefs)}–{formatTime(f.end, prefs)} · {f.title}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold"><Sparkles className="h-4 w-4 text-amber" aria-hidden />Suggested times</h3>
            {data.suggestions.length === 0 ? (
              <p className="text-sm text-muted">No flexible tasks to place. Tasks without a time for today (or overdue) will appear here.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.suggestions.map((s) => (
                  <li key={s.task_id} className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-amber/60 bg-amber-soft/40 px-3 py-2">
                    <Checkbox
                      checked={accepted.has(s.task_id)}
                      onChange={(v) => setAccepted((prev) => { const n = new Set(prev); if (v) n.add(s.task_id); else n.delete(s.task_id); return n; })}
                      label={<span><span className="font-medium">{formatTime(s.start, prefs)}</span> · {s.title} <span className="text-muted">({minutesLabel(s.duration_minutes)})</span></span>}
                    />
                    <span className="shrink-0 text-xs text-muted">{s.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {data.unplaced.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-sm font-semibold">Didn't fit</h3>
              <ul className="list-disc pl-5 text-sm text-muted">{data.unplaced.map((u) => <li key={u.task_id}>{u.title} ({minutesLabel(u.duration_minutes)})</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}
