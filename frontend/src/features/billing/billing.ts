import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type BillingState = "trial" | "active" | "complimentary" | "read_only";
export type Renewal = "none" | "active" | "non_renewing" | "attention";

export interface BillingPlan {
  code: string;
  name: string;
  interval: "monthly" | "annually";
  currency: "KES" | "USD";
  amount_minor: number;
  auto_renew_available: boolean;
  mpesa_available: boolean;
}

export interface BillingPayment {
  reference: string;
  plan: string;
  kind: "checkout" | "renewal";
  auto_renew: boolean;
  amount_minor: number;
  currency: string;
  status: "pending" | "success" | "failed" | "abandoned";
  channel: string;
  period_start: string | null;
  period_end: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface Billing {
  state: BillingState;
  has_premium: boolean;
  trial_ends_at: string;
  paid_until: string | null;
  renewal: Renewal;
  plan: string | null;
  payments_enabled: boolean;
  plans: BillingPlan[];
  payments: BillingPayment[];
}

export const billingKey = ["billing"] as const;

export const useBilling = () => useQuery({ queryKey: billingKey, queryFn: () => api.get<Billing>("/billing/"), staleTime: 5 * 60_000 });

export function useCheckout() {
  return useMutation({
    mutationFn: (input: { plan: string; auto_renew: boolean }) => api.post<{ authorization_url: string; reference: string }>("/billing/checkout/", input),
  });
}

export function useVerifyPayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reference: string) => api.post<{ payment: BillingPayment; billing: Billing }>("/billing/verify/", { reference }),
    onSuccess: (res) => qc.setQueryData(billingKey, res.billing),
  });
}

export function useCancelRenewal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Billing>("/billing/cancel-renewal/"),
    onSuccess: (billing) => qc.setQueryData(billingKey, billing),
  });
}

export function formatPrice(amountMinor: number, currency: string): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency, minimumFractionDigits: amountMinor % 100 ? 2 : 0 }).format(amountMinor / 100);
}

/** Whole days left until ``iso`` (0 when it's today or past). */
export function daysUntil(iso: string, now = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - now) / 86_400_000));
}
