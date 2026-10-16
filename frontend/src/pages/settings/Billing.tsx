import clsx from "clsx";
import { CreditCard, Receipt, Smartphone, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Badge, Card, CardHeader, ErrorState, LoadingList, SegmentedControl } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { type Billing as BillingData, type BillingPlan, daysUntil, formatPrice, useBilling, useCancelRenewal, useCheckout, useVerifyPayment } from "@/features/billing/billing";
import { formatDate, localDateOf } from "@/lib/datetime";

type Currency = "KES" | "USD";

/** Formats an instant as a date in the user's own zone and date format. */
function useFmt() {
  const { prefs } = useSession();
  return (iso: string) => formatDate(localDateOf(new Date(iso), prefs.time_zone), prefs);
}
type Method = "auto" | "once";

export default function Billing() {
  const billing = useBilling();
  const { prefs } = useSession();
  const [params, setParams] = useSearchParams();
  const verify = useVerifyPayment();
  const toast = useToast();
  const verified = useRef<string | null>(null);

  // Paystack sends the customer back here with ?reference=…; confirm it with the server (never trust the redirect).
  const reference = params.get("reference") ?? params.get("trxref");
  useEffect(() => {
    if (!reference || verified.current === reference) return;
    verified.current = reference;
    verify.mutate(reference, {
      onSuccess: ({ payment }) => {
        if (payment.status === "success") toast.success("Payment received", "Thank you — Premium is active.");
        else toast.error("Payment not completed", payment.status === "pending" ? "We haven't received confirmation yet. Refresh in a minute." : "No money was taken. You can try again.");
      },
      onError: (err) => toast.error("Couldn't confirm the payment", (err as Error).message),
      onSettled: () => setParams({}, { replace: true }),
    });
  }, [reference]); // oxlint-disable-line react-hooks/exhaustive-deps -- run once per returned reference

  if (billing.isPending || (reference && verify.isPending)) return <LoadingList rows={3} label={reference ? "Confirming your payment" : "Loading your plan"} />;
  if (billing.error) return <ErrorState error={billing.error} onRetry={() => billing.refetch()} />;
  return <BillingPanel data={billing.data} defaultCurrency={prefs.time_zone === "Africa/Nairobi" ? "KES" : "USD"} />;
}

function StatusCard({ data }: { data: BillingData }) {
  const fmt = useFmt();
  const cancel = useCancelRenewal();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const plan = data.plans.find((p) => p.code === data.plan);
  const summary = {
    trial: <>Free trial — <strong>{daysUntil(data.trial_ends_at)} day{daysUntil(data.trial_ends_at) === 1 ? "" : "s"} left</strong> (until {fmt(data.trial_ends_at)}). Everything is unlocked.</>,
    active: data.renewal === "active"
      ? <>Premium{plan ? ` · ${plan.name}` : ""}. Renews automatically on <strong>{fmt(data.paid_until!)}</strong>.</>
      : <>Premium{plan ? ` · ${plan.name}` : ""}, paid until <strong>{fmt(data.paid_until!)}</strong>.{data.renewal === "non_renewing" ? " Automatic renewal is off." : " Pay again before then to keep it."}</>,
    complimentary: <>Complimentary Premium. Nothing to pay.</>,
    read_only: <>Your trial has ended, so DayWell is <strong>read-only</strong>. Everything you saved is still here — subscribe to add or change things.</>,
  }[data.state];
  return (
    <Card aria-labelledby="plan-status">
      <CardHeader id="plan-status" title="Your plan" icon={Sparkles} action={<Badge tone={data.state === "read_only" ? "warn" : "primary"}>{{ trial: "Trial", active: "Premium", complimentary: "Premium", read_only: "Read-only" }[data.state]}</Badge>} />
      <p className="text-sm">{summary}</p>
      {data.renewal === "attention" && <p className="mt-2 text-sm text-danger">Your last automatic renewal didn't go through. Check your card with your bank, or pay once below.</p>}
      {(data.renewal === "active" || data.renewal === "attention") && (
        <>
          <Button variant="secondary" size="sm" className="mt-3" onClick={() => setConfirm(true)}>Turn off automatic renewal</Button>
          <ConfirmDialog
            open={confirm}
            onOpenChange={setConfirm}
            title="Turn off automatic renewal?"
            description={`You keep Premium until ${data.paid_until ? fmt(data.paid_until) : "the end of this period"}. After that DayWell becomes read-only unless you pay again.`}
            confirmLabel="Turn off renewal"
            onConfirm={() => cancel.mutate(undefined, {
              onSuccess: () => toast.success("Automatic renewal is off"),
              onError: (err) => toast.error("Couldn't change renewal", (err as Error).message),
            })}
          />
        </>
      )}
    </Card>
  );
}

function BillingPanel({ data, defaultCurrency }: { data: BillingData; defaultCurrency: Currency }) {
  const [currency, setCurrency] = useState<Currency>(defaultCurrency);
  const [method, setMethod] = useState<Method>("once");
  const [selected, setSelected] = useState<string | null>(null);
  const checkout = useCheckout();
  const toast = useToast();
  const fmt = useFmt();
  const plans = data.plans.filter((p) => p.currency === currency);
  const monthly = plans.find((p) => p.interval === "monthly");
  const chosen = plans.find((p) => p.code === selected) ?? plans.find((p) => p.interval === "annually") ?? plans[0];
  const autoAvailable = !!chosen?.auto_renew_available;
  const effectiveMethod: Method = method === "auto" && autoAvailable ? "auto" : "once";
  const alreadyRenewing = data.renewal === "active";

  const pay = () => {
    if (!chosen) return;
    checkout.mutate(
      { plan: chosen.code, auto_renew: effectiveMethod === "auto" },
      {
        onSuccess: ({ authorization_url }) => window.location.assign(authorization_url),
        onError: (err) => toast.error("Couldn't start the payment", (err as Error).message),
      },
    );
  };

  return (
    <div className="space-y-4">
      <StatusCard data={data} />
      {data.state !== "complimentary" && (
        <Card aria-labelledby="choose-plan">
          <CardHeader id="choose-plan" title={data.state === "active" ? "Extend Premium" : "Choose a plan"} icon={CreditCard}
            action={<SegmentedControl label="Currency" value={currency} onChange={(v) => { setCurrency(v); setSelected(null); }} options={[{ value: "KES", label: "KES" }, { value: "USD", label: "USD" }]} />} />
          <div role="radiogroup" aria-label="Billing period" className="grid gap-3 sm:grid-cols-2">
            {plans.map((p) => <PlanOption key={p.code} plan={p} monthly={monthly} checked={chosen?.code === p.code} onSelect={() => setSelected(p.code)} />)}
          </div>

          <fieldset className="mt-4">
            <legend className="text-sm font-medium">How would you like to pay?</legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <MethodOption checked={effectiveMethod === "once"} onSelect={() => setMethod("once")} icon={currency === "KES" ? Smartphone : CreditCard}
                title="Pay once" detail={currency === "KES" ? "M-Pesa or card. Covers one period; pay again to continue." : "Card. Covers one period; pay again to continue."} />
              <MethodOption checked={effectiveMethod === "auto"} onSelect={() => setMethod("auto")} disabled={!autoAvailable || alreadyRenewing} icon={CreditCard}
                title="Renew automatically" detail={alreadyRenewing ? "You already have automatic renewal." : autoAvailable ? "Card only. Charged each period until you turn it off." : "Not available for this plan yet."} />
            </div>
          </fieldset>

          {!data.payments_enabled && <p className="mt-3 text-sm text-muted">Payments are being set up — check back soon.</p>}
          <Button className="mt-4 w-full sm:w-auto" onClick={pay} loading={checkout.isPending} disabled={!chosen || !data.payments_enabled}>
            {chosen ? `Continue to payment · ${formatPrice(chosen.amount_minor, chosen.currency)}` : "Continue to payment"}
          </Button>
          <p className="mt-2 text-xs text-muted">You'll finish on Paystack's secure page and come straight back here. DayWell never sees your card or M-Pesa PIN.</p>
        </Card>
      )}
      {data.payments.length > 0 && (
        <Card aria-labelledby="payment-history">
          <CardHeader id="payment-history" title="Payment history" icon={Receipt} />
          <ul className="divide-y divide-line text-sm">
            {data.payments.map((p) => (
              <li key={p.reference} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>{fmt(p.paid_at ?? p.created_at)} · {data.plans.find((x) => x.code === p.plan)?.name ?? p.plan}{p.kind === "renewal" ? " (renewal)" : ""}{p.channel === "mobile_money" ? " · M-Pesa" : p.channel ? ` · ${p.channel}` : ""}</span>
                <span className="flex items-center gap-2">{formatPrice(p.amount_minor, p.currency)} <Badge tone={p.status === "success" ? "primary" : "warn"}>{p.status === "success" ? "Paid" : p.status}</Badge></span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function PlanOption({ plan, monthly, checked, onSelect }: { plan: BillingPlan; monthly?: BillingPlan; checked: boolean; onSelect: () => void }) {
  const annual = plan.interval === "annually";
  const saving = annual && monthly ? Math.round(100 - (plan.amount_minor / (monthly.amount_minor * 12)) * 100) : 0;
  return (
    <button type="button" role="radio" aria-checked={checked} onClick={onSelect}
      className={clsx("rounded-xl border p-4 text-left transition-colors", checked ? "border-primary bg-sage-soft" : "border-line hover:bg-sage-soft")}>
      <span className="flex items-center justify-between gap-2">
        <span className="font-semibold">{annual ? "Annual" : "Monthly"}</span>
        {saving > 0 && <Badge tone="amber">Save {saving}%</Badge>}
      </span>
      <span className="mt-1 block text-xl font-semibold">{formatPrice(plan.amount_minor, plan.currency)}<span className="text-sm font-normal text-muted"> / {annual ? "year" : "month"}</span></span>
    </button>
  );
}

function MethodOption({ checked, onSelect, disabled, icon: Icon, title, detail }: { checked: boolean; onSelect: () => void; disabled?: boolean; icon: typeof CreditCard; title: string; detail: string }) {
  return (
    <label className={clsx("flex min-h-9 cursor-pointer items-start gap-3 rounded-xl border p-3", checked ? "border-primary bg-sage-soft" : "border-line", disabled && "cursor-not-allowed opacity-60")}>
      <input type="radio" name="pay-method" className="mt-1 h-5 w-5" checked={checked} onChange={onSelect} disabled={disabled} />
      <span>
        <span className="flex items-center gap-1.5 text-sm font-medium"><Icon className="h-4 w-4" aria-hidden />{title}</span>
        <span className="block text-sm text-muted">{detail}</span>
      </span>
    </label>
  );
}
