import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, setUnauthorizedHandler } from "@/lib/api";
import type { Me, Preferences, User } from "@/lib/types";
import { keys, useMe } from "@/hooks/queries";

interface Session {
  user: User;
  prefs: Preferences;
}

const SessionCtx = createContext<Session | null>(null);

/** Provide a session directly (used by tests and storybook-style previews). */
export function SessionProvider({ value, children }: { value: Session; children: ReactNode }) {
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession used outside an authenticated route");
  return s;
}

/** Applies theme, reduced motion and text scale from preferences to <html>. */
function useAppearance(prefs: Preferences | undefined) {
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const dark = prefs?.theme === "dark" || (prefs?.theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
      root.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    root.classList.toggle("dw-reduce-motion", !!prefs?.reduced_motion);
    root.style.setProperty("--dw-text-scale", String(prefs?.text_scale ?? 1));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [prefs?.theme, prefs?.reduced_motion, prefs?.text_scale]);
}

export function RequireAuth({ children, allowOnboarding = false }: { children: ReactNode; allowOnboarding?: boolean }) {
  const me = useMe();
  const qc = useQueryClient();
  const location = useLocation();
  useAppearance(me.data?.preferences);

  useEffect(() => {
    setUnauthorizedHandler(() => qc.setQueryData(keys.me, null));
  }, [qc]);

  if (me.isPending) {
    return (
      <div className="grid min-h-dvh place-items-center" role="status" aria-live="polite">
        <p className="text-muted">Getting your day ready…</p>
      </div>
    );
  }
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) {
    return (
      <div className="grid min-h-dvh place-items-center p-6 text-center" role="alert">
        <div>
          <p className="font-medium">We couldn't reach DayWell.</p>
          <p className="mt-1 text-sm text-muted">{me.error.message}</p>
          <button className="mt-4 rounded-lg bg-primary px-4 py-2 text-on-primary" onClick={() => me.refetch()}>Try again</button>
        </div>
      </div>
    );
  }
  const data = me.data as Me | null | undefined;
  if (!data) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (!data.preferences.onboarding_completed && !allowOnboarding) return <Navigate to="/welcome" replace />;
  return <SessionCtx.Provider value={{ user: data.user, prefs: data.preferences }}>{children}</SessionCtx.Provider>;
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const me = useMe();
  useAppearance(undefined);
  if (me.isPending) return null;
  if (me.data) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Signs out on the server, drops every cached query (no data from this account lingers), and goes to sign-in. */
export function useSignOut() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return async () => {
    await api.post("/auth/logout/").catch(() => undefined); // even if the request fails, leave the device signed out locally
    qc.clear();
    qc.setQueryData(keys.me, null);
    navigate("/login", { replace: true });
  };
}
