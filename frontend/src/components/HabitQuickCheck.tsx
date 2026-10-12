import clsx from "clsx";
import { Check, Minus, Plus } from "lucide-react";
import { useHabitAction } from "@/hooks/queries";
import type { DashboardHabit } from "@/lib/types";
import { useToast } from "./ui/Toast";

/** One habit on the daily checklist: tap to complete (binary) or +/- for counted targets. */
export function HabitQuickCheck({ habit, date }: { habit: DashboardHabit; date?: string }) {
  const act = useHabitAction();
  const toast = useToast();
  const done = habit.status === "done";
  const value = Number(habit.value);
  const target = Number(habit.target_value);
  const run = (action: "complete" | "undo" | "increment", body?: object) =>
    act.mutate({ id: habit.id, action, body: { date, ...body } }, { onError: (e) => toast.error("Couldn't update the habit", (e as Error).message) });
  if (habit.target_type === "binary") {
    return (
      <button
        type="button"
        aria-pressed={done}
        onClick={() => run(done ? "undo" : "complete")}
        disabled={act.isPending}
        className={clsx("flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors",
          done ? "border-primary/40 bg-sage-soft" : "border-line bg-surface hover:bg-sage-soft")}
      >
        <span className={clsx("grid h-7 w-7 shrink-0 place-items-center rounded-full border-2", done ? "border-primary bg-primary text-on-primary" : "border-line")} aria-hidden>
          {done && <Check className="h-4 w-4" />}
        </span>
        <span className="flex-1 font-medium">{habit.name}</span>
        <span className="text-xs text-muted">{done ? "Done" : habit.status === "skipped" ? "Rest day" : "To do"}</span>
      </button>
    );
  }
  return (
    <div className={clsx("flex items-center gap-3 rounded-xl border px-3 py-2", done ? "border-primary/40 bg-sage-soft" : "border-line bg-surface")}>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{habit.name}</p>
        <p className="text-xs text-muted">{value} / {target} {habit.unit}{done ? " · Done" : ""}</p>
        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-sage" aria-hidden>
          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, (value / (target || 1)) * 100)}%` }} />
        </div>
      </div>
      <button type="button" onClick={() => run("increment", { amount: -1 })} disabled={act.isPending || value <= 0}
        className="grid h-10 w-10 place-items-center rounded-full border border-line hover:bg-sage-soft disabled:opacity-40" aria-label={`Remove one from ${habit.name}`}>
        <Minus className="h-4 w-4" aria-hidden />
      </button>
      <button type="button" onClick={() => run("increment", { amount: habit.target_type === "duration" ? 5 : 1 })} disabled={act.isPending}
        className="grid h-10 w-10 place-items-center rounded-full bg-primary text-on-primary hover:bg-primary-strong" aria-label={`Add ${habit.target_type === "duration" ? "5 minutes" : "one"} to ${habit.name}`}>
        <Plus className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
