import { useEffect, useState } from "react";
import { describeRRule, parseRRule, toRRule, type Freq, type RecurrenceValue } from "@/lib/recurrence";
import { DayPicker, Field, Input, Select } from "./ui/form";

/** Edits an RRULE through simple choices; shows a plain-language summary. Value is the RRULE string ('' = none). */
export function RecurrenceEditor({ value, onChange }: { value: string; onChange: (rule: string) => void }) {
  const [v, setV] = useState<RecurrenceValue>(() => parseRRule(value));
  useEffect(() => {
    setV(parseRRule(value));
  }, [value]);
  const update = (patch: Partial<RecurrenceValue>) => {
    const next = { ...v, ...patch };
    setV(next);
    onChange(toRRule(next));
  };
  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-control)] border border-line bg-surface-2 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Repeat">
          {({ id }) => (
            <Select id={id} value={v.freq} onChange={(e) => update({ freq: e.target.value as Freq })}>
              <option value="none">Does not repeat</option>
              <option value="DAILY">Daily</option>
              <option value="WEEKDAYS">Every weekday (Mon–Fri)</option>
              <option value="WEEKLY">Weekly</option>
              <option value="MONTHLY">Monthly</option>
              <option value="YEARLY">Yearly</option>
            </Select>
          )}
        </Field>
        {v.freq !== "none" && v.freq !== "WEEKDAYS" && (
          <Field label="Every">
            {({ id }) => (
              <div className="flex items-center gap-2">
                <Input id={id} type="number" min={1} max={99} value={v.interval} onChange={(e) => update({ interval: Math.max(1, Number(e.target.value) || 1) })} className="w-20" />
                <span className="text-sm text-muted">{{ DAILY: "day(s)", WEEKLY: "week(s)", MONTHLY: "month(s)", YEARLY: "year(s)" }[v.freq as "DAILY"]}</span>
              </div>
            )}
          </Field>
        )}
      </div>
      {v.freq === "WEEKLY" && <DayPicker label="On" value={v.byDay} onChange={(byDay) => update({ byDay })} />}
      {v.freq === "MONTHLY" && (
        <Field label="Day of the month" hint="Leave empty to repeat on the start date's day.">
          {({ id, describedBy }) => (
            <Input id={id} aria-describedby={describedBy} type="number" min={1} max={31} value={v.monthDay ?? ""}
              onChange={(e) => update({ monthDay: e.target.value ? Math.min(31, Math.max(1, Number(e.target.value))) : null })} className="w-24" />
          )}
        </Field>
      )}
      {v.freq !== "none" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Ends">
            {({ id }) => (
              <Select id={id} value={v.end} onChange={(e) => update({ end: e.target.value as RecurrenceValue["end"] })}>
                <option value="never">Never</option>
                <option value="until">On a date</option>
                <option value="count">After a number of times</option>
              </Select>
            )}
          </Field>
          {v.end === "until" && (
            <Field label="End date">{({ id }) => <Input id={id} type="date" value={v.until} onChange={(e) => update({ until: e.target.value })} />}</Field>
          )}
          {v.end === "count" && (
            <Field label="Occurrences">
              {({ id }) => <Input id={id} type="number" min={1} max={2000} value={v.count} onChange={(e) => update({ count: Math.max(1, Number(e.target.value) || 1) })} />}
            </Field>
          )}
        </div>
      )}
      <p className="text-sm text-muted" aria-live="polite">{describeRRule(toRRule(v))}</p>
    </div>
  );
}

const OFFSETS = [0, 5, 10, 15, 30, 60, 120, 1440];

export function offsetLabel(m: number): string {
  if (m === 0) return "At the time";
  if (m < 60) return `${m} min before`;
  if (m < 1440) return `${m / 60} h before`;
  return `${m / 1440} day before`;
}

/** Pick reminder offsets (minutes before). */
export function ReminderOffsetsEditor({ value, onChange, disabled, disabledReason }: { value: number[]; onChange: (v: number[]) => void; disabled?: boolean; disabledReason?: string }) {
  return (
    <fieldset disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium">Remind me</legend>
      {disabled && disabledReason && <p className="mb-1.5 text-xs text-muted">{disabledReason}</p>}
      <div className="flex flex-wrap gap-1.5">
        {OFFSETS.map((m) => {
          const on = value.includes(m);
          return (
            <button key={m} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== m) : [...value, m].sort((a, b) => a - b))}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors disabled:opacity-50 ${on ? "border-primary bg-sage-soft font-medium text-primary-strong" : "border-line bg-surface text-ink hover:bg-sage-soft"}`}>
              {offsetLabel(m)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
