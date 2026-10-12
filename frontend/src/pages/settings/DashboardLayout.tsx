import { ArrowDown, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/feedback";
import { Switch } from "@/components/ui/form";
import { useSession } from "@/features/auth/session";
import type { Preferences, SectionKey } from "@/lib/types";
import { useSettingSaver } from "./useSettingSaver";

const LABELS: Record<SectionKey, string> = {
  briefing: "Greeting & briefing", progress: "Today's progress", agenda: "Agenda", priorities: "Top priorities", reminders: "Reminders", habits: "Habits",
  affirmation: "Affirmation", reading: "Reading", fitness: "Movement", hydration: "Hydration", evening: "Evening recap",
};

/** Reorder and hide Today sections. Buttons (not drag) so it works with keyboards and screen readers. */
export default function DashboardLayout() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  const layout = prefs.dashboard_layout;
  const commit = (next: Preferences["dashboard_layout"]) => save({ dashboard_layout: next }, "Layout saved");
  const move = (i: number, d: -1 | 1) => {
    const next = [...layout];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    commit(next);
  };
  return (
    <Card>
      <CardHeader title="Today page sections" />
      <p className="mb-3 text-sm text-muted">Choose what shows on Today and in what order. Module sections only appear when the module is on.</p>
      <ol className="flex flex-col gap-1.5">
        {layout.map((s, i) => (
          <li key={s.key} className="flex items-center gap-2 rounded-xl border border-line px-3 py-1">
            <div className="flex-1"><Switch label={LABELS[s.key]} checked={s.visible} onCheckedChange={(v) => commit(layout.map((x) => (x.key === s.key ? { ...x, visible: v } : x)))} /></div>
            <Button size="icon" variant="ghost" aria-label={`Move ${LABELS[s.key]} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="h-4 w-4" aria-hidden /></Button>
            <Button size="icon" variant="ghost" aria-label={`Move ${LABELS[s.key]} down`} disabled={i === layout.length - 1} onClick={() => move(i, 1)}><ArrowDown className="h-4 w-4" aria-hidden /></Button>
          </li>
        ))}
      </ol>
    </Card>
  );
}
