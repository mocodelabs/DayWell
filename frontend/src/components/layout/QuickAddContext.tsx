import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import type { Task, TaskInput } from "@/lib/types";
import { QuickAddDialog } from "../QuickAddDialog";
import { TaskForm } from "../TaskForm";

interface QuickAddApi {
  openQuickAdd: () => void;
  openTaskForm: (opts?: { task?: Task | null; defaults?: Partial<TaskInput> }) => void;
}

const Ctx = createContext<QuickAddApi>({ openQuickAdd: () => undefined, openTaskForm: () => undefined });
export const useQuickAdd = () => useContext(Ctx);

export function QuickAddProvider({ children }: { children: ReactNode }) {
  const [quickOpen, setQuickOpen] = useState(false);
  const [form, setForm] = useState<{ task?: Task | null; defaults?: Partial<TaskInput> } | null>(null);
  const [params, setParams] = useSearchParams();

  const openQuickAdd = useCallback(() => setQuickOpen(true), []);
  const openTaskForm = useCallback((opts?: { task?: Task | null; defaults?: Partial<TaskInput> }) => setForm(opts ?? {}), []);

  // PWA shortcut / deep link: /?quickadd=1
  useEffect(() => {
    if (params.get("quickadd")) {
      setQuickOpen(true);
      params.delete("quickadd");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);

  // Keyboard shortcut: "n" opens quick add (not while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "n" && !e.metaKey && !e.ctrlKey && !e.altKey && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) && !t.isContentEditable) {
        e.preventDefault();
        setQuickOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Ctx.Provider value={{ openQuickAdd, openTaskForm }}>
      {children}
      <QuickAddDialog
        open={quickOpen}
        onOpenChange={setQuickOpen}
        onOpenFull={(draft) => {
          setQuickOpen(false);
          setForm({ defaults: { title: draft.title, scheduled_date: draft.date || null, scheduled_time: draft.time || null } });
        }}
      />
      <TaskForm open={!!form} onOpenChange={(o) => !o && setForm(null)} task={form?.task} defaults={form?.defaults} />
    </Ctx.Provider>
  );
}
