import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { HabitQuickCheck } from "@/components/HabitQuickCheck";
import { QuickAddDialog } from "@/components/QuickAddDialog";
import { TaskForm } from "@/components/TaskForm";
import { TaskItem } from "@/components/TaskItem";
import { AlarmDialog } from "@/features/alarms/AlarmDialog";
import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import Today from "@/pages/Today";
import type { AlarmOccurrence, Dashboard } from "@/lib/types";
import { mockApi, renderApp, testPrefs } from "./utils";

describe("Login & registration", () => {
  it("validates before calling the server", async () => {
    const { fetchMock } = mockApi({});
    renderApp(<Login />, { route: "/login" });
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's message for wrong credentials", async () => {
    mockApi({
      "POST /api/v1/auth/login/": { __status: 400, body: { error: { code: "validation_error", message: "That email and password don't match.", fields: { non_field_errors: ["That email and password don't match."] } } } },
    });
    renderApp(<Login />, { route: "/login" });
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That email and password don't match.");
  });

  it("maps field errors from registration onto inputs", async () => {
    mockApi({
      "POST /api/v1/auth/register/": { __status: 400, body: { error: { code: "validation_error", message: "", fields: { email: ["An account with this email already exists."] } } } },
    });
    renderApp(<Register />, { route: "/register" });
    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("An account with this email already exists.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("Tasks", () => {
  it("completes a task with an accessible toggle", async () => {
    const { calls } = mockApi({ "POST /api/v1/tasks/7/complete/": { id: 7, status: "completed" } });
    renderApp(<TaskItem task={{ id: 7, title: "Write report", priority: "high", status: "pending", scheduled_date: "2026-10-09", scheduled_time: "10:00", is_overdue: false, is_recurring: false }} />);
    await userEvent.click(screen.getByRole("button", { name: "Mark “Write report” as done" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/tasks/7/complete/"))).toBe(true));
    expect(await screen.findByText("Completed")).toBeInTheDocument();
  });

  it("quick add shows its interpretation and saves exactly that", async () => {
    const { calls } = mockApi({ "POST /api/v1/tasks/": { id: 1 } });
    renderApp(<QuickAddDialog open onOpenChange={() => undefined} onOpenFull={() => undefined} />);
    await userEvent.type(screen.getByLabelText("What do you need to do?"), "Call the supplier tomorrow at 10 am and remind me 15 minutes before");
    const preview = screen.getByText("Here's what we understood").closest("div")!;
    expect(within(preview).getByText(/Reminder: 15 min before/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add task" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")).toBeTruthy());
    const body = calls.find((c) => c.method === "POST")!.body as Record<string, unknown>;
    expect(body).toMatchObject({ title: "Call the supplier", scheduled_time: "10:00", reminders: [{ offset_minutes: 15, anchor: "start" }] });
    expect(String(body.scheduled_date)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("task form requires a date when a time is given", async () => {
    const { fetchMock } = mockApi({ "GET /api/v1/categories/": [] });
    renderApp(<TaskForm open onOpenChange={() => undefined} />);
    await userEvent.type(screen.getByLabelText("Title"), "Dentist");
    await userEvent.type(screen.getByLabelText(/^Time/), "10:00");
    await userEvent.click(screen.getByRole("button", { name: "Add task" }));
    expect(await screen.findByText("Pick a date for this time.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(false);
  });
});

const alarm: AlarmOccurrence = {
  id: 9, reminder: 1, reminder_title: "Meds", title: "Take medication", body: "Time for: Take medication.", category: "custom", status: "sent", status_label: "Sent",
  skip_reason: "", last_error: "", silent: false, scheduled_for: "2026-10-09T06:00:00Z", fire_at: "2026-10-09T06:00:00Z", sent_at: "2026-10-09T06:00:01Z",
  delivered_at: null, audio_status: "", audio_played_at: null, acted_at: null, dismissed_at: null, completed_at: null, snoozed_until: null, read_at: null,
  escalations: 0, snooze_count: 0, parent: null, target_key: "task:3", task: 3, sound: "bell", snooze_minutes: 10, linked: { type: "task", id: 3 },
  can_complete: true, deliveries: [],
};

describe("Alarm dialog", () => {
  it("offers snooze, done and dismiss-without-completing", async () => {
    const onSnooze = vi.fn();
    const onComplete = vi.fn();
    const onDismiss = vi.fn();
    renderApp(<AlarmDialog alarm={alarm} queued={0} audioBlocked={false} onEnableSound={vi.fn()} onSnooze={onSnooze} onDismiss={onDismiss} onComplete={onComplete} onStopSound={vi.fn()} />);
    expect(screen.getByRole("alertdialog")).toHaveAccessibleName("Take medication");
    await userEvent.click(screen.getByRole("button", { name: "Snooze 10 min" }));
    expect(onSnooze).toHaveBeenCalledWith();
    await userEvent.click(screen.getByRole("button", { name: "Mark done" }));
    expect(onComplete).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss without completing" }));
    expect(onDismiss).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Snooze for…" }));
    await userEvent.click(screen.getByRole("button", { name: "30 min" }));
    expect(onSnooze).toHaveBeenLastCalledWith(30);
  });

  it("says plainly when the browser blocked the sound, and lets the user enable it", async () => {
    const onEnable = vi.fn();
    renderApp(<AlarmDialog alarm={alarm} queued={2} audioBlocked onEnableSound={onEnable} onSnooze={vi.fn()} onDismiss={vi.fn()} onComplete={vi.fn()} onStopSound={vi.fn()} />);
    expect(screen.getByText("Your browser blocked the alarm sound.")).toBeInTheDocument();
    expect(screen.getByText("2 more waiting")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Play sound" }));
    expect(onEnable).toHaveBeenCalled();
  });

  it("Escape snoozes rather than silently dismissing", async () => {
    const onSnooze = vi.fn();
    renderApp(<AlarmDialog alarm={alarm} queued={0} audioBlocked={false} onEnableSound={vi.fn()} onSnooze={onSnooze} onDismiss={vi.fn()} onComplete={vi.fn()} onStopSound={vi.fn()} />);
    await userEvent.keyboard("{Escape}");
    expect(onSnooze).toHaveBeenCalled();
  });
});

const dashboard: Dashboard = {
  generated_at: "2026-10-09T05:00:00Z",
  local: { date: "2026-10-09", time: "08:00", iso: "2026-10-09T08:00:00+03:00", time_zone: "Africa/Nairobi", weekday: "Friday" },
  greeting: { headline: "Good morning, Ada!", message: "A new day is here.", part_of_day: "morning" },
  briefing: { style: "short", schedule: "You have 1 planned activity today, and next up is Standup at 09:00.", getting_started: "A good place to start: “Ship”.", conflicts: "", overdue: "" },
  agenda: [{ type: "event", id: 1, key: "2026-10-09T09:00", title: "Standup", start: "2026-10-09T06:00:00Z", end: "2026-10-09T06:15:00Z", all_day: false }],
  next_up: { type: "event", id: 1, key: "2026-10-09T09:00", title: "Standup", start: "2026-10-09T06:00:00Z", end: "2026-10-09T06:15:00Z", all_day: false },
  tasks_today: [], priorities: [{ id: 5, title: "Ship", priority: "urgent", status: "pending", scheduled_date: "2026-10-09", scheduled_time: null, scheduled_at: null, deadline: null, duration_minutes: null, category: null, is_overdue: false, is_recurring: false }],
  overdue: { count: 0, items: [] },
  habits: { items: [{ id: 2, name: "Stretch", icon: "", color: "", target_type: "binary", target_value: "1", unit: "", value: "0", status: null, times_per_week: null }], done: 0, total: 1 },
  reminders: { upcoming: [], active: 0, missed: 2 },
  progress: { tasks_done: 0, tasks_total: 1, habits_done: 0, habits_total: 1, events_total: 1, events_attended: 0, overall: 0 },
  conflicts: [],
  modules: testPrefs.modules,
  layout: [{ key: "briefing", visible: true }, { key: "agenda", visible: true }, { key: "priorities", visible: true }, { key: "habits", visible: true }, { key: "reminders", visible: true }, { key: "affirmation", visible: false }],
  evening: null,
  affirmation: { id: 1, text: "One step at a time.", category: "focus", acknowledged: false },
};

describe("Today dashboard", () => {
  it("shows a loading state, then the real briefing", async () => {
    mockApi({ "GET /api/v1/dashboard/today/": dashboard });
    renderApp(<Today />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading your day/);
    expect(await screen.findByRole("heading", { name: "Good morning, Ada!" })).toBeInTheDocument();
    expect(screen.getByText(/next up is Standup at 09:00/)).toBeInTheDocument();
    expect(screen.getByText(/Up next ·/)).toBeInTheDocument();
    expect(screen.getByText(/2 missed reminders to review/)).toBeInTheDocument();
    expect(screen.queryByText("One step at a time.")).not.toBeInTheDocument(); // hidden by layout
  });

  it("shows a recoverable error when the briefing fails", async () => {
    mockApi({ "GET /api/v1/dashboard/today/": { __status: 500, body: { error: { code: "server_error", message: "Something went wrong on our side. Please try again.", fields: {} } } } });
    renderApp(<Today />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("explains offline clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderApp(<Today />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach DayWell|offline/i);
  });
});

describe("Habits", () => {
  it("toggles a binary habit with aria-pressed", async () => {
    const { calls } = mockApi({ "POST /api/v1/habits/2/complete/": {} });
    renderApp(<HabitQuickCheck habit={dashboard.habits.items[0]} />);
    const btn = screen.getByRole("button", { name: /Stretch/ });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/habits/2/complete/"))).toBe(true));
  });

  it("increments counted habits", async () => {
    const { calls } = mockApi({ "POST /api/v1/habits/4/increment/": {} });
    renderApp(<HabitQuickCheck habit={{ ...dashboard.habits.items[0], id: 4, name: "Water", target_type: "count", target_value: "8", unit: "glasses", value: "3" }} />);
    expect(screen.getByText("3 / 8 glasses")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add one to Water" }));
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/increment/"))?.body).toMatchObject({ amount: 1 }));
  });
});

describe("Navigation & notification permission", () => {
  it("mobile bottom navigation exposes the main sections", async () => {
    const { AppShell } = await import("@/components/layout/AppShell");
    const { QuickAddProvider } = await import("@/components/layout/QuickAddContext");
    mockApi({
      "GET /api/v1/dashboard/today/": dashboard, "GET /api/v1/notifications/unread-count/": { count: 3 }, "GET /api/v1/categories/": [],
    });
    renderApp(<Routes><Route element={<QuickAddProvider><AppShell /></QuickAddProvider>}><Route index element={<p>home</p>} /></Route></Routes>);
    const navs = screen.getAllByRole("navigation", { name: "Main" });
    expect(navs.length).toBe(2); // sidebar + bottom bar
    const bottom = navs[1];
    for (const name of ["Today", "Calendar", "Tasks", "Habits", "More"]) expect(within(bottom).getByText(name)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Notifications, 3 unread" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
  });

  it("logs out from the More menu: server sign-out, then back to sign-in", async () => {
    const { AppShell } = await import("@/components/layout/AppShell");
    const { QuickAddProvider } = await import("@/components/layout/QuickAddContext");
    const { calls } = mockApi({
      "GET /api/v1/dashboard/today/": dashboard, "GET /api/v1/notifications/unread-count/": { count: 0 }, "GET /api/v1/categories/": [],
      "POST /api/v1/auth/logout/": undefined,
    });
    renderApp(
      <Routes>
        <Route element={<QuickAddProvider><AppShell /></QuickAddProvider>}><Route index element={<p>home</p>} /></Route>
        <Route path="/login" element={<p>sign-in page</p>} />
      </Routes>,
    );
    await userEvent.click(screen.getByRole("button", { name: "More" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Signed in as Ada/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Log out" }));
    expect(await screen.findByText("sign-in page")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/auth/logout/"))).toBe(true);
  });

  it("reports denied notification permission honestly", async () => {
    vi.stubGlobal("Notification", Object.assign(function Notification() {}, { permission: "denied", requestPermission: vi.fn() }));
    const { pushSupport, subscribeToPush } = await import("@/lib/push");
    expect(pushSupport().permission).toBe("denied");
    const res = await subscribeToPush("test");
    expect(res.ok).toBe(false);
    vi.unstubAllGlobals();
  });
});

describe("Dialog focus management (WCAG 2.4.3)", () => {
  it("returns focus to the element that opened a programmatic dialog", async () => {
    const { useState } = await import("react");
    const { Dialog } = await import("@/components/ui/Dialog");
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open it</button>
          <Dialog open={open} onOpenChange={setOpen} title="Example"><input aria-label="Field" autoFocus /></Dialog>
        </>
      );
    }
    renderApp(<Harness />);
    const opener = screen.getByRole("button", { name: "Open it" });
    opener.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByLabelText("Field")).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(opener).toHaveFocus());
  });
});
