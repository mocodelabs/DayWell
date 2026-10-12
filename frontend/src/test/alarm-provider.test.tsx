import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AlarmProvider } from "@/features/alarms/AlarmProvider";
import { alarmAudio } from "@/lib/audio";
import type { AlarmOccurrence } from "@/lib/types";
import { mockApi, renderApp } from "./utils";

const occ: AlarmOccurrence = {
  id: 9, reminder: 1, reminder_title: "Meds", title: "Take medication", body: "It's time.", category: "custom", status: "sent", status_label: "Sent",
  skip_reason: "", last_error: "", silent: false, scheduled_for: new Date().toISOString(), fire_at: new Date().toISOString(), sent_at: null, delivered_at: null,
  audio_status: "", audio_played_at: null, acted_at: null, dismissed_at: null, completed_at: null, snoozed_until: null, read_at: null, escalations: 0,
  snooze_count: 0, parent: null, target_key: "", task: null, sound: "bell", snooze_minutes: 10, linked: null, can_complete: false, deliveries: [],
};

function fakeAudio(play: () => Promise<void>) {
  class FakeAudio {
    loop = false; volume = 1; paused = true; currentTime = 0; src: string;
    constructor(src: string) { this.src = src; }
    play() { this.paused = false; return play(); }
    pause() { this.paused = true; }
  }
  vi.stubGlobal("Audio", FakeAudio);
}

describe("AlarmProvider (regression: honest audio + single snooze)", () => {
  beforeEach(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  });
  afterEach(() => {
    alarmAudio.stop();
    vi.unstubAllGlobals();
  });

  it("reports blocked audio, never 'played', and snoozes exactly once", async () => {
    fakeAudio(() => Promise.reject(new DOMException("autoplay blocked", "NotAllowedError")));
    let active: AlarmOccurrence[] = [occ];
    const { calls } = mockApi({
      "GET /api/v1/alarms/active/": () => active,
      "GET /api/v1/alarms/upcoming/": [],
      "POST /api/v1/alarms/9/shown/": occ,
      "POST /api/v1/alarms/9/snooze/": () => {
        active = [];
        return { snoozed_until: new Date(Date.now() + 600_000).toISOString(), next_occurrence: 10 };
      },
    });
    renderApp(<AlarmProvider><p>app</p></AlarmProvider>);
    expect(await screen.findByRole("alertdialog", { name: "Take medication" })).toBeInTheDocument();
    expect(await screen.findByText("Your browser blocked the alarm sound.")).toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/alarms/9/shown/"))).toHaveLength(1));
    expect(calls.find((c) => c.url.endsWith("/alarms/9/shown/"))!.body).toEqual({ audio: "blocked" });

    await userEvent.click(screen.getByRole("button", { name: "Snooze 10 min" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(calls.filter((c) => c.url.endsWith("/alarms/9/snooze/"))).toHaveLength(1);
    expect(calls.some((c) => (c.body as { audio?: string } | undefined)?.audio === "played")).toBe(false);
  });

  it("reports 'played' only when playback actually started", async () => {
    fakeAudio(() => Promise.resolve());
    const { calls } = mockApi({
      "GET /api/v1/alarms/active/": [occ],
      "GET /api/v1/alarms/upcoming/": [],
      "POST /api/v1/alarms/9/shown/": occ,
    });
    renderApp(<AlarmProvider><p>app</p></AlarmProvider>);
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/alarms/9/shown/"))?.body).toEqual({ audio: "played" }));
    expect(screen.queryByText("Your browser blocked the alarm sound.")).not.toBeInTheDocument();
  });

  it("silent (quiet-hours) alarms never try to play sound", async () => {
    const play = vi.fn(() => Promise.resolve());
    fakeAudio(play);
    const { calls } = mockApi({
      "GET /api/v1/alarms/active/": [{ ...occ, silent: true }],
      "GET /api/v1/alarms/upcoming/": [],
      "POST /api/v1/alarms/9/shown/": occ,
    });
    renderApp(<AlarmProvider><p>app</p></AlarmProvider>);
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/alarms/9/shown/"))?.body).toEqual({ audio: "muted" }));
    expect(play).not.toHaveBeenCalled();
  });
});

describe("push subscription re-sync", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  function stubPush(existing: { endpoint: string } | null) {
    const subscribe = vi.fn(async () => ({ toJSON: () => ({ endpoint: "https://push.example/new", keys: { p256dh: "p", auth: "a" } }) }));
    const reg = { pushManager: { getSubscription: async () => (existing ? { toJSON: () => ({ ...existing, keys: { p256dh: "p", auth: "a" } }) } : null), subscribe } };
    vi.stubGlobal("Notification", Object.assign(function N() {}, { permission: "granted", requestPermission: async () => "granted" }));
    vi.stubGlobal("PushManager", function PM() {});
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration: async () => reg, ready: Promise.resolve(reg), register: async () => reg, addEventListener() {}, removeEventListener() {} } });
    return subscribe;
  }

  it("does nothing unless this device opted in", async () => {
    stubPush(null);
    const { calls } = mockApi({});
    const { syncPushSubscription } = await import("@/lib/push");
    expect(await syncPushSubscription()).toBe("skipped");
    expect(calls).toHaveLength(0);
  });

  it("re-sends an existing subscription and re-subscribes when the browser dropped it", async () => {
    localStorage.setItem("dw:push-opt-in", "1");
    stubPush({ endpoint: "https://push.example/abc" });
    const { calls } = mockApi({ "POST /api/v1/push/subscriptions/": { id: 1, active: true }, "GET /api/v1/push/config/": { configured: true, public_key: "BAAA" } });
    const { syncPushSubscription } = await import("@/lib/push");
    expect(await syncPushSubscription()).toBe("synced");
    expect(calls[0].body).toMatchObject({ endpoint: "https://push.example/abc" });
    const subscribe = stubPush(null);
    expect(await syncPushSubscription()).toBe("resubscribed");
    expect(subscribe).toHaveBeenCalledOnce();
  });
});
