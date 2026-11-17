import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Landing from "@/pages/Landing";
import { mockApi, renderApp } from "./utils";

const plans = [
  { code: "monthly-kes", name: "Monthly (KES)", interval: "monthly", currency: "KES", amount_minor: 34_900, auto_renew_available: true, mpesa_available: true },
  { code: "annual-kes", name: "Annual (KES)", interval: "annually", currency: "KES", amount_minor: 349_000, auto_renew_available: true, mpesa_available: true },
  { code: "monthly-usd", name: "Monthly (USD)", interval: "monthly", currency: "USD", amount_minor: 499, auto_renew_available: true, mpesa_available: false },
  { code: "annual-usd", name: "Annual (USD)", interval: "annually", currency: "USD", amount_minor: 3_999, auto_renew_available: true, mpesa_available: false },
];

afterEach(() => vi.unstubAllGlobals());

describe("Landing page", () => {
  it("explains the app and links to sign up and log in", async () => {
    mockApi({ "GET /api/v1/billing/plans/": { trial_days: 14, price_label: "Early-adopter price", plans } });
    renderApp(<Landing />);
    expect(screen.getByRole("heading", { level: 1, name: /Make every day count/ })).toBeInTheDocument();
    for (const name of ["Plan your day", "Reminders that actually ring", "Habits that stick", "Honest insights"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("link", { name: /Sign up|Start your free|Start free trial/ })[0]).toHaveAttribute("href", "/register");
    expect(screen.getAllByRole("link", { name: /Log in/ })[0]).toHaveAttribute("href", "/login");
  });

  it("shows live prices with the early-adopter label and annual saving", async () => {
    mockApi({ "GET /api/v1/billing/plans/": { trial_days: 14, price_label: "Early-adopter price", plans } });
    renderApp(<Landing />);
    expect(await screen.findByText("Early-adopter price")).toBeInTheDocument();
    expect(screen.getByText(/KES\s?349\b|Ksh\s?349\b/)).toBeInTheDocument();
    expect(screen.getByText(/Save 17%/)).toBeInTheDocument();
    expect(screen.getByText(/US\$\s?4\.99|\$4\.99/)).toBeInTheDocument();
  });
});
