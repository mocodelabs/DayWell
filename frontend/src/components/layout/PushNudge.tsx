import { BellRing, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { currentSubscription, pushSupport } from "@/lib/push";

const DISMISS_KEY = "dw:push-nudge-dismissed-at"; // per-device convenience only
const SNOOZE_MS = 7 * 86_400_000;

function dismissedRecently(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY) || 0);
    return Date.now() - at < SNOOZE_MS;
  } catch {
    return false;
  }
}

/**
 * On a phone or tablet that can receive Web Push but isn't subscribed, say plainly that alarms won't ring while DayWell
 * is closed, and link to the one-tap fix. Hidden on desktop, when permission is blocked, or for a week after dismissal.
 */
export function PushNudge() {
  const location = useLocation();
  const [show, setShow] = useState(false);

  useEffect(() => {
    const support = pushSupport();
    const touch = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;
    if (!touch || !support.push || support.permission === "denied" || support.permission === "unsupported" || dismissedRecently()) return;
    let cancelled = false;
    void (async () => {
      const [sub, config] = await Promise.all([
        currentSubscription().catch(() => null),
        api.get<{ configured: boolean }>("/push/config/").catch(() => ({ configured: false })),
      ]);
      if (!cancelled) setShow(!sub && config.configured);
    })();
    return () => { cancelled = true; };
  }, [location.pathname]);

  if (!show || location.pathname.startsWith("/settings/notifications")) return null;
  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* storage unavailable */ }
    setShow(false);
  };
  return (
    <div role="status" className="flex items-center gap-2 bg-amber-soft px-4 py-2 text-sm">
      <BellRing className="h-4 w-4 shrink-0" aria-hidden />
      <Link to="/settings/notifications" className="flex-1 hover:underline">
        Alarms won't ring on this device while DayWell is closed. Turn on notifications →
      </Link>
      <button onClick={dismiss} className="grid min-h-9 min-w-9 place-items-center rounded-full hover:bg-sage-soft" aria-label="Dismiss for a week">
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
