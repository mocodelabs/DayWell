import clsx from "clsx";
import {
  BarChart3, Bell, CalendarDays, CheckSquare, ChevronsLeft, ChevronsRight, CloudOff, Ellipsis, Leaf, Lock, LogOut, Plus, Settings, Sparkles, Sprout, Sun, TriangleAlert, type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useDashboard, useUnreadCount } from "@/hooks/queries";
import { useSession, useSignOut } from "@/features/auth/session";
import { daysUntil, useBilling } from "@/features/billing/billing";
import { Dialog } from "../ui/Dialog";
import { PushNudge } from "./PushNudge";
import { UpNextPanel } from "./UpNextPanel";
import { useQuickAdd } from "./QuickAddContext";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Today", icon: Sun, end: true },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/tasks", label: "Tasks", icon: CheckSquare },
  { to: "/habits", label: "Habits", icon: Sprout },
  { to: "/growth", label: "Growth", icon: Leaf },
  { to: "/insights", label: "Insights", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];
const MOBILE_PRIMARY = NAV.slice(0, 4);

function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function AppShell() {
  const { prefs, user } = useSession();
  const signOut = useSignOut();
  const { openQuickAdd } = useQuickAdd();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("dw:sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const [moreOpen, setMoreOpen] = useState(false);
  const online = useOnline();
  const unread = useUnreadCount();
  const location = useLocation();
  // The dashboard (also used by Today and the up-next panel) already carries the missed count — no extra request.
  const dash = useDashboard();

  useEffect(() => setMoreOpen(false), [location.pathname]);
  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem("dw:sidebar", c ? "expanded" : "collapsed");
      } catch { /* storage unavailable — keep in memory */ }
      return !c;
    });
  };
  const missedCount = prefs.missed_policy === "show" ? (dash.data?.reminders.missed ?? 0) : 0;

  return (
    <div className="min-h-dvh lg:flex">
      <a href="#main" className="sr-only-focusable fixed top-2 left-2 z-[90] rounded-lg bg-primary px-3 py-2 text-on-primary">Skip to content</a>

      {/* Desktop sidebar */}
      <aside className={clsx("sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-surface lg:flex", collapsed ? "w-[4.5rem]" : "w-60")}>
        <div className={clsx("flex items-center gap-2 px-4 py-5", collapsed && "justify-center px-0")}>
          <img src="/icons/icon-192.png" alt="" className="h-8 w-8 rounded-lg" />
          {!collapsed && <span className="font-[family-name:var(--font-display)] text-xl font-semibold text-primary-strong">DayWell</span>}
        </div>
        <button onClick={openQuickAdd} className={clsx("mx-3 mb-3 flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-primary px-3 font-medium text-on-primary hover:bg-primary-strong", collapsed && "justify-center")}
          aria-label="Quick add" title="Quick add (N)">
          <Plus className="h-5 w-5" aria-hidden />
          {!collapsed && "Quick add"}
        </button>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5 px-2">
          {NAV.map((item) => <SideLink key={item.to} item={item} collapsed={collapsed} />)}
          <SideLink item={{ to: "/notifications", label: "Notifications", icon: Bell }} collapsed={collapsed} badge={unread.data?.count} />
        </nav>
        <button onClick={() => void signOut()} aria-label={`Log out of ${user.display_name || user.email}`} title={collapsed ? "Log out" : undefined}
          className={clsx("mx-2 mt-2 flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted hover:bg-sage-soft hover:text-ink", collapsed && "justify-center px-0")}>
          <LogOut className="h-5 w-5 shrink-0" aria-hidden />
          {!collapsed && "Log out"}
        </button>
        <button onClick={toggle} className="m-3 mt-1 flex items-center justify-center gap-2 rounded-lg p-2 text-sm text-muted hover:bg-sage-soft" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <ChevronsRight className="h-4 w-4" aria-hidden /> : <><ChevronsLeft className="h-4 w-4" aria-hidden /> Collapse</>}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-bg/95 px-4 py-2.5 backdrop-blur lg:hidden">
          <Link to="/" className="flex shrink-0 items-center gap-2">
            <img src="/icons/icon-192.png" alt="" className="h-7 w-7 rounded-lg" />
            <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-primary-strong">DayWell</span>
          </Link>
          <div className="flex items-center gap-1">
            <TrialBadge />
            <Link to="/notifications" className="relative rounded-full p-2 hover:bg-sage-soft" aria-label={`Notifications${unread.data?.count ? `, ${unread.data.count} unread` : ""}`}>
              <Bell className="h-5 w-5" aria-hidden />
              {!!unread.data?.count && <span className="absolute top-1 right-1 h-2.5 w-2.5 rounded-full bg-terracotta" aria-hidden />}
            </Link>
          </div>
        </header>
        {/* Desktop: the same badge in the top-right corner (its own row, so it never covers banners or page content) */}
        <TrialBadge placement="desktop" />

        {!online && (
          <div role="status" className="flex items-center gap-2 bg-amber-soft px-4 py-2 text-sm">
            <CloudOff className="h-4 w-4" aria-hidden /> You're offline. You can browse what's loaded; changes need a connection. In-app alarms can't be checked until you reconnect.
          </div>
        )}
        <BillingBanner />
        <PushNudge />
        {missedCount > 0 && location.pathname !== "/notifications" && (
          <Link to="/notifications?tab=missed" className="flex items-center gap-2 bg-terracotta-soft px-4 py-2 text-sm hover:underline">
            <TriangleAlert className="h-4 w-4" aria-hidden /> {missedCount} reminder{missedCount === 1 ? "" : "s"} need{missedCount === 1 ? "s" : ""} your attention. Review them →
          </Link>
        )}

        <div className="flex flex-1">
          <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 pt-5 pb-28 outline-none sm:px-6 lg:pb-10">
            <Outlet />
          </main>
          <UpNextPanel />
        </div>
      </div>

      {/* Mobile floating quick add */}
      <button onClick={openQuickAdd} aria-label="Quick add"
        className="fixed right-4 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-30 grid h-14 w-14 place-items-center rounded-full bg-primary text-on-primary shadow-lg lg:hidden">
        <Plus className="h-6 w-6" aria-hidden />
      </button>

      {/* Mobile bottom navigation */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
        {MOBILE_PRIMARY.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}
            className={({ isActive }) => clsx("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[0.7rem] font-medium", isActive ? "text-primary" : "text-muted")}>
            <item.icon className="h-5 w-5" aria-hidden />
            {item.label}
          </NavLink>
        ))}
        <button onClick={() => setMoreOpen(true)} className="flex min-h-14 flex-col items-center justify-center gap-0.5 text-[0.7rem] font-medium text-muted" aria-haspopup="dialog">
          <Ellipsis className="h-5 w-5" aria-hidden />
          More
        </button>
      </nav>
      <Dialog open={moreOpen} onOpenChange={setMoreOpen} title="More" size="sm">
        <nav className="grid grid-cols-2 gap-2" aria-label="More sections">
          {[...NAV.slice(4), { to: "/notifications", label: "Notifications", icon: Bell }, { to: "/reminders", label: "Reminders", icon: Bell }].map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => clsx("flex items-center gap-2 rounded-xl border border-line p-3 text-sm font-medium", isActive && "border-primary bg-sage-soft")}>
              <item.icon className="h-5 w-5 text-primary" aria-hidden /> {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 border-t border-line pt-3">
          <p className="mb-2 truncate text-sm text-muted">Signed in as {user.display_name || user.email}</p>
          <button onClick={() => { setMoreOpen(false); void signOut(); }}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-line p-3 text-sm font-medium hover:bg-sage-soft">
            <LogOut className="h-5 w-5" aria-hidden /> Log out
          </button>
        </div>
      </Dialog>
    </div>
  );
}

function SideLink({ item, collapsed, badge }: { item: NavItem; collapsed: boolean; badge?: number }): ReactNode {
  return (
    <NavLink to={item.to} end={item.end} title={collapsed ? item.label : undefined}
      className={({ isActive }) => clsx(
        "relative flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
        collapsed && "justify-center px-0",
        isActive ? "bg-sage-soft text-primary-strong" : "text-muted hover:bg-sage-soft hover:text-ink",
      )}>
      <item.icon className="h-5 w-5 shrink-0" aria-hidden />
      {collapsed ? <span className="sr-only">{item.label}</span> : item.label}
      {!!badge && <span className={clsx("ml-auto rounded-full bg-terracotta px-1.5 text-xs text-on-primary", collapsed && "absolute top-1 right-1")}><span className="sr-only">, unread: </span>{badge}</span>}
    </NavLink>
  );
}

/** Trial ending soon or read-only mode: one calm line linking to Plan & billing (hidden on that page itself). */
function BillingBanner() {
  const billing = useBilling();
  const location = useLocation();
  const data = billing.data;
  if (!data || location.pathname.startsWith("/settings/billing")) return null;
  const left = daysUntil(data.trial_ends_at);
  if (data.state === "read_only") {
    return (
      <Link to="/settings/billing" className="flex items-center gap-2 bg-amber-soft px-4 py-2 text-sm hover:underline">
        <Lock className="h-4 w-4" aria-hidden /> Your free trial has ended, so DayWell is read-only. Your data is safe — subscribe to keep planning →
      </Link>
    );
  }
  if (data.state === "trial" && left <= 3) {
    return (
      <Link to="/settings/billing" className="flex items-center gap-2 bg-sage-soft px-4 py-2 text-sm hover:underline">
        <Sparkles className="h-4 w-4" aria-hidden /> {left === 0 ? "Your free trial ends today." : `${left} day${left === 1 ? "" : "s"} left in your free trial.`} Choose a plan to keep everything unlocked →
      </Link>
    );
  }
  return null;
}

/** Small "Trial · N days" countdown pill shown only during the free trial; links to Plan & billing. */
function TrialBadge({ placement = "mobile" }: { placement?: "mobile" | "desktop" }) {
  const billing = useBilling();
  if (billing.data?.state !== "trial") return null;
  const left = daysUntil(billing.data.trial_ends_at);
  const badge = (
    <Link to="/settings/billing" aria-label={`Free trial: ${left === 0 ? "ends today" : `${left} day${left === 1 ? "" : "s"} left`}. View plans`}
      className={clsx("inline-flex min-h-8 items-center gap-1 rounded-full border px-2.5 text-xs font-semibold whitespace-nowrap hover:opacity-90",
        left <= 3 ? "border-terracotta bg-terracotta-soft text-ink" : "border-line bg-surface text-primary-strong")}>
      <Sparkles className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span aria-hidden><span className="hidden min-[400px]:inline lg:inline">Trial · </span>{left === 0 ? "ends today" : <>{left}<span className="hidden min-[400px]:inline lg:inline"> day{left === 1 ? "" : "s"}</span><span className="min-[400px]:hidden lg:hidden">d</span></>}</span>
    </Link>
  );
  return placement === "desktop" ? <div className="hidden justify-end px-4 pt-3 lg:flex">{badge}</div> : badge;
}
