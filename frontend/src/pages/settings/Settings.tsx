import clsx from "clsx";
import { Bell, CreditCard, Eye, LayoutDashboard, Puzzle, Shield, Sun, User } from "lucide-react";
import { lazy, Suspense } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { LoadingList, PageHeader } from "@/components/ui/feedback";

const Profile = lazy(() => import("./Profile"));
const DayRhythm = lazy(() => import("./DayRhythm"));
const Modules = lazy(() => import("./Modules"));
const DashboardLayout = lazy(() => import("./DashboardLayout"));
const NotificationSettings = lazy(() => import("./NotificationSettings"));
const Appearance = lazy(() => import("./Appearance"));
const Privacy = lazy(() => import("./Privacy"));
const Billing = lazy(() => import("./Billing"));

const SECTIONS = [
  { path: "profile", label: "Profile & region", icon: User, el: <Profile /> },
  { path: "rhythm", label: "Day, tone & briefings", icon: Sun, el: <DayRhythm /> },
  { path: "notifications", label: "Notifications & alarms", icon: Bell, el: <NotificationSettings /> },
  { path: "modules", label: "Modules", icon: Puzzle, el: <Modules /> },
  { path: "dashboard", label: "Today page", icon: LayoutDashboard, el: <DashboardLayout /> },
  { path: "appearance", label: "Appearance & accessibility", icon: Eye, el: <Appearance /> },
  { path: "privacy", label: "Privacy & security", icon: Shield, el: <Privacy /> },
  { path: "billing", label: "Plan & billing", icon: CreditCard, el: <Billing /> },
];

export default function Settings() {
  return (
    <div>
      <PageHeader title="Settings" />
      <div className="grid gap-5 lg:grid-cols-[14rem_1fr]">
        <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
          {SECTIONS.map((s) => (
            <NavLink key={s.path} to={`/settings/${s.path}`} className={({ isActive }) => clsx("flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium",
              isActive ? "bg-sage-soft text-primary-strong" : "text-muted hover:bg-sage-soft hover:text-ink")}>
              <s.icon className="h-4 w-4" aria-hidden />{s.label}
            </NavLink>
          ))}
        </nav>
        <div className="min-w-0">
          <Suspense fallback={<LoadingList rows={4} />}>
            <Routes>
              <Route index element={<Navigate to="profile" replace />} />
              {SECTIONS.map((s) => <Route key={s.path} path={s.path} element={s.el} />)}
            </Routes>
          </Suspense>
        </div>
      </div>
    </div>
  );
}
