import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { useCategories, useChangeOccurrence, useSaveEvent } from "@/hooks/queries";
import { applyServerErrors } from "@/lib/api";
import type { CalendarEvent, Occurrence } from "@/lib/types";
import { useSession } from "@/features/auth/session";
import { RecurrenceEditor, ReminderOffsetsEditor } from "./RecurrenceEditor";
import { Button } from "./ui/Button";
import { Dialog, ScopeDialog } from "./ui/Dialog";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "./ui/form";
import { useToast } from "./ui/Toast";

const schema = z.object({
  title: z.string().trim().min(1, "Give the event a title.").max(200),
  all_day: z.boolean(),
  start_date: z.string().min(1, "Choose a date."),
  start_time: z.string(),
  end_date: z.string(),
  end_time: z.string(),
  location: z.string().max(300),
  meeting_url: z.string().refine((v) => v === "" || /^https?:\/\//.test(v), "Use a full link starting with https://"),
  description: z.string().max(5000),
  category: z.string(),
  status: z.enum(["confirmed", "tentative", "cancelled"]),
}).superRefine((v, ctx) => {
  if (!v.all_day && !v.start_time) ctx.addIssue({ code: "custom", path: ["start_time"], message: "Choose a start time, or make it all-day." });
  if (!v.all_day && !v.end_time) ctx.addIssue({ code: "custom", path: ["end_time"], message: "Choose an end time." });
  const sd = v.start_date, ed = v.end_date || v.start_date;
  if (ed < sd || (!v.all_day && ed === sd && v.end_time && v.start_time && v.end_time <= v.start_time)) {
    ctx.addIssue({ code: "custom", path: ["end_time"], message: "The event must end after it starts." });
  }
});
type Values = z.infer<typeof schema>;

export interface EventFormProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  event?: CalendarEvent | null;
  occurrence?: Occurrence | null;
  defaults?: { start_date: string; start_time?: string; end_time?: string; all_day?: boolean };
}

export function EventForm(props: EventFormProps) {
  return props.open ? <EventFormInner {...props} /> : null;
}

function EventFormInner({ open, onOpenChange, event, occurrence, defaults }: EventFormProps) {
  const { prefs } = useSession();
  const toast = useToast();
  const categories = useCategories();
  const save = useSaveEvent();
  const changeOcc = useChangeOccurrence();
  const [rrule, setRrule] = useState(event?.rrule ?? "");
  const [offsets, setOffsets] = useState<number[]>(event?.reminder_offsets ?? [15]);
  const [formError, setFormError] = useState("");
  const [scopeOpen, setScopeOpen] = useState(false);
  const [pending, setPending] = useState<Values | null>(null);
  // When editing one occurrence of a series, start from that occurrence's (possibly moved) local times.
  const occStart = occurrence?.local_start ? occurrence.local_start : null;
  const occEnd = occurrence?.local_end ? occurrence.local_end : null;
  const { register, handleSubmit, control, watch, setError, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: occurrence?.title ?? event?.title ?? "",
      all_day: event?.all_day ?? defaults?.all_day ?? false,
      start_date: occStart?.slice(0, 10) ?? event?.start_date ?? defaults?.start_date ?? "",
      start_time: (occStart && !event?.all_day ? occStart.slice(11, 16) : event?.start_time?.slice(0, 5)) ?? defaults?.start_time ?? "09:00",
      end_date: occEnd?.slice(0, 10) ?? event?.end_date ?? defaults?.start_date ?? "",
      end_time: (occEnd && !event?.all_day ? occEnd.slice(11, 16) : event?.end_time?.slice(0, 5)) ?? defaults?.end_time ?? "10:00",
      location: occurrence?.location ?? event?.location ?? "",
      meeting_url: event?.meeting_url ?? "",
      description: occurrence?.description ?? event?.description ?? "",
      category: event?.category ? String(event.category) : "",
      status: event?.status ?? "confirmed",
    },
  });
  const allDay = watch("all_day");

  const persist = async (v: Values, scope: "this" | "series") => {
    setFormError("");
    try {
      if (event && occurrence && event.rrule && scope === "this") {
        await changeOcc.mutateAsync({
          id: event.id, key: occurrence.key, title: v.title, description: v.description, location: v.location,
          start_date: v.start_date, start_time: v.all_day ? null : v.start_time, end_date: v.end_date || v.start_date, end_time: v.all_day ? null : v.end_time,
        });
        toast.success("This occurrence was updated");
      } else {
        const body = {
          title: v.title, all_day: v.all_day, start_date: v.start_date, end_date: v.end_date || v.start_date,
          start_time: v.all_day ? null : v.start_time, end_time: v.all_day ? null : v.end_time, location: v.location, meeting_url: v.meeting_url,
          description: v.description, category: v.category ? Number(v.category) : null, status: v.status, rrule,
          reminder_offsets: v.all_day ? [] : offsets, time_zone: event?.time_zone ?? prefs.time_zone,
        };
        if (event && occurrence && event.rrule) {
          // Series edit from an occurrence: keep the series' own start date, apply the new times and details.
          Object.assign(body, { start_date: event.start_date, end_date: event.end_date });
        }
        const res = await save.mutateAsync({ id: event?.id, ...body });
        if (res.conflicts?.length) {
          toast.info("Saved — heads up", `This overlaps with ${res.conflicts.map((c) => (c.a.event_id === res.id ? c.b.title : c.a.title)).slice(0, 2).join(", ")}.`);
        } else {
          toast.success(event ? "Event updated" : "Event added");
        }
      }
      onOpenChange(false);
    } catch (e) {
      setFormError(applyServerErrors(e, setError, ["title", "start_date", "start_time", "end_date", "end_time", "meeting_url", "location"]));
    }
  };

  const onSubmit = (v: Values) => {
    if (event?.rrule && occurrence) {
      setPending(v);
      setScopeOpen(true);
      return;
    }
    void persist(v, "series");
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange} title={event ? "Edit event" : "New event"} size="lg"
        description={event?.time_zone && event.time_zone !== prefs.time_zone ? `Times are in ${event.time_zone}.` : undefined}
        footer={<><Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" form="event-form" loading={save.isPending || changeOcc.isPending}>{event ? "Save" : "Add event"}</Button></>}>
        <form id="event-form" onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <FormError message={formError} />
          <Field label="Title" error={errors.title?.message}>{({ id, invalid }) => <Input id={id} autoFocus aria-invalid={invalid} {...register("title")} />}</Field>
          <Controller control={control} name="all_day" render={({ field }) => <Checkbox checked={field.value} onChange={field.onChange} label="All day" />} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Starts" error={errors.start_date?.message}>{({ id }) => <Input id={id} type="date" {...register("start_date")} />}</Field>
            {!allDay && <Field label="Start time" error={errors.start_time?.message}>{({ id, invalid }) => <Input id={id} type="time" aria-invalid={invalid} {...register("start_time")} />}</Field>}
            <Field label="Ends">{({ id }) => <Input id={id} type="date" {...register("end_date")} />}</Field>
            {!allDay && <Field label="End time" error={errors.end_time?.message}>{({ id, invalid }) => <Input id={id} type="time" aria-invalid={invalid} {...register("end_time")} />}</Field>}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Location" optional>{({ id }) => <Input id={id} {...register("location")} />}</Field>
            <Field label="Meeting link" optional error={errors.meeting_url?.message}>{({ id, invalid }) => <Input id={id} type="url" placeholder="https://" aria-invalid={invalid} {...register("meeting_url")} />}</Field>
          </div>
          {!(event?.rrule && occurrence) && (
            <>
              {!allDay && <ReminderOffsetsEditor value={offsets} onChange={setOffsets} />}
              <div>
                <p className="mb-1.5 text-sm font-medium">Repeat</p>
                <RecurrenceEditor value={rrule} onChange={setRrule} />
              </div>
            </>
          )}
          <details className="rounded-[var(--radius-control)] border border-line p-3">
            <summary className="cursor-pointer text-sm font-medium">More details</summary>
            <div className="mt-3 flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Category" optional>
                  {({ id }) => <Select id={id} {...register("category")}><option value="">None</option>{categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>}
                </Field>
                <Field label="Status">
                  {({ id }) => <Select id={id} {...register("status")}><option value="confirmed">Confirmed</option><option value="tentative">Tentative</option><option value="cancelled">Cancelled</option></Select>}
                </Field>
              </div>
              <Field label="Notes" optional>{({ id }) => <Textarea id={id} rows={3} {...register("description")} />}</Field>
            </div>
          </details>
        </form>
      </Dialog>
      <ScopeDialog open={scopeOpen} onOpenChange={setScopeOpen} onChoose={(scope) => { setScopeOpen(false); if (pending) void persist(pending, scope); }} />
    </>
  );
}
