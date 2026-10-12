import { Bell, CalendarClock } from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboard } from "@/hooks/queries";
import { formatTime, relativeMinutes } from "@/lib/datetime";
import { useSession } from "@/features/auth/session";

/** Optional right-hand panel (xl screens): the next commitments and reminders for today. */
export function UpNextPanel() {
  const { prefs } = useSession();
  const dash = useDashboard();
  const now = Date.now();
  const agenda = (dash.data?.agenda ?? []).filter((a) => !a.all_day && new Date(a.end).getTime() > now).slice(0, 5);
  const reminders = dash.data?.reminders.upcoming ?? [];
  return (
    <aside aria-label="Up next" className="sticky top-0 hidden h-dvh w-72 shrink-0 overflow-y-auto border-l border-line bg-surface-2 px-4 py-6 2xl:block">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted"><CalendarClock className="h-4 w-4" aria-hidden /> Up next</h2>
      {agenda.length === 0 ? (
        <p className="text-sm text-muted">Nothing else timed today.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {agenda.map((a) => (
            <li key={`${a.type}-${a.id}-${a.key ?? ""}`} className="rounded-xl border border-line bg-surface p-3">
              <p className="text-xs text-muted">{formatTime(a.start, prefs)} · {relativeMinutes(a.start, now)}</p>
              <p className="text-sm font-medium">{a.title}</p>
              {a.type === "task" && <p className="text-xs text-muted">Task</p>}
            </li>
          ))}
        </ol>
      )}
      <h2 className="mt-6 mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted"><Bell className="h-4 w-4" aria-hidden /> Reminders</h2>
      {reminders.length === 0 ? (
        <p className="text-sm text-muted">No more reminders scheduled today.</p>
      ) : (
        <ul className="flex flex-col gap-1.5 text-sm">
          {reminders.map((r) => (
            <li key={r.id} className="flex justify-between gap-2"><span className="truncate">{r.title}</span><span className="shrink-0 text-muted">{formatTime(r.fire_at, prefs)}</span></li>
          ))}
        </ul>
      )}
      <Link to="/reminders" className="mt-3 inline-block text-sm font-medium text-primary hover:underline">Manage reminders</Link>
    </aside>
  );
}
