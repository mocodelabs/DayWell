import { AlarmClock } from "lucide-react";
import { useEffect, useState } from "react";
import { useModuleReminder, useSaveModuleReminder } from "@/hooks/queries";
import type { ModuleReminder } from "@/lib/types";
import { Button } from "./ui/Button";
import { Card, CardHeader } from "./ui/feedback";
import { DayPicker, Field, Input, Select, Switch } from "./ui/form";
import { useToast } from "./ui/Toast";

/** "Remind me at HH:MM on these days" for an optional module (reading, affirmation, wind-down, …). */
export function ModuleReminderCard({ path, title, description, interval = false }: { path: string; title: string; description?: string; interval?: boolean }) {
  const q = useModuleReminder(path);
  const save = useSaveModuleReminder(path);
  const toast = useToast();
  const [v, setV] = useState<ModuleReminder>({ enabled: false, time: "08:00", days: [0, 1, 2, 3, 4, 5, 6], every_minutes: 120, until: "19:00" });
  useEffect(() => {
    if (q.data) setV({ ...q.data, time: q.data.time ?? "08:00", every_minutes: q.data.every_minutes ?? 120, until: q.data.until ?? "19:00" });
  }, [q.data]);
  const submit = () => save.mutate(v, {
    onSuccess: (d) => toast.success(d.enabled ? "Reminder saved" : "Reminder turned off"),
    onError: (e) => toast.error("Couldn't save the reminder", (e as Error).message),
  });
  return (
    <Card>
      <CardHeader title={title} icon={AlarmClock} />
      {description && <p className="-mt-1 mb-2 text-sm text-muted">{description}</p>}
      <Switch label="Remind me" checked={v.enabled} onCheckedChange={(enabled) => setV({ ...v, enabled })} />
      {v.enabled && (
        <div className="mt-2 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label={interval ? "From" : "At"}>{({ id }) => <Input id={id} type="time" value={v.time ?? ""} onChange={(e) => setV({ ...v, time: e.target.value })} />}</Field>
            {interval && <Field label="Until">{({ id }) => <Input id={id} type="time" value={v.until ?? ""} onChange={(e) => setV({ ...v, until: e.target.value })} />}</Field>}
          </div>
          {interval && (
            <Field label="Every">
              {({ id }) => (
                <Select id={id} value={v.every_minutes} onChange={(e) => setV({ ...v, every_minutes: Number(e.target.value) })}>
                  <option value={60}>Hour</option><option value={120}>2 hours</option><option value={180}>3 hours</option>
                </Select>
              )}
            </Field>
          )}
          <DayPicker value={v.days} onChange={(days) => setV({ ...v, days })} />
        </div>
      )}
      <div className="mt-3"><Button size="sm" onClick={submit} loading={save.isPending}>Save</Button></div>
    </Card>
  );
}
