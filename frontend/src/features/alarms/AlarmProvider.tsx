import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useActiveAlarms, useAlarmAction, useUpcomingAlarms } from "@/hooks/queries";
import { alarmAudio, vibrate, type AudioOutcome } from "@/lib/audio";
import { showLocalNotification, syncPushSubscription } from "@/lib/push";
import type { AlarmOccurrence } from "@/lib/types";
import { useSession } from "@/features/auth/session";
import { useToast } from "@/components/ui/Toast";
import { AlarmDialog } from "./AlarmDialog";

interface AlarmCtx {
  active: AlarmOccurrence[];
  audioBlocked: boolean;
  enableSound: () => Promise<void>;
}

const Ctx = createContext<AlarmCtx>({ active: [], audioBlocked: false, enableSound: async () => undefined });
export const useAlarms = () => useContext(Ctx);

/**
 * Foreground alarm surface. The server is the authoritative scheduler: we poll /alarms/active/ (every 20 s while visible,
 * on focus, and when the service worker reports a push). Local timers only *refetch early* at an upcoming occurrence's
 * fire time so the in-app alarm is punctual; they never decide whether an alarm exists.
 */
export function AlarmProvider({ children }: { children: ReactNode }) {
  const { prefs } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const active = useActiveAlarms(true);
  const upcoming = useUpcomingAlarms(2, visible);
  const act = useAlarmAction();
  const [audioBlocked, setAudioBlocked] = useState(false);
  const shownRef = useRef(new Map<number, AudioOutcome | "silent">());
  const notifiedRef = useRef(new Set<number>());
  const [handled, setHandled] = useState<Set<number>>(new Set());

  const alarms = useMemo(() => (active.data ?? []).filter((a) => !handled.has(a.id)), [active.data, handled]);
  const current = alarms[0] ?? null;

  // Visibility + focus refetch, and unlock audio on the first user gesture.
  useEffect(() => {
    const onVis = () => {
      setVisible(document.visibilityState === "visible");
      if (document.visibilityState === "visible") active.refetch();
    };
    const unlock = () => void alarmAudio.unlock();
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onVis);
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onVis);
    };
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- mount-only: listeners must not be re-added on every poll
  }, []);

  // Service worker messages: a push arrived, or a notification was clicked.
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    void syncPushSubscription().catch(() => undefined); // re-register a rotated/dropped subscription on start
    const onMsg = (e: MessageEvent) => {
      if (e.data?.type === "daywell:push") active.refetch();
      if (e.data?.type === "daywell:push-subscription-changed") void syncPushSubscription().catch(() => undefined);
      if (e.data?.type === "daywell:notification-click" && typeof e.data.url === "string") navigate(e.data.url);
    };
    navigator.serviceWorker.addEventListener("message", onMsg);
    return () => navigator.serviceWorker.removeEventListener("message", onMsg);
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- mount-only service-worker listener; refetch/navigate are stable enough for a message handler
  }, []);

  // Early refetch at the exact fire time of the next few upcoming occurrences (non-authoritative).
  useEffect(() => {
    const timers = (upcoming.data ?? []).slice(0, 10).map((o) => {
      const delay = new Date(o.fire_at).getTime() - Date.now() + 2500;
      return delay > 0 && delay < 2 * 3600_000 ? window.setTimeout(() => active.refetch(), delay) : 0;
    });
    return () => timers.forEach((t) => t && window.clearTimeout(t));
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- re-arm only when the upcoming list changes
  }, [upcoming.data]);

  // Ring the current alarm (once), report what actually happened to the server.
  useEffect(() => {
    if (!current) {
      alarmAudio.stop();
      return;
    }
    if (!visible) {
      if (!notifiedRef.current.has(current.id)) {
        notifiedRef.current.add(current.id);
        void showLocalNotification(current.title, current.body, `occ-${current.id}`);
      }
      return;
    }
    if (shownRef.current.has(current.id)) return;
    let cancelled = false;
    (async () => {
      let outcome: AudioOutcome | "silent" = "silent";
      if (!current.silent) {
        outcome = await alarmAudio.play(`occ-${current.id}`, current.sound || prefs.default_sound, prefs.alarm_volume);
        vibrate();
      }
      if (cancelled) return;
      shownRef.current.set(current.id, outcome);
      setAudioBlocked(outcome === "blocked");
      act.mutate({ id: current.id, action: "shown", body: { audio: outcome === "silent" ? "muted" : outcome } });
    })();
    return () => {
      cancelled = true;
    };
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- ring once per alarm id / visibility change; re-running on every poll would restart the sound
  }, [current?.id, visible]);

  const enableSound = useCallback(async () => {
    if (!current) {
      await alarmAudio.unlock();
      return;
    }
    const outcome = await alarmAudio.play(`occ-${current.id}`, current.sound || prefs.default_sound, prefs.alarm_volume);
    setAudioBlocked(outcome === "blocked");
    if (outcome === "played") act.mutate({ id: current.id, action: "shown", body: { audio: "played" } });
  }, [current, prefs.default_sound, prefs.alarm_volume, act]);

  const finish = useCallback((id: number) => {
    alarmAudio.stop();
    setHandled((prev) => new Set(prev).add(id));
    setAudioBlocked(false);
  }, []);

  const runAction = useCallback(async (occ: AlarmOccurrence, action: "snooze" | "dismiss" | "complete", minutes?: number) => {
    finish(occ.id);
    try {
      await act.mutateAsync({ id: occ.id, action, body: action === "snooze" ? { minutes } : undefined });
      if (action === "snooze") toast.info("Snoozed", `We'll remind you again in ${minutes ?? occ.snooze_minutes} minutes.`);
      if (action === "complete") toast.success("Nicely done", "Marked as complete.");
    } catch (e) {
      setHandled((prev) => {
        const n = new Set(prev);
        n.delete(occ.id);
        return n;
      });
      shownRef.current.delete(occ.id);
      toast.error("That didn't go through", (e as Error).message);
    }
  }, [act, finish, toast]);

  // Notification click deep links: /?alarm=<id>&action=snooze
  useEffect(() => {
    const id = Number(params.get("alarm"));
    const action = params.get("action");
    if (!id) return;
    if (action === "snooze") {
      act.mutateAsync({ id, action: "snooze" }).then(
        () => toast.info("Snoozed from your notification"),
        (e: Error) => toast.error("Couldn't snooze", e.message),
      );
    }
    params.delete("alarm");
    params.delete("action");
    setParams(params, { replace: true });
    // oxlint-disable-next-line react-hooks/exhaustive-deps -- handle the deep link once on mount
  }, []);

  return (
    <Ctx.Provider value={{ active: alarms, audioBlocked, enableSound }}>
      {children}
      {current && visible && (
        <AlarmDialog
          alarm={current}
          queued={alarms.length - 1}
          audioBlocked={audioBlocked}
          onEnableSound={enableSound}
          onSnooze={(m) => runAction(current, "snooze", m)}
          onDismiss={() => runAction(current, "dismiss")}
          onComplete={() => runAction(current, "complete")}
          onStopSound={() => alarmAudio.stop()}
        />
      )}
    </Ctx.Provider>
  );
}
