import clsx from "clsx";
import { BookOpen, Brain, Droplets, Dumbbell, Heart, Moon, NotebookPen } from "lucide-react";
import { lazy, Suspense } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { EmptyState, LoadingList, PageHeader } from "@/components/ui/feedback";
import { useSession } from "@/features/auth/session";
import type { ModuleKey } from "@/lib/types";

const Affirmations = lazy(() => import("./Affirmations"));
const Reading = lazy(() => import("./Reading"));
const Fitness = lazy(() => import("./Fitness"));
const Hydration = lazy(() => import("./Hydration"));
const Sleep = lazy(() => import("./Sleep"));
const Journal = lazy(() => import("./Journal"));
const Mindfulness = lazy(() => import("./Mindfulness"));

const TABS: { path: string; label: string; module: ModuleKey; icon: typeof Heart; el: React.ReactNode }[] = [
  { path: "reading", label: "Reading", module: "reading", icon: BookOpen, el: <Reading /> },
  { path: "fitness", label: "Fitness", module: "fitness", icon: Dumbbell, el: <Fitness /> },
  { path: "affirmations", label: "Affirmations", module: "affirmations", icon: Heart, el: <Affirmations /> },
  { path: "hydration", label: "Hydration", module: "hydration", icon: Droplets, el: <Hydration /> },
  { path: "sleep", label: "Sleep", module: "sleep", icon: Moon, el: <Sleep /> },
  { path: "journal", label: "Journal", module: "journal", icon: NotebookPen, el: <Journal /> },
  { path: "mindfulness", label: "Mindfulness", module: "mindfulness", icon: Brain, el: <Mindfulness /> },
];

export default function Growth() {
  const { prefs } = useSession();
  const enabled = TABS.filter((t) => prefs.modules[t.module]);
  return (
    <div>
      <PageHeader title="Growth" subtitle="Reading, movement and wellbeing — only the parts you've chosen." />
      {enabled.length === 0 ? (
        <EmptyState title="No growth modules turned on" action={<Link to="/settings/modules" className="font-medium text-primary hover:underline">Choose modules</Link>}>
          Reading, fitness, affirmations, hydration, sleep, journaling and mindfulness are all optional.
        </EmptyState>
      ) : (
        <>
          <nav className="mb-5 flex gap-1 overflow-x-auto pb-1" aria-label="Growth sections">
            {enabled.map((t) => (
              <NavLink key={t.path} to={`/growth/${t.path}`}
                className={({ isActive }) => clsx("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium",
                  isActive ? "border-primary bg-primary text-on-primary" : "border-line bg-surface text-muted hover:text-ink")}>
                <t.icon className="h-4 w-4" aria-hidden />{t.label}
              </NavLink>
            ))}
            <Link to="/settings/modules" className="shrink-0 px-3 py-1.5 text-sm text-primary hover:underline">More modules…</Link>
          </nav>
          <Suspense fallback={<LoadingList rows={4} />}>
            <Routes>
              <Route index element={<Navigate to={enabled[0].path} replace />} />
              {enabled.map((t) => <Route key={t.path} path={t.path} element={t.el} />)}
              <Route path="*" element={<EmptyState title="This module is turned off" action={<Link to="/settings/modules" className="text-primary underline">Turn it on in Settings</Link>} />} />
            </Routes>
          </Suspense>
        </>
      )}
    </div>
  );
}
