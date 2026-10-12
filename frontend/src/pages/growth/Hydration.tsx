import { Droplets, Minus, Plus } from "lucide-react";
import { useState } from "react";
import { ModuleReminderCard } from "@/components/ModuleReminderCard";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, ErrorState, LoadingList, ProgressRing } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useHydration, useUpdatePreferences, useWellnessMutation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/datetime";

export default function Hydration() {
  const { prefs } = useSession();
  const h = useHydration();
  const mut = useWellnessMutation();
  const updatePrefs = useUpdatePreferences();
  const toast = useToast();
  const [custom, setCustom] = useState("");
  if (h.isPending) return <LoadingList />;
  if (h.error) return <ErrorState error={h.error} onRetry={() => h.refetch()} />;
  const t = h.data.today;
  const unitLabel = t.unit === "glass" ? "glasses" : t.unit;
  const add = (amount: number, unit?: string) => mut.mutate(() => api.post("/wellness/water/", { amount, unit }), { onError: (e) => toast.error("Couldn't log water", (e as Error).message) });
  const max = Math.max(...h.data.week.map((d) => d.total_ml), t.target_ml, 1);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader title="Today" icon={Droplets} />
        <ProgressRing value={t.progress} size={96} label={`${t.total} of ${t.target} ${unitLabel}`} sublabel={`${t.total_ml} ml logged`} />
        <div className="mt-4 flex flex-wrap gap-2">
          <Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => add(1, "glass")} loading={mut.isPending}>Glass ({t.glass_ml} ml)</Button>
          <Button variant="soft" onClick={() => add(500, "ml")}>Bottle (500 ml)</Button>
        </div>
        <form className="mt-3 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (Number(custom) > 0) { add(Number(custom), prefs.hydration_unit === "glass" ? "ml" : prefs.hydration_unit); setCustom(""); } }}>
          <Field label={`Custom amount (${prefs.hydration_unit === "glass" ? "ml" : prefs.hydration_unit})`}>{({ id }) => <Input id={id} type="number" min={1} value={custom} onChange={(e) => setCustom(e.target.value)} className="w-32" />}</Field>
          <Button type="submit" variant="secondary">Add</Button>
          <Button variant="ghost" icon={<Minus className="h-4 w-4" aria-hidden />} onClick={async () => {
            const latest = await api.get<{ results: { id: number }[] }>("/wellness/water/", { date: t.date });
            if (latest.results[0]) mut.mutate(() => api.delete(`/wellness/water/${latest.results[0].id}/`));
          }}>Undo last</Button>
        </form>
      </Card>
      <Card>
        <CardHeader title="Last 7 days" />
        <ol className="flex h-32 items-end gap-2" aria-label="Water per day">
          {h.data.week.map((d) => (
            <li key={d.date} className="flex flex-1 flex-col items-center gap-1" aria-label={`${formatDate(d.date, prefs, "weekday")}: ${d.total_ml} ml`}>
              <div className="w-full rounded-t bg-primary/70" style={{ height: `${(d.total_ml / max) * 100}%`, minHeight: 2 }} />
              <span className="text-[0.65rem] text-muted">{formatDate(d.date, prefs, "weekday").slice(0, 3)}</span>
            </li>
          ))}
        </ol>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <Field label="Daily target">{({ id }) => <Input id={id} type="number" min={1} defaultValue={prefs.hydration_target} onBlur={(e) => updatePrefs.mutate({ hydration_target: Number(e.target.value) })} />}</Field>
          <Field label="Unit">{({ id }) => <Select id={id} value={prefs.hydration_unit} onChange={(e) => updatePrefs.mutate({ hydration_unit: e.target.value as "ml" })}><option value="ml">ml</option><option value="oz">oz</option><option value="glass">glasses</option></Select>}</Field>
          <Field label="Glass (ml)">{({ id }) => <Input id={id} type="number" min={50} defaultValue={prefs.glass_size_ml} onBlur={(e) => updatePrefs.mutate({ glass_size_ml: Number(e.target.value) })} />}</Field>
        </div>
      </Card>
      <div className="md:col-span-2"><ModuleReminderCard path="/wellness/water-reminder/" title="Water reminders" description="Gentle, spaced reminders through the day." interval /></div>
    </div>
  );
}
