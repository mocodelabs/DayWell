import { useQuery } from "@tanstack/react-query";
import {
  BarChart3, BellRing, BookOpen, CalendarDays, Check, CheckCircle2, Circle, Dumbbell, Droplets, HeartHandshake, Leaf, Lock, Moon, NotebookPen,
  ShieldCheck, Smartphone, Sparkles, Sprout, Sun, type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { InstallApp } from "@/components/InstallApp";
import { formatPrice, type BillingPlan } from "@/features/billing/billing";
import { api } from "@/lib/api";

interface PublicPlans {
  trial_days: number;
  price_label: string;
  plans: BillingPlan[];
}

const FEATURES: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: CalendarDays, title: "Plan your day", body: "Tasks, a real calendar and a smart day planner that fits work around your fixed commitments and warns before you overload." },
  { icon: BellRing, title: "Reminders that actually ring", body: "Alarms with snooze, quiet hours and push notifications to your phone — scheduled on our servers, so they fire even when you forget DayWell is open." },
  { icon: Sun, title: "A warm morning briefing", body: "Start with what matters: today's plan, what's happening now and what can wait — in the tone you choose." },
  { icon: Sprout, title: "Habits that stick", body: "Daily or a few times a week, counts or minutes, with streaks and rest days so one missed day doesn't undo your progress." },
  { icon: Leaf, title: "Wellness in one place", body: "Reading, workouts, water, sleep, journaling, mindfulness and affirmations — no more five separate apps." },
  { icon: BarChart3, title: "Honest insights", body: "Weekly reviews and trends calculated from what you really did, with gentle suggestions instead of guilt." },
];

const BENEFITS: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: HeartHandshake, title: "Calm, not nagging", body: "Encouraging words when you've earned them, quiet hours when you need them." },
  { icon: Lock, title: "Private by design", body: "Your journal is never shared. Export or delete your data any time." },
  { icon: Smartphone, title: "Works everywhere", body: "Phone, tablet or computer. Install it like an app — no app store needed." },
];

const FAQ: { q: string; a: ReactNode }[] = [
  { q: "Is there a free trial?", a: "Yes — every new account gets every feature free for 14 days, no card needed. After that your data stays readable; subscribe to keep adding and changing things." },
  { q: "How do I pay?", a: "M-Pesa or card in Kenyan shillings, or card in US dollars, through Paystack's secure checkout. Pay monthly or yearly, renew automatically or pay once — your choice." },
  { q: "Will alarms ring on my phone?", a: "Yes. Install DayWell and allow notifications, and reminders arrive as phone notifications even when the app is closed. When DayWell is open you get the full alarm with sound, snooze and dismiss." },
  { q: "Does it work on iPhone?", a: "Yes. Open daywell.live in Safari, tap Share → Add to Home Screen, then enable notifications from the installed app." },
  { q: "Can I cancel?", a: "Any time, from Settings. You keep Premium until the end of the period you paid for." },
];

export default function Landing() {
  const plans = useQuery({ queryKey: ["public-plans"], queryFn: () => api.get<PublicPlans>("/billing/plans/"), staleTime: 60 * 60_000 });

  return (
    <div className="min-h-dvh bg-bg text-ink">
      <a href="#main" className="sr-only-focusable fixed top-2 left-2 z-[90] rounded-lg bg-primary px-3 py-2 text-on-primary">Skip to content</a>

      <header className="sticky top-0 z-30 border-b border-white/10 bg-[#1f4d3a]/95 text-[#f7f4ed] backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-2">
            <img src="/icons/logo.svg" alt="" className="h-8 w-8" />
            <span className="font-[family-name:var(--font-display)] text-xl font-semibold">DayWell</span>
          </Link>
          <nav aria-label="Page sections" className="hidden items-center gap-6 text-sm md:flex">
            <a href="#features" className="hover:underline">Features</a>
            <a href="#how" className="hover:underline">How it works</a>
            <a href="#pricing" className="hover:underline">Pricing</a>
            <a href="#faq" className="hover:underline">FAQ</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/login" className="inline-flex min-h-10 items-center rounded-full px-3 text-sm font-semibold hover:bg-white/10">Log in</Link>
            <Link to="/register" className="inline-flex min-h-10 items-center rounded-full bg-[#e8b35a] px-4 text-sm font-semibold text-[#1f2d24] hover:bg-[#f0c475]">Sign up</Link>
          </div>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="outline-none">
        {/* Hero */}
        <section className="bg-[#1f4d3a] text-[#f7f4ed]" aria-labelledby="hero-title">
          <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 pt-10 pb-16 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:pt-16 lg:pb-24">
            <div>
              <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm"><Sparkles className="h-4 w-4 text-[#e8b35a]" aria-hidden /> Your calm personal companion</p>
              <h1 id="hero-title" className="font-[family-name:var(--font-display)] text-5xl leading-[1.05] font-semibold sm:text-6xl">
                Make every <span className="text-[#e8b35a]">day count.</span>
              </h1>
              <p className="mt-5 max-w-xl text-lg text-[#e3ebe1]">More clarity. Better routines. A day that works for you — plans, reminders that ring, habits and wellness in one gentle app.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/register" className="inline-flex min-h-12 items-center rounded-full bg-[#e8b35a] px-6 font-semibold text-[#1f2d24] shadow-sm hover:bg-[#f0c475]">Start your free 14 days</Link>
                <Link to="/login" className="inline-flex min-h-12 items-center rounded-full border border-white/40 px-6 font-semibold hover:bg-white/10">I already have an account</Link>
              </div>
              <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-sm text-[#e3ebe1]">
                {["No card needed", "Phone & desktop", "M-Pesa or card"].map((t) => (
                  <li key={t} className="flex items-center gap-1.5"><Check className="h-4 w-4 text-[#e8b35a]" aria-hidden />{t}</li>
                ))}
              </ul>
            </div>
            <PhoneMock />
          </div>
        </section>

        {/* Features */}
        <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6" aria-labelledby="features-title">
          <h2 id="features-title" className="font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Everything your day needs, nothing it doesn't</h2>
          <p className="mt-3 max-w-2xl text-muted">DayWell brings your schedule and your wellbeing together, so planning the day and looking after yourself happen in the same place.</p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <article key={f.title} className="rounded-[var(--radius-card)] border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-sage-soft text-primary-strong"><f.icon className="h-5 w-5" aria-hidden /></span>
                <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.body}</p>
              </article>
            ))}
          </div>
          <ul className="mt-8 flex flex-wrap gap-2 text-sm" aria-label="Wellness modules">
            {[[BookOpen, "Reading"], [Dumbbell, "Fitness"], [Droplets, "Hydration"], [Moon, "Sleep"], [NotebookPen, "Journal"], [Leaf, "Mindfulness"], [Sparkles, "Affirmations"]].map(([Icon, label]) => {
              const I = Icon as LucideIcon;
              return <li key={label as string} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5"><I className="h-4 w-4 text-primary" aria-hidden />{label as string}</li>;
            })}
          </ul>
        </section>

        {/* Benefits */}
        <section className="bg-surface-2" aria-labelledby="why-title">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 id="why-title" className="font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Why people choose DayWell</h2>
            <div className="mt-8 grid gap-6 md:grid-cols-3">
              {BENEFITS.map((b) => (
                <div key={b.title} className="flex gap-4">
                  <b.icon className="mt-1 h-6 w-6 shrink-0 text-primary" aria-hidden />
                  <div>
                    <h3 className="font-semibold">{b.title}</h3>
                    <p className="mt-1 text-sm text-muted">{b.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6" aria-labelledby="how-title">
          <h2 id="how-title" className="font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Up and running in two minutes</h2>
          <ol className="mt-8 grid gap-4 md:grid-cols-3">
            {[
              ["Create your account", "Sign up with your email — your 14-day free trial starts straight away."],
              ["Set your rhythm", "Tell DayWell your working hours, wake time and what you want to focus on. Skip anything you like."],
              ["Install & get reminded", "Add DayWell to your home screen and turn on notifications, so reminders reach your phone."],
            ].map(([title, body], i) => (
              <li key={title} className="rounded-[var(--radius-card)] border border-line bg-surface p-5">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-primary font-semibold text-on-primary" aria-hidden>{i + 1}</span>
                <h3 className="mt-3 font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted">{body}</p>
              </li>
            ))}
          </ol>
          <div className="mt-6 max-w-xs"><InstallApp /></div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-20 bg-surface-2" aria-labelledby="pricing-title">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="pricing-title" className="font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Simple pricing</h2>
              {plans.data?.price_label && <span className="rounded-full bg-amber-soft px-3 py-1 text-sm font-semibold">{plans.data.price_label}</span>}
            </div>
            <p className="mt-3 max-w-2xl text-muted">
              Try everything free for {plans.data?.trial_days ?? 14} days. Then one plan unlocks <strong className="text-ink">all Premium features</strong> — pay in shillings with M-Pesa or card, or in dollars by card.
            </p>
            <Pricing plans={plans.data?.plans} loading={plans.isPending} />
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl scroll-mt-20 px-4 py-16 sm:px-6" aria-labelledby="faq-title">
          <h2 id="faq-title" className="font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Questions</h2>
          <div className="mt-6 divide-y divide-line rounded-[var(--radius-card)] border border-line bg-surface">
            {FAQ.map((f) => (
              <details key={f.q} className="group p-5">
                <summary className="cursor-pointer list-none font-semibold marker:hidden">
                  <span className="flex items-center justify-between gap-4">{f.q}<span className="text-primary transition-transform group-open:rotate-45" aria-hidden>+</span></span>
                </summary>
                <p className="mt-2 text-sm text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* Final call to action */}
        <section className="bg-[#1f4d3a] text-[#f7f4ed]" aria-labelledby="cta-title">
          <div className="mx-auto flex max-w-6xl flex-col items-center px-4 py-16 text-center sm:px-6">
            <img src="/icons/logo.svg" alt="" className="h-14 w-14" />
            <h2 id="cta-title" className="mt-4 font-[family-name:var(--font-display)] text-3xl font-semibold sm:text-4xl">Ready for a better day?</h2>
            <p className="mt-2 text-[#e3ebe1]">Start free today. It takes two minutes.</p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link to="/register" className="inline-flex min-h-12 items-center rounded-full bg-[#e8b35a] px-6 font-semibold text-[#1f2d24] hover:bg-[#f0c475]">Sign up free</Link>
              <Link to="/login" className="inline-flex min-h-12 items-center rounded-full border border-white/40 px-6 font-semibold hover:bg-white/10">Log in</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-muted sm:px-6">
          <span className="flex items-center gap-2"><img src="/icons/logo.svg" alt="" className="h-5 w-5" /> © {new Date().getFullYear()} DayWell · daywell.live</span>
          <span className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4" aria-hidden /> Payments secured by Paystack</span>
        </div>
      </footer>
    </div>
  );
}

function Pricing({ plans, loading }: { plans?: BillingPlan[]; loading: boolean }) {
  if (loading) return <p className="mt-8 text-sm text-muted" role="status">Loading prices…</p>;
  if (!plans?.length) return <p className="mt-8 text-sm text-muted">Prices are shown after you sign up.</p>;
  const monthly = (cur: string) => plans.find((p) => p.currency === cur && p.interval === "monthly");
  const annual = (cur: string) => plans.find((p) => p.currency === cur && p.interval === "annually");
  return (
    <div className="mt-8 grid gap-4 md:grid-cols-2">
      {(["monthly", "annually"] as const).map((interval) => {
        const kes = interval === "monthly" ? monthly("KES") : annual("KES");
        const usd = interval === "monthly" ? monthly("USD") : annual("USD");
        const kesMonthly = monthly("KES");
        const saving = interval === "annually" && kes && kesMonthly ? Math.round(100 - (kes.amount_minor / (kesMonthly.amount_minor * 12)) * 100) : 0;
        return (
          <article key={interval} className={`rounded-[var(--radius-card)] border bg-surface p-6 ${interval === "annually" ? "border-primary shadow-[var(--shadow-card)]" : "border-line"}`}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-lg font-semibold">{interval === "monthly" ? "Monthly" : "Annual"}</h3>
              {saving > 0 && <span className="rounded-full bg-sage-soft px-2.5 py-0.5 text-xs font-semibold text-primary-strong">Save {saving}%</span>}
            </div>
            {kes && <p className="mt-3"><span className="text-3xl font-semibold">{formatPrice(kes.amount_minor, kes.currency)}</span><span className="text-muted"> / {interval === "monthly" ? "month" : "year"}</span></p>}
            {usd && <p className="mt-1 text-sm text-muted">or {formatPrice(usd.amount_minor, usd.currency)} / {interval === "monthly" ? "month" : "year"} by card</p>}
            <ul className="mt-5 space-y-2 text-sm">
              {["All Premium features", "Reminders & push notifications", "Habits, wellness & insights", interval === "annually" ? "Best value — two-plus months free" : "Cancel any time"].map((t) => (
                <li key={t} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-primary" aria-hidden />{t}</li>
              ))}
            </ul>
            <Link to="/register" className={`mt-6 inline-flex min-h-11 w-full items-center justify-center rounded-full font-semibold ${interval === "annually" ? "bg-primary text-on-primary hover:bg-primary-strong" : "border border-line hover:bg-sage-soft"}`}>
              Start free trial
            </Link>
          </article>
        );
      })}
    </div>
  );
}

/** A stylised phone showing the Today view (pure HTML/CSS, no images — keeps the page fast and the CSP strict). */
function PhoneMock() {
  const items: [string, string, boolean][] = [["Finish project proposal", "9:00 AM", false], ["Workout", "6:00 PM", true], ["Read 20 pages", "8:00 PM", false], ["Plan tomorrow", "9:00 PM", false]];
  return (
    <div className="mx-auto w-full max-w-[19rem] lg:mr-0" aria-hidden>
      <div className="rotate-[4deg] rounded-[2.6rem] border-[10px] border-[#14271e] bg-[#f7f4ed] p-5 text-[#1f2d24] shadow-2xl">
        <div className="mb-4 flex items-center justify-between text-[0.7rem] font-semibold"><span>9:41</span><span className="h-1.5 w-16 rounded-full bg-[#14271e]" /></div>
        <img src="/icons/logo.svg" alt="" className="h-8 w-8" />
        <p className="mt-2 font-[family-name:var(--font-display)] text-2xl font-semibold">Good morning!</p>
        <p className="text-xs text-[#5f655c]">Let's make today count.</p>
        <div className="mt-4 flex items-center gap-2 rounded-xl bg-[#dfe8dc] px-3 py-2 text-xs font-medium"><CalendarDays className="h-4 w-4" /> Today</div>
        <p className="mt-4 text-sm font-semibold">Your day</p>
        <ul className="mt-2 divide-y divide-[#e4e1d8]">
          {items.map(([t, time, done]) => (
            <li key={t} className="flex items-center gap-3 py-2.5">
              {done ? <CheckCircle2 className="h-5 w-5 text-[#3f6b4f]" /> : <Circle className="h-5 w-5 text-[#9aa196]" />}
              <span className="text-sm"><span className={done ? "text-[#5f655c] line-through" : ""}>{t}</span><span className="block text-[0.7rem] text-[#5f655c]">{time}</span></span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-[#dfe8dc] px-3 py-2.5 text-xs"><Leaf className="h-4 w-4 text-[#3f6b4f]" /> <span><strong>You're on track!</strong> Keep going.</span></div>
      </div>
    </div>
  );
}
