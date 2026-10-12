import clsx from "clsx";
import { Switch as RSwitch } from "radix-ui";
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

const control =
  "w-full rounded-[var(--radius-control)] border border-line bg-surface px-3 text-ink placeholder:text-muted/80 " +
  "focus:border-primary disabled:opacity-60 aria-[invalid=true]:border-danger";

interface FieldProps {
  label: ReactNode;
  error?: string;
  hint?: ReactNode;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
  className?: string;
  optional?: boolean;
}

/** Label + control + hint/error, wired with aria-describedby and aria-invalid. */
export function Field({ label, error, hint, children, className, optional }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      {children({ id, describedBy: [hintId, errId].filter(Boolean).join(" ") || undefined, invalid: !!error })}
      {hint && !error && <p id={hintId} className="text-xs text-muted">{hint}</p>}
      {error && <p id={errId} role="alert" className="text-xs font-medium text-danger">{error}</p>}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={clsx(control, "h-11", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={clsx(control, "min-h-24 py-2.5", className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} className={clsx(control, "h-11 pr-8", className)} {...rest}>
      {children}
    </select>
  );
});

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}

export function Switch({ checked, onCheckedChange, label, description, disabled, id }: SwitchProps) {
  const auto = useId();
  const sid = id ?? auto;
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div className="min-w-0">
        <label htmlFor={sid} className="text-sm font-medium text-ink">{label}</label>
        {description && <p className="text-xs text-muted">{description}</p>}
      </div>
      <RSwitch.Root
        id={sid}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className="relative mt-0.5 h-7 w-12 shrink-0 rounded-full border border-line bg-sage transition-colors data-[state=checked]:bg-primary disabled:opacity-50"
      >
        <RSwitch.Thumb className="block h-5 w-5 translate-x-1 rounded-full bg-surface shadow transition-transform data-[state=checked]:translate-x-6" />
      </RSwitch.Root>
    </div>
  );
}

export function Checkbox({ checked, onChange, label, className }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; className?: string }) {
  return (
    <label className={clsx("inline-flex cursor-pointer items-center gap-2 text-sm", className)}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-5 w-5 accent-[var(--color-primary)]" />
      {label}
    </label>
  );
}

/** Weekday picker (0 = Monday) rendered as toggle buttons with aria-pressed. */
export function DayPicker({ value, onChange, label = "Days" }: { value: number[]; onChange: (v: number[]) => void; label?: string }) {
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  const names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {days.map((d, i) => {
          const on = value.includes(i);
          return (
            <button
              key={names[i]}
              type="button"
              aria-pressed={on}
              aria-label={names[i]}
              onClick={() => onChange(on ? value.filter((x) => x !== i) : [...value, i].sort())}
              className={clsx("h-10 w-10 rounded-full border text-sm font-medium transition-colors",
                on ? "border-primary bg-primary text-on-primary" : "border-line bg-surface text-ink hover:bg-sage-soft")}
            >
              {d}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

export function FormError({ message }: { message?: string }) {
  if (!message) return null;
  return <p role="alert" className="rounded-[var(--radius-control)] bg-danger-soft px-3 py-2 text-sm text-danger">{message}</p>;
}
