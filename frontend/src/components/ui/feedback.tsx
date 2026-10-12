import clsx from "clsx";
import { CloudOff, RefreshCw, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { Button } from "./Button";

export function Card({ children, className, as: As = "section", ...rest }: { children: ReactNode; className?: string; as?: "section" | "div" | "article"; "aria-labelledby"?: string }) {
  return <As className={clsx("rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-[var(--shadow-card)] sm:p-5", className)} {...rest}>{children}</As>;
}

export function CardHeader({ title, action, id, icon: Icon }: { title: ReactNode; action?: ReactNode; id?: string; icon?: LucideIcon }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <h2 id={id} className="flex items-center gap-2 text-base font-semibold">
        {Icon && <Icon className="h-4.5 w-4.5 text-primary" aria-hidden />}
        {title}
      </h2>
      {action}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-sage/60", className)} aria-hidden />;
}

export function LoadingList({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-2">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-14 w-full" />)}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children, action }: { icon?: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-line px-4 py-8 text-center">
      {Icon && <Icon className="h-8 w-8 text-primary/70" aria-hidden />}
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-sm text-sm text-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const offline = error instanceof ApiError && error.isNetwork;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className={clsx("flex flex-col items-center gap-2 rounded-[var(--radius-card)] bg-danger-soft/60 text-center", compact ? "p-3" : "px-4 py-8")}>
      {offline && <CloudOff className="h-7 w-7 text-danger" aria-hidden />}
      <p className="text-sm font-medium text-ink">{offline ? "You're offline" : "That didn't load"}</p>
      <p className="max-w-sm text-sm text-muted">{message}</p>
      {onRetry && <Button size="sm" variant="secondary" icon={<RefreshCw className="h-4 w-4" aria-hidden />} onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "primary" | "warn" | "danger" | "amber"; className?: string }) {
  const tones = {
    neutral: "bg-surface-2 text-muted border-line",
    primary: "bg-sage-soft text-primary-strong border-sage",
    warn: "bg-terracotta-soft text-ink border-terracotta/40",
    danger: "bg-danger-soft text-danger border-danger/30",
    amber: "bg-amber-soft text-ink border-amber/40",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

/** Circular progress with a text label — never colour alone. ``value`` null renders an em-dash (nothing planned). */
export function ProgressRing({ value, size = 64, label, sublabel }: { value: number | null; size?: number; label?: string; sublabel?: string }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value));
  const text = value === null ? "—" : `${Math.round(pct * 100)}%`;
  return (
    <div className="flex items-center gap-3">
      <svg width={size} height={size} role="img" aria-label={`${label ?? "Progress"}: ${value === null ? "nothing planned yet" : text}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-sage)" strokeWidth={7} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-primary)" strokeWidth={7} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - pct)} transform={`rotate(-90 ${size / 2} ${size / 2})`} className="transition-[stroke-dashoffset] duration-500" />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-[var(--color-ink)] text-[0.8rem] font-semibold">{text}</text>
      </svg>
      {(label || sublabel) && (
        <div>
          {label && <p className="text-sm font-medium">{label}</p>}
          {sublabel && <p className="text-xs text-muted">{sublabel}</p>}
        </div>
      )}
    </div>
  );
}

export function ProgressBar({ value, label, className }: { value: number | null; label: string; className?: string }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div className={className}>
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct * 100)}
        className="h-2.5 w-full overflow-hidden rounded-full bg-sage">
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${pct * 100}%` }} />
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function SegmentedControl<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-[var(--radius-control)] border border-line bg-surface p-1">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={clsx("rounded-[0.55rem] px-3 py-1.5 text-sm font-medium transition-colors",
            value === o.value ? "bg-primary text-on-primary" : "text-muted hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
