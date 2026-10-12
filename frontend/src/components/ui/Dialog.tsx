import clsx from "clsx";
import { X } from "lucide-react";
import { AlertDialog, Dialog as RDialog } from "radix-ui";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { useReturnFocus } from "./useReturnFocus";

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

/** Centered dialog on desktop, bottom sheet on small screens. Focus trap, Esc and labelled title come from Radix. */
export function Dialog({ open, onOpenChange, title, description, children, footer, size = "md" }: DialogProps) {
  const focus = useReturnFocus(open);
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-40 bg-black/35 dw-enter" />
        <RDialog.Content
         
          onCloseAutoFocus={focus.onCloseAutoFocus}
          className={clsx(
            "fixed z-50 flex max-h-[92dvh] flex-col bg-surface text-ink shadow-[var(--shadow-card)] dw-enter",
            "inset-x-0 bottom-0 rounded-t-[1.25rem] sm:inset-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-[var(--radius-card)]",
            { sm: "sm:w-[26rem]", md: "sm:w-[34rem]", lg: "sm:w-[44rem]" }[size],
          )}
          {...(description ? {} : { "aria-describedby": undefined })}
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <RDialog.Title className="text-lg font-semibold">{title}</RDialog.Title>
              {description && <RDialog.Description className="mt-0.5 text-sm text-muted">{description}</RDialog.Description>}
            </div>
            <RDialog.Close asChild>
              <button className="-mr-2 rounded-full p-2 text-muted hover:bg-sage-soft" aria-label="Close">
                <X className="h-5 w-5" aria-hidden />
              </button>
            </RDialog.Close>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{footer}</div>}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

interface ConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  children?: ReactNode;
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", danger, loading, onConfirm, children }: ConfirmProps) {
  const focus = useReturnFocus(open);
  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/35" />
        <AlertDialog.Content onCloseAutoFocus={focus.onCloseAutoFocus} className="fixed top-1/2 left-1/2 z-50 w-[min(92vw,26rem)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-card)] bg-surface p-5 shadow-[var(--shadow-card)] dw-enter">
          <AlertDialog.Title className="text-lg font-semibold">{title}</AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm text-muted">{description}</AlertDialog.Description>
          {children && <div className="mt-3">{children}</div>}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary">{cancelLabel}</Button>
            </AlertDialog.Cancel>
            <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

/** Ask whether an edit applies to one occurrence or the whole series. */
export function ScopeDialog({ open, onOpenChange, onChoose, action = "change" }: {
  open: boolean; onOpenChange: (o: boolean) => void; onChoose: (scope: "this" | "series") => void; action?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="This is a repeating item" description={`Do you want to ${action} just this one, or the whole series?`} size="sm">
      <div className="flex flex-col gap-2">
        <Button variant="secondary" onClick={() => onChoose("this")}>Only this occurrence</Button>
        <Button onClick={() => onChoose("series")}>This and every other occurrence</Button>
      </div>
    </Dialog>
  );
}
