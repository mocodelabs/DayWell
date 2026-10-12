import clsx from "clsx";
import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { Toast as RToast } from "radix-ui";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info";
interface ToastItem {
  id: number;
  kind: Kind;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

interface ToastApi {
  show: (t: Omit<ToastItem, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
}

const Ctx = createContext<ToastApi | null>(null);
let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const show = useCallback((t: Omit<ToastItem, "id">) => setItems((prev) => [...prev.slice(-3), { ...t, id: ++counter }]), []);
  const api = useMemo<ToastApi>(() => ({
    show,
    success: (title, description) => show({ kind: "success", title, description }),
    error: (title, description) => show({ kind: "error", title, description }),
    info: (title, description) => show({ kind: "info", title, description }),
  }), [show]);
  const icons = { success: CheckCircle2, error: TriangleAlert, info: Info };
  return (
    <Ctx.Provider value={api}>
      <RToast.Provider swipeDirection="down" duration={5000}>
        {children}
        {items.map((t) => {
          const Icon = icons[t.kind];
          return (
            <RToast.Root
              key={t.id}
              type={t.kind === "error" ? "foreground" : "background"}
              onOpenChange={(open) => !open && setItems((prev) => prev.filter((x) => x.id !== t.id))}
              className={clsx("flex items-start gap-3 rounded-[var(--radius-card)] border bg-surface p-3.5 shadow-[var(--shadow-card)] dw-enter",
                t.kind === "error" ? "border-danger/40" : "border-line")}
            >
              <Icon className={clsx("mt-0.5 h-5 w-5 shrink-0", { success: "text-primary", error: "text-danger", info: "text-amber" }[t.kind])} aria-hidden />
              <div className="min-w-0 flex-1">
                <RToast.Title className="text-sm font-semibold">{t.title}</RToast.Title>
                {t.description && <RToast.Description className="text-sm text-muted">{t.description}</RToast.Description>}
              </div>
              {t.action && (
                <RToast.Action altText={t.action.label} asChild>
                  <button className="rounded-md px-2 py-1 text-sm font-semibold text-primary hover:bg-sage-soft" onClick={t.action.onClick}>{t.action.label}</button>
                </RToast.Action>
              )}
              <RToast.Close aria-label="Dismiss" className="rounded-full p-1 text-muted hover:bg-sage-soft"><X className="h-4 w-4" aria-hidden /></RToast.Close>
            </RToast.Root>
          );
        })}
        <RToast.Viewport className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-1/2 z-[60] flex w-[min(94vw,24rem)] -translate-x-1/2 flex-col gap-2 outline-none lg:bottom-6 lg:left-auto lg:right-6 lg:translate-x-0" />
      </RToast.Provider>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
