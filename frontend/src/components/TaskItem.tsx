import clsx from "clsx";
import { AlarmClock, CalendarClock, Circle, CircleCheck, Repeat, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useTaskAction } from "@/hooks/queries";
import { formatDate, formatWallTime } from "@/lib/datetime";
import type { Priority, TaskCard, TaskStatus } from "@/lib/types";
import { useSession } from "@/features/auth/session";
import { useToast } from "./ui/Toast";

const PRIORITY: Record<Priority, { label: string; cls: string }> = {
  urgent: { label: "Urgent", cls: "bg-danger-soft text-danger border-danger/30" },
  high: { label: "High", cls: "bg-terracotta-soft text-ink border-terracotta/40" },
  normal: { label: "", cls: "" },
  low: { label: "Low", cls: "bg-surface-2 text-muted border-line" },
};

type Item = Pick<TaskCard, "id" | "title" | "priority" | "status" | "scheduled_date" | "scheduled_time" | "is_overdue" | "is_recurring"> & {
  hasReminder?: boolean;
  subtitle?: ReactNode;
};

/** A task row with a large, labelled completion toggle. Status is shown with icon + text, not colour alone. */
export function TaskItem({ task, onOpen, showDate = false, actions }: { task: Item; onOpen?: () => void; showDate?: boolean; actions?: ReactNode }) {
  const { prefs } = useSession();
  const act = useTaskAction();
  const toast = useToast();
  const done = task.status === "completed";
  const cancelled = task.status === "cancelled";
  const toggle = async () => {
    try {
      await act.mutateAsync({ id: task.id, action: done ? "reopen" : "complete" });
      if (!done) {
        toast.show({ kind: "success", title: "Completed", description: task.title, action: { label: "Undo", onClick: () => act.mutate({ id: task.id, action: "reopen" }) } });
      }
    } catch (e) {
      toast.error("Couldn't update the task", (e as Error).message);
    }
  };
  const p = PRIORITY[task.priority];
  return (
    <div className={clsx("group flex items-start gap-3 rounded-xl border border-line bg-surface px-3 py-2.5", done && "bg-surface-2")}>
      <button
        type="button"
        onClick={toggle}
        disabled={act.isPending || cancelled}
        aria-label={done ? `Mark “${task.title}” as not done` : `Mark “${task.title}” as done`}
        aria-pressed={done}
        className="-m-1 mt-[-0.15rem] rounded-full p-1 text-primary disabled:opacity-40"
      >
        {done ? <CircleCheck className="h-6 w-6" aria-hidden /> : <Circle className="h-6 w-6" aria-hidden />}
      </button>
      <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left" disabled={!onOpen}>
        <p className={clsx("font-medium leading-snug", (done || cancelled) && "text-muted line-through")}>{task.title}</p>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          {showDate && task.scheduled_date && <span className="inline-flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5" aria-hidden />{formatDate(task.scheduled_date, prefs, "weekday")}</span>}
          {task.scheduled_time && <span>{formatWallTime(task.scheduled_time, prefs)}</span>}
          {task.is_overdue && <span className="inline-flex items-center gap-1 text-terracotta"><TriangleAlert className="h-3.5 w-3.5" aria-hidden />Overdue</span>}
          {task.is_recurring && <span className="inline-flex items-center gap-1"><Repeat className="h-3.5 w-3.5" aria-hidden /><span className="sr-only">Repeats</span></span>}
          {task.hasReminder && <span className="inline-flex items-center gap-1"><AlarmClock className="h-3.5 w-3.5" aria-hidden /><span className="sr-only">Has reminder</span></span>}
          {task.status === "postponed" && <span>Postponed</span>}
          {task.status === "in_progress" && <span>In progress</span>}
          {cancelled && <span>Cancelled</span>}
          {task.subtitle}
        </div>
      </button>
      {p.label && <span className={clsx("shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium", p.cls)}>{p.label}</span>}
      {actions}
    </div>
  );
}

export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending", in_progress: "In progress", completed: "Completed", postponed: "Postponed", cancelled: "Cancelled",
};
