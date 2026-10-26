import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PushNudge } from "@/components/layout/PushNudge";
import { mockApi, renderApp } from "./utils";

function device({ touch, subscribed, permission = "default" }: { touch: boolean; subscribed: boolean; permission?: string }) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("coarse") ? touch : false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("Notification", Object.assign(function Notification() {}, { permission, requestPermission: vi.fn() }));
  vi.stubGlobal("PushManager", function PushManager() {});
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { getRegistration: async () => ({ pushManager: { getSubscription: async () => (subscribed ? { endpoint: "e" } : null) } }) },
  });
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("Push nudge on phones", () => {
  it("tells an unsubscribed phone that alarms won't ring while closed", async () => {
    device({ touch: true, subscribed: false });
    mockApi({ "GET /api/v1/push/config/": { configured: true, public_key: "BAAA" } });
    renderApp(<PushNudge />);
    const link = await screen.findByRole("link", { name: /Alarms won't ring on this device/ });
    expect(link).toHaveAttribute("href", "/settings/notifications");
  });

  it("stays hidden once the device is subscribed, on desktop, or when blocked", async () => {
    for (const d of [{ touch: true, subscribed: true }, { touch: false, subscribed: false }, { touch: true, subscribed: false, permission: "denied" }]) {
      device(d);
      mockApi({ "GET /api/v1/push/config/": { configured: true, public_key: "BAAA" } });
      const { unmount } = renderApp(<PushNudge />);
      await new Promise((r) => setTimeout(r, 20));
      expect(screen.queryByText(/Alarms won't ring/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("can be dismissed for a week", async () => {
    device({ touch: true, subscribed: false });
    mockApi({ "GET /api/v1/push/config/": { configured: true, public_key: "BAAA" } });
    renderApp(<PushNudge />);
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss for a week" }));
    await waitFor(() => expect(screen.queryByText(/Alarms won't ring/)).not.toBeInTheDocument());
    expect(Number(localStorage.getItem("dw:push-nudge-dismissed-at"))).toBeGreaterThan(0);
  });
});
