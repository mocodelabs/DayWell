import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Billing as BillingData } from "@/features/billing/billing";
import Billing from "@/pages/settings/Billing";
import { mockApi, renderApp, testPrefs } from "./utils";

const plans: BillingData["plans"] = [
  { code: "monthly-kes", name: "Monthly (KES)", interval: "monthly", currency: "KES", amount_minor: 34_900, auto_renew_available: true, mpesa_available: true },
  { code: "annual-kes", name: "Annual (KES)", interval: "annually", currency: "KES", amount_minor: 349_000, auto_renew_available: true, mpesa_available: true },
  { code: "monthly-usd", name: "Monthly (USD)", interval: "monthly", currency: "USD", amount_minor: 499, auto_renew_available: true, mpesa_available: false },
  { code: "annual-usd", name: "Annual (USD)", interval: "annually", currency: "USD", amount_minor: 3_999, auto_renew_available: false, mpesa_available: false },
];

function billing(over: Partial<BillingData> = {}): BillingData {
  const inFiveDays = new Date(Date.now() + 5 * 86_400_000).toISOString();
  return { state: "trial", has_premium: true, trial_ends_at: inFiveDays, paid_until: null, renewal: "none", plan: null, payments_enabled: true, price_label: "Early-adopter price", plans, payments: [], ...over };
}

afterEach(() => vi.unstubAllGlobals());

describe("Plan & billing", () => {
  it("shows the trial and defaults Nairobi users to KES with M-Pesa", async () => {
    mockApi({ "GET /api/v1/billing/": billing() });
    renderApp(<Billing />, { route: "/settings/billing" });
    expect(await screen.findByText(/5 days left/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Annual/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText(/M-Pesa or card/)).toBeInTheDocument();
    expect(screen.getByText(/Save 17%/)).toBeInTheDocument(); // KES 3,490 vs 12 × 349
    expect(screen.getByText("Early-adopter price")).toBeInTheDocument();
    expect(screen.getByText(/all Premium features/)).toBeInTheDocument();
  });

  it("starts Paystack checkout for the chosen plan and payment method", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const { calls } = mockApi({
      "GET /api/v1/billing/": billing(),
      "POST /api/v1/billing/checkout/": { authorization_url: "https://checkout.paystack.com/x", reference: "dw_1" },
    });
    renderApp(<Billing />, { route: "/settings/billing" });
    await userEvent.click(await screen.findByRole("radio", { name: /Monthly/ }));
    await userEvent.click(screen.getByLabelText(/Renew automatically/));
    await userEvent.click(screen.getByRole("button", { name: /Continue to payment/ }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://checkout.paystack.com/x"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ plan: "monthly-kes", auto_renew: true });
  });

  it("USD offers card only and disables auto-renew when the plan isn't synced", async () => {
    mockApi({ "GET /api/v1/billing/": billing() });
    renderApp(<Billing />, { route: "/settings/billing", prefs: { ...testPrefs, time_zone: "Europe/London" } });
    expect(await screen.findByText(/Card\. Covers one period/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Renew automatically/)).toBeDisabled(); // annual-usd has no Paystack plan yet
  });

  it("confirms a returning payment with the server, not the redirect", async () => {
    const { calls } = mockApi({
      "GET /api/v1/billing/": billing(),
      "POST /api/v1/billing/verify/": {
        payment: { reference: "dw_9", plan: "annual-kes", kind: "checkout", auto_renew: false, amount_minor: 349_000, currency: "KES", status: "success", channel: "mobile_money", period_start: null, period_end: null, paid_at: new Date().toISOString(), created_at: new Date().toISOString() },
        billing: billing({ state: "active", paid_until: new Date(Date.now() + 365 * 86_400_000).toISOString(), plan: "annual-kes" }),
      },
    });
    renderApp(<Billing />, { route: "/settings/billing?trxref=dw_9&reference=dw_9" });
    expect(await screen.findByText("Payment received")).toBeInTheDocument();
    expect(await screen.findByText(/paid until/)).toBeInTheDocument();
    expect(calls.filter((c) => c.url.includes("/billing/verify/"))).toHaveLength(1);
  });

  it("explains read-only mode", async () => {
    mockApi({ "GET /api/v1/billing/": billing({ state: "read_only", has_premium: false, trial_ends_at: "2026-01-01T00:00:00Z" }) });
    renderApp(<Billing />, { route: "/settings/billing" });
    expect(await screen.findByText(/read-only/, { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/Everything you saved is still here/)).toBeInTheDocument();
  });
});
