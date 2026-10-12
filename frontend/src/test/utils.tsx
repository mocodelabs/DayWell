import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "@/components/ui/Toast";
import { SessionProvider } from "@/features/auth/session";
import type { Preferences, User } from "@/lib/types";

export const testUser: User = { id: 1, email: "ada@example.com", display_name: "Ada", email_verified: true, date_joined: "2026-10-01T00:00:00Z" };

export const testPrefs: Preferences = {
  time_zone: "Africa/Nairobi", locale: "en", date_format: "DMY", time_format: "24h", week_start: 0, theme: "light", reduced_motion: false, text_scale: "1.00",
  onboarding_completed: true, onboarding_completed_at: "2026-10-01T00:00:00Z", focus_areas: [],
  modules: { affirmations: true, reading: true, fitness: false, hydration: true, sleep: false, journal: false, goals: false, mindfulness: false, admin: false },
  dashboard_layout: [], greeting_enabled: true, tone: "warm", briefing_style: "short", greeting_time: "07:00:00", morning_notification: false,
  evening_summary: true, evening_time: "20:00:00", wake_time: "06:30:00", bedtime: "22:30:00", work_start: "09:00:00", work_end: "17:00:00",
  work_days: [0, 1, 2, 3, 4], planning_buffer_minutes: 10, hydration_target: 2000, hydration_unit: "ml", glass_size_ml: 250, reading_yearly_goal: 0,
  weekly_workout_goal: 0, affirmation_categories: [], default_sound: "chime", alarm_volume: 80, quiet_enabled: false, quiet_start: "22:00:00",
  quiet_end: "07:00:00", quiet_days: [0, 1, 2, 3, 4, 5, 6], quiet_behavior: "delay", missed_policy: "show", ai_suggestions_enabled: false,
  journal_ai_consent: false, updated_at: "2026-10-01T00:00:00Z",
};

type Handler = (url: string, init?: RequestInit) => unknown | Promise<unknown>;

/** Mock fetch with a route table: { "GET /api/v1/tasks/": body | (url, init) => body }. Unmatched requests fail the test. */
export function mockApi(routes: Record<string, unknown | Handler>) {
  const calls: { method: string; url: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.split("?")[0];
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = Object.keys(routes).find((k) => k === `${method} ${path}` || k === `${method} ${url}`);
    if (!key) throw new Error(`Unmocked request: ${method} ${url}`);
    const entry = routes[key];
    let body = typeof entry === "function" ? await (entry as Handler)(url, init) : entry;
    let status = 200;
    if (body && typeof body === "object" && "__status" in (body as Record<string, unknown>)) {
      status = (body as { __status: number }).__status;
      body = (body as { body: unknown }).body;
    }
    return new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "daywell_csrftoken=test-csrf";
  return { fetchMock, calls };
}

export function renderApp(ui: ReactElement, { route = "/", prefs = testPrefs }: { route?: string; prefs?: Preferences } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          <SessionProvider value={{ user: testUser, prefs }}>{ui}</SessionProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
