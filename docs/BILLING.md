# Subscriptions & payments

DayWell Premium is sold monthly or annually through **Paystack** (cards everywhere, M-Pesa in Kenya).

| Plan | KES | USD |
|---|---|---|
| Monthly | KES 499 | USD 4 |
| Annual | KES 4,999 (≈17% off) | USD 45 (≈6% off) |

Prices live in the `billing.Plan` table (seeded by migration `billing/0002`); change them in Django admin, then clear
`paystack_plan_code` so a new Paystack plan is created (Paystack plan amounts are fixed).

## Access rules
- **Trial:** every new account gets **14 days** of everything (`BILLING_TRIAL_DAYS`), no card needed. Accounts that
  existed when billing shipped got a fresh 14-day trial.
- **Read-only after the trial** (or when a paid period ends): every page and all data stay visible, but creating or
  changing things returns `402 subscription_required` with a friendly message. Still allowed while read-only: sign in/out,
  profile and password, **data export and account deletion**, preferences, push registration, acting on alarms that are
  already ringing, notifications, and subscribing (`apps/billing/permissions.py`). Existing reminders keep firing.
- **Paid:** each successful charge adds one period to `paid_until`, counted from the later of now and the current end, so
  paying early never loses days.
- **Complimentary:** `manage.py billing_grant <email> --complimentary` (the public demo account has this; `seed_demo` sets
  it). `--trial-days N` extends a trial; `--revoke` removes complimentary access.

## Payment methods
| Choice | Channels | Renewal |
|---|---|---|
| **Pay once** (KES) | M-Pesa or card | none — the user pays again; a banner appears 3 days before the trial ends |
| **Pay once** (USD) | card | none |
| **Renew automatically** | card only (Paystack subscriptions don't support mobile money) | Paystack charges the card each period; `charge.success` webhooks extend access; 3-day grace (`BILLING_RENEWAL_GRACE_DAYS`) while a renewal settles |

The user can turn off automatic renewal in **Settings → Plan & billing**; access continues to the end of the paid period.

## Flow
1. `POST /api/v1/billing/checkout/ {plan, auto_renew}` creates a pending `Payment` with our own reference and calls
   Paystack `transaction/initialize` (amount, currency, channels, and the Paystack plan code for auto-renew). The browser
   is sent to Paystack's hosted page — DayWell never handles card numbers or M-Pesa PINs.
2. Paystack returns the user to `/settings/billing?reference=…`; the page calls `POST /api/v1/billing/verify/`, which
   **verifies with Paystack server-side** and checks the confirmed amount and currency match the plan before granting access.
3. Paystack also calls `POST /api/v1/billing/webhook/paystack/` (HMAC-SHA512 signature checked with the secret key). Charges
   are applied **exactly once** per reference, so verify + webhook + webhook retries never double-extend. Webhooks also
   handle `subscription.create` (stores the subscription code), `subscription.not_renew` / `subscription.disable`, and
   `invoice.payment_failed` (shows "renewal failed" on the billing page).

## Setting up Paystack (owner checklist)
1. Create a Paystack business account (Kenya) at https://dashboard.paystack.com. Start in **Test mode**.
2. **Settings → API Keys & Webhooks:** copy the **secret key** and set it in Vercel yourself (never paste it into chat):
   `vercel env add PAYSTACK_SECRET_KEY production --sensitive`, then redeploy (`git push` or `vercel deploy --prod`).
3. Same page, **Webhook URL:** `https://daywell-three.vercel.app/api/v1/billing/webhook/paystack/`.
   (The callback URL is set per transaction by DayWell; nothing to configure.)
4. **USD:** Kenyan Paystack accounts settle in KES by default; accepting USD needs Paystack to enable it on your account.
   Until then USD checkouts fail with Paystack's message, and the hourly plan sync reports USD plans as "not created".
5. Plans: within an hour of the key being set, the scheduler creates the Paystack plans automatically
   (`sync-billing-plans` job; or run `manage.py billing_sync_plans`). Until a plan is synced, only "Pay once" is offered.
6. Test with Paystack's test cards / test M-Pesa number, then switch to **Live** keys (repeat steps 2–3 with the live
   key and live webhook) after Paystack activates your business.

## Not included (yet)
Receipts/invoices by email (email isn't configured on the trial host), proration when switching monthly↔annual (a new
period simply stacks onto the old one), refunds (do them in the Paystack dashboard; access isn't revoked automatically),
coupons, and taxes/VAT handling.
