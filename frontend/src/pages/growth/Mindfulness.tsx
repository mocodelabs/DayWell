import { Brain, Pause, Play, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useMindfulness, useWellnessMutation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate, minutesLabel } from "@/lib/datetime";
import type { MindfulnessSession } from "@/lib/types";

const KINDS: { key: MindfulnessSession["kind"]; label: string; guide: string[] }[] = [
  { key: "breathing", label: "Breathing", guide: ["Breathe in… 4", "Hold… 4", "Breathe out… 6"] },
  { key: "meditation", label: "Quiet sitting", guide: ["Notice your breath", "Let thoughts pass by", "Return to the breath"] },
  { key: "reflection", label: "Reflection", guide: ["What do I need right now?", "What went well today?", "What can I let go of?"] },
  { key: "stretch", label: "Stretch break", guide: ["Roll your shoulders", "Stretch your neck gently", "Reach up and breathe"] },
];

/** A lightweight timer with gentle prompts — not a clinical intervention. */
export default function Mindfulness() {
  const { prefs } = useSession();
  const history = useMindfulness();
  const mut = useWellnessMutation();
  const toast = useToast();
  const [kind, setKind] = useState<MindfulnessSession["kind"]>("breathing");
  const [minutes, setMinutes] = useState(3);
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  const timer = useRef<number | null>(null);
  const planned = minutes * 60;
  const guide = KINDS.find((k) => k.key === kind)!.guide;

  useEffect(() => {
    if (!running) return;
    timer.current = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [running]);
  useEffect(() => {
    if (running && elapsed >= planned) finish(planned);
  });

  const finish = (completed: number) => {
    setRunning(false);
    if (completed < 30) {
      setElapsed(0);
      return;
    }
    mut.mutate(() => api.post("/wellness/mindfulness/", { kind, planned_seconds: planned, completed_seconds: completed }), {
      onSuccess: () => toast.success("Session saved", completed >= planned ? "Well done for taking that time." : "Every minute counts."),
    });
    setElapsed(0);
  };

  const step = guide[Math.floor(elapsed / (kind === "breathing" ? 4 : 20)) % guide.length];
  const left = Math.max(0, planned - elapsed);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader title="Take a moment" icon={Brain} />
        <div className="grid grid-cols-2 gap-2">
          <Select aria-label="Exercise" value={kind} onChange={(e) => setKind(e.target.value as MindfulnessSession["kind"])} disabled={running}>{KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}</Select>
          <Select aria-label="Length" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} disabled={running}>{[1, 3, 5, 10, 15, 20].map((m) => <option key={m} value={m}>{m} min</option>)}</Select>
        </div>
        <div className="my-6 flex flex-col items-center gap-2">
          <div className={`grid h-40 w-40 place-items-center rounded-full bg-sage-soft ${running && kind === "breathing" ? "transition-transform duration-[4000ms] ease-in-out" : ""}`}
            style={running && kind === "breathing" ? { transform: `scale(${Math.floor(elapsed / 4) % 3 === 0 ? 1.12 : Math.floor(elapsed / 4) % 3 === 2 ? 0.88 : 1.12})` } : undefined}>
            <span className="font-mono text-3xl font-semibold" role="timer" aria-live="off">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span>
          </div>
          <p className="min-h-6 text-center text-lg" aria-live="polite">{running ? step : "Ready when you are."}</p>
        </div>
        <div className="flex justify-center gap-2">
          {!running ? <Button size="lg" icon={<Play className="h-5 w-5" aria-hidden />} onClick={() => setRunning(true)}>{elapsed ? "Resume" : "Begin"}</Button>
            : <Button size="lg" variant="secondary" icon={<Pause className="h-5 w-5" aria-hidden />} onClick={() => setRunning(false)}>Pause</Button>}
          {elapsed > 0 && <Button size="lg" variant="ghost" icon={<Square className="h-5 w-5" aria-hidden />} onClick={() => finish(elapsed)}>End</Button>}
        </div>
        <p className="mt-4 text-xs text-muted">A short pause for wellbeing — not therapy or medical treatment.</p>
      </Card>
      <Card>
        <CardHeader title="Recent sessions" />
        {history.data?.results.length ? (
          <ul className="divide-y divide-line text-sm">
            {history.data.results.map((s) => (
              <li key={s.id} className="flex justify-between py-2"><span>{formatDate(s.date, prefs, "weekday")} · {KINDS.find((k) => k.key === s.kind)?.label}</span><span className="text-muted">{minutesLabel(Math.round(s.completed_seconds / 60))}</span></li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">No sessions yet.</p>}
      </Card>
    </div>
  );
}
