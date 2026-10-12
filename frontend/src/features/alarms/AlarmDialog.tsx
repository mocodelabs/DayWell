import { AlarmClock, BellOff, Check, Moon, Volume2, VolumeX } from "lucide-react";
import { AlertDialog } from "radix-ui";
import { useState } from "react";
import { useReturnFocus } from "@/components/ui/useReturnFocus";
import { Button } from "@/components/ui/Button";
import { useSession } from "@/features/auth/session";
import { formatTime } from "@/lib/datetime";
import type { AlarmOccurrence } from "@/lib/types";

const SNOOZE_CHOICES = [5, 10, 15, 30, 60];

interface Props {
  alarm: AlarmOccurrence;
  queued: number;
  audioBlocked: boolean;
  onEnableSound: () => void;
  onSnooze: (minutes?: number) => void;
  onDismiss: () => void;
  onComplete: () => void;
  onStopSound: () => void;
}

/**
 * The ringing alarm. An alertdialog (focus-trapped, announced to screen readers) with large, thumb-friendly controls.
 * Status is conveyed with text and icons, not colour alone.
 */
export function AlarmDialog({ alarm, queued, audioBlocked, onEnableSound, onSnooze, onDismiss, onComplete, onStopSound }: Props) {
  const { prefs } = useSession();
  const [muted, setMuted] = useState(false);
  const [moreSnooze, setMoreSnooze] = useState(false);
  const focus = useReturnFocus(true);
  return (
    <AlertDialog.Root open>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-[70] bg-black/45" />
        <AlertDialog.Content
         
          onCloseAutoFocus={focus.onCloseAutoFocus}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
            onSnooze();
          }}
          className="fixed inset-x-3 bottom-3 z-[80] rounded-[1.5rem] bg-surface p-5 shadow-[var(--shadow-card)] dw-enter sm:inset-auto sm:top-1/2 sm:left-1/2 sm:w-[28rem] sm:-translate-x-1/2 sm:-translate-y-1/2"
        >
          <div className="flex items-start gap-4">
            <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-amber-soft ${alarm.silent || muted ? "" : "dw-ringing"}`} aria-hidden>
              <AlarmClock className="h-7 w-7 text-terracotta" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                {alarm.silent ? "Quiet reminder" : "Reminder"} · {formatTime(alarm.scheduled_for, prefs)}
              </p>
              <AlertDialog.Title className="mt-0.5 text-xl font-semibold leading-snug">{alarm.title}</AlertDialog.Title>
              <AlertDialog.Description className="mt-1 text-sm text-muted">{alarm.body || "It's time."}</AlertDialog.Description>
            </div>
          </div>

          {audioBlocked && !alarm.silent && (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-amber/50 bg-amber-soft px-3 py-2.5 text-sm" role="status">
              <span className="flex items-center gap-2"><VolumeX className="h-4 w-4" aria-hidden /> Your browser blocked the alarm sound.</span>
              <Button size="sm" variant="secondary" icon={<Volume2 className="h-4 w-4" aria-hidden />} onClick={onEnableSound}>Play sound</Button>
            </div>
          )}

          <div className="mt-5 grid grid-cols-2 gap-2">
            <Button size="lg" variant="secondary" icon={<Moon className="h-5 w-5" aria-hidden />} onClick={() => onSnooze()} autoFocus>
              Snooze {alarm.snooze_minutes} min
            </Button>
            {alarm.can_complete ? (
              <Button size="lg" icon={<Check className="h-5 w-5" aria-hidden />} onClick={onComplete}>Mark done</Button>
            ) : (
              <Button size="lg" icon={<BellOff className="h-5 w-5" aria-hidden />} onClick={onDismiss}>Dismiss</Button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
            <div className="flex flex-wrap gap-1">
              {alarm.can_complete && <Button size="sm" variant="ghost" onClick={onDismiss}>Dismiss without completing</Button>}
              <Button size="sm" variant="ghost" aria-expanded={moreSnooze} onClick={() => setMoreSnooze((v) => !v)}>Snooze for…</Button>
              {!alarm.silent && !audioBlocked && (
                <Button size="sm" variant="ghost" icon={<VolumeX className="h-4 w-4" aria-hidden />} onClick={() => { onStopSound(); setMuted(true); }}>
                  Silence
                </Button>
              )}
            </div>
            {queued > 0 && <span className="text-muted">{queued} more waiting</span>}
          </div>
          {moreSnooze && (
            <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Snooze duration">
              {SNOOZE_CHOICES.map((m) => (
                <Button key={m} size="sm" variant="soft" onClick={() => onSnooze(m)}>{m < 60 ? `${m} min` : "1 hour"}</Button>
              ))}
            </div>
          )}
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
