import clsx from "clsx";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "soft";
type Size = "sm" | "md" | "lg" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-strong shadow-sm",
  secondary: "bg-surface text-ink border border-line hover:bg-sage-soft",
  soft: "bg-sage-soft text-primary-strong hover:bg-sage",
  ghost: "text-ink hover:bg-sage-soft",
  danger: "bg-danger text-on-primary hover:opacity-90",
};
const sizes: Record<Size, string> = {
  sm: "h-9 px-3 text-sm gap-1.5",
  md: "h-11 px-4 text-sm gap-2",
  lg: "h-12 px-5 text-base gap-2",
  icon: "h-11 w-11 justify-center",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon, className, children, disabled, type = "button", ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex select-none items-center justify-center rounded-[var(--radius-control)] font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-55",
        variants[variant], sizes[size], className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function IconButton({ label, className, ...rest }: ButtonProps & { label: string }) {
  return <Button variant="ghost" size="icon" aria-label={label} title={label} className={clsx("shrink-0", className)} {...rest} />;
}
