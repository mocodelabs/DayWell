import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { useCategories, useCreateTask, useUpdateTask } from "@/hooks/queries";
import { applyServerErrors } from "@/lib/api";
import { isoToZoned, zonedToIso } from "@/lib/datetime";
import type { Task, TaskInput } from "@/lib/types";
import { useSession } from "@/features/auth/session";
import { RecurrenceEditor, ReminderOffsetsEditor } from "./RecurrenceEditor";
import { Button } from "./ui/Button";
import { Dialog, ScopeDialog } from "./ui/Dialog";
import { Checkbox, Field, FormError, Input, Select, Textarea } from "./ui/form";
import { useToast } from "./ui/Toast";

const schema = z.object({
  title: z.string().trim().min(1, "Give the task a title.").max(200),
  description: z.string().max(5000),
  priority: z.enum(["low", "normal", "high", "urgent"]),
  important: z.boolean(),
  category: z.string(),
  scheduled_date: z.string(),
  scheduled_time: z.string(),
  duration_minutes: z.string().refine((v) => v === "" || (Number(v) > 0 && Number(v) <= 1440), "Between 1 and 1440 minutes."),
  deadline_date: z.string(),
  deadline_time: z.string(),
  tags: z.string().max(400),
  link_url: z.string().refine((v) => v === "" || /^https?:\/\//.test(v), "Use a full link starting with https://"),
  notes: z.string().max(10000),
  checklist: z.string().max(4000),
}).refine((v) => !v.scheduled_time || v.scheduled_date, { path: ["scheduled_time"], message: "Pick a date for this time." });

type Values = z.infer<typeof schema>;

export interface TaskFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task?: Task | null;
  defaults?: Partial<TaskInput>;
}

export function TaskForm({ open, onOpenChange, task, defaults }: TaskFormProps) {
  return open ? <TaskFormInner open={open} onOpenChange={onOpenChange} task={task} defaults={defaults} /> : null;
}

function TaskFormInner({ open, onOpenChange, task, defaults }: TaskFormProps) {
  const { prefs } = useSession();
  const toast = useToast();
  const categories = useCategories();
  const create = useCreateTask();
  const update = useUpdateTask();
  const [rrule, setRrule] = useState(defaults?.recurrence ?? "");
  const [offsets, setOffsets] = useState<number[]>(task?.reminders.filter((r) => r.anchor === "start").map((r) => r.offset_minutes) ?? defaults?.reminders?.map((r) => r.offset_minutes) ?? []);
  const [deadlineOffsets, setDeadlineOffsets] = useState<number[]>(task?.reminders.filter((r) => r.anchor === "deadline").map((r) => r.offset_minutes) ?? []);
  const [formError, setFormError] = useState("");
  const [scopeOpen, setScopeOpen] = useState(false);
  const [pending, setPending] = useState<TaskInput | null>(null);
  const deadline = task?.deadline ? isoToZoned(task.deadline, prefs.time_zone) : null;

  const { register, handleSubmit, control, watch, setError, formState: { errors } } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: task?.title ?? defaults?.title ?? "",
      description: task?.description ?? "",
      priority: task?.priority ?? defaults?.priority ?? "normal",
      important: task?.important ?? false,
      category: task?.category ? String(task.category) : defaults?.category ? String(defaults.category) : "",
      scheduled_date: task?.scheduled_date ?? defaults?.scheduled_date ?? "",
      scheduled_time: task?.scheduled_time?.slice(0, 5) ?? defaults?.scheduled_time ?? "",
      duration_minutes: task?.duration_minutes ? String(task.duration_minutes) : "",
      deadline_date: deadline?.date ?? "",
      deadline_time: deadline?.time ?? "",
      tags: task?.tags.join(", ") ?? "",
      link_url: task?.link_url ?? "",
      notes: task?.notes ?? "",
      checklist: "",
    },
  });
  const hasTime = !!watch("scheduled_date") && !!watch("scheduled_time");
  const hasDeadline = !!watch("deadline_date");

  const save = async (body: TaskInput, scope: "this" | "series" = "this") => {
    setFormError("");
    try {
      if (task) {
        await update.mutateAsync({ id: task.id, scope, ...body });
        toast.success("Task updated");
      } else {
        await create.mutateAsync(body);
        toast.success("Task added", body.scheduled_date ? undefined : "It's in your inbox until you give it a date.");
      }
      onOpenChange(false);
    } catch (e) {
      setFormError(applyServerErrors(e, setError, ["title", "scheduled_date", "scheduled_time", "duration_minutes", "link_url", "tags"]));
    }
  };

  const onSubmit = (v: Values) => {
    const body: TaskInput = {
      title: v.title,
      description: v.description,
      notes: v.notes,
      priority: v.priority,
      important: v.important,
      category: v.category ? Number(v.category) : null,
      scheduled_date: v.scheduled_date || null,
      scheduled_time: v.scheduled_time || null,
      duration_minutes: v.duration_minutes ? Number(v.duration_minutes) : null,
      deadline: v.deadline_date ? zonedToIso(v.deadline_date, v.deadline_time || "23:59", prefs.time_zone) : null,
      tags: v.tags.split(",").map((t) => t.trim()).filter(Boolean),
      link_url: v.link_url,
      reminders: [
        ...(hasTime ? offsets.map((m) => ({ offset_minutes: m, anchor: "start" as const })) : []),
        ...(hasDeadline ? deadlineOffsets.map((m) => ({ offset_minutes: m, anchor: "deadline" as const })) : []),
      ],
    };
    if (!task) {
      body.checklist = v.checklist.split("\n").map((s) => s.trim()).filter(Boolean);
      if (rrule) body.recurrence = rrule;
    }
    if (task?.series && !task.detached) {
      setPending(body);
      setScopeOpen(true);
      return;
    }
    void save(body);
  };

  const busy = create.isPending || update.isPending;
  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        title={task ? "Edit task" : "New task"}
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" form="task-form" loading={busy}>{task ? "Save changes" : "Add task"}</Button>
          </>
        }
      >
        <form id="task-form" onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <FormError message={formError} />
          <Field label="Title" error={errors.title?.message}>
            {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} autoFocus {...register("title")} />}
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Date" optional error={errors.scheduled_date?.message}>{({ id }) => <Input id={id} type="date" {...register("scheduled_date")} />}</Field>
            <Field label="Time" optional error={errors.scheduled_time?.message}>{({ id, invalid }) => <Input id={id} type="time" aria-invalid={invalid} {...register("scheduled_time")} />}</Field>
            <Field label="Duration (min)" optional error={errors.duration_minutes?.message}>
              {({ id, invalid }) => <Input id={id} type="number" min={1} inputMode="numeric" aria-invalid={invalid} {...register("duration_minutes")} />}
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Priority">
              {({ id }) => (
                <Select id={id} {...register("priority")}>
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </Select>
              )}
            </Field>
            <Field label="Category" optional>
              {({ id }) => (
                <Select id={id} {...register("category")}>
                  <option value="">None</option>
                  {categories.data?.filter((c) => !c.archived).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              )}
            </Field>
            <div className="flex items-end pb-2">
              <Controller control={control} name="important" render={({ field }) => <Checkbox checked={field.value} onChange={field.onChange} label="Important" />} />
            </div>
          </div>
          <ReminderOffsetsEditor value={offsets} onChange={setOffsets} disabled={!hasTime} disabledReason="Add a date and time to set reminders before the start." />
          {!task && (
            <div>
              <p className="mb-1.5 text-sm font-medium">Repeat</p>
              <RecurrenceEditor value={rrule} onChange={setRrule} />
              {rrule && !watch("scheduled_date") && <p className="mt-1 text-xs text-danger" role="alert">A repeating task needs a start date.</p>}
            </div>
          )}
          {task?.series_rule && <p className="text-sm text-muted">Part of a repeating series. Changes can apply to this one or the whole series.</p>}
          <details className="rounded-[var(--radius-control)] border border-line p-3">
            <summary className="cursor-pointer text-sm font-medium">More details</summary>
            <div className="mt-3 flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Deadline date" optional>{({ id }) => <Input id={id} type="date" {...register("deadline_date")} />}</Field>
                <Field label="Deadline time" optional hint="Defaults to the end of the day.">{({ id, describedBy }) => <Input id={id} type="time" aria-describedby={describedBy} {...register("deadline_time")} />}</Field>
              </div>
              {hasDeadline && (
                <div>
                  <p className="mb-1 text-xs text-muted">Reminders before the deadline</p>
                  <ReminderOffsetsEditor value={deadlineOffsets} onChange={setDeadlineOffsets} />
                </div>
              )}
              <Field label="Description" optional>{({ id }) => <Textarea id={id} rows={3} {...register("description")} />}</Field>
              {!task && (
                <Field label="Checklist" optional hint="One item per line.">{({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={3} {...register("checklist")} />}</Field>
              )}
              <Field label="Tags" optional hint="Separate with commas.">{({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} {...register("tags")} />}</Field>
              <Field label="Link" optional error={errors.link_url?.message}>{({ id, invalid }) => <Input id={id} type="url" aria-invalid={invalid} placeholder="https://" {...register("link_url")} />}</Field>
              <Field label="Notes" optional>{({ id }) => <Textarea id={id} rows={3} {...register("notes")} />}</Field>
            </div>
          </details>
        </form>
      </Dialog>
      <ScopeDialog
        open={scopeOpen}
        onOpenChange={setScopeOpen}
        action="change"
        onChoose={(scope) => {
          setScopeOpen(false);
          if (pending) void save(pending, scope);
        }}
      />
    </>
  );
}
