import { Lock, NotebookPen, Search } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Card, CardHeader, EmptyState, LoadingList } from "@/components/ui/feedback";
import { Field, FormError, Input, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useJournal, useJournalPrompt, useWellnessMutation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate, todayIn } from "@/lib/datetime";
import type { JournalEntry } from "@/lib/types";

const MOODS = ["Very low", "Low", "Okay", "Good", "Great"];

export default function Journal() {
  const { prefs } = useSession();
  const [q, setQ] = useState("");
  const entries = useJournal(q);
  const prompt = useJournalPrompt();
  const mut = useWellnessMutation();
  const toast = useToast();
  const [editing, setEditing] = useState<JournalEntry | null>(null);
  const [deleting, setDeleting] = useState<JournalEntry | null>(null);
  const blank = { date: todayIn(prefs.time_zone), title: "", body: "", g1: "", g2: "", g3: "", mood: "" };
  const [v, setV] = useState(blank);
  const [error, setError] = useState("");
  const startEdit = (e: JournalEntry) => {
    setEditing(e);
    setV({ date: e.date, title: e.title, body: e.body, g1: e.gratitude[0] ?? "", g2: e.gratitude[1] ?? "", g3: e.gratitude[2] ?? "", mood: e.mood ? String(e.mood) : "" });
  };
  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!v.body.trim() && !v.g1.trim()) return setError("Write a few words or one thing you're grateful for.");
    const body = { date: v.date, title: v.title, body: v.body, gratitude: [v.g1, v.g2, v.g3].filter((x) => x.trim()), mood: v.mood ? Number(v.mood) : null, prompt: prompt.data?.prompt ?? "" };
    mut.mutate(() => (editing ? api.patch(`/wellness/journal/${editing.id}/`, body) : api.post("/wellness/journal/", body)), {
      onSuccess: () => { toast.success("Saved privately"); setV(blank); setEditing(null); setError(""); },
      onError: (e) => setError((e as Error).message),
    });
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <Card>
        <CardHeader title={editing ? "Edit entry" : "Today's entry"} icon={NotebookPen} />
        <p className="mb-3 flex items-center gap-1.5 text-xs text-muted"><Lock className="h-3.5 w-3.5" aria-hidden />Private to you. Never shared or sent to AI services.</p>
        {prompt.data && !editing && <p className="mb-3 rounded-xl bg-sage-soft p-3 text-sm italic">{prompt.data.prompt}</p>}
        <form onSubmit={submit} className="flex flex-col gap-3">
          <FormError message={error} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date">{({ id }) => <Input id={id} type="date" max={todayIn(prefs.time_zone)} value={v.date} onChange={(e) => setV({ ...v, date: e.target.value })} />}</Field>
            <Field label="Title" optional>{({ id }) => <Input id={id} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />}</Field>
          </div>
          <Field label="Your thoughts" optional>{({ id }) => <Textarea id={id} rows={6} value={v.body} onChange={(e) => setV({ ...v, body: e.target.value })} />}</Field>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">Three things I'm grateful for <span className="font-normal text-muted">(optional)</span></legend>
            {(["g1", "g2", "g3"] as const).map((k, i) => <Input key={k} aria-label={`Gratitude ${i + 1}`} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />)}
          </fieldset>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium">Mood check-in <span className="font-normal text-muted">(optional)</span></legend>
            <div className="flex flex-wrap gap-1.5">
              {MOODS.map((m, i) => (
                <button key={m} type="button" aria-pressed={v.mood === String(i + 1)} onClick={() => setV({ ...v, mood: v.mood === String(i + 1) ? "" : String(i + 1) })}
                  className={`rounded-full border px-3 py-1.5 text-sm ${v.mood === String(i + 1) ? "border-primary bg-sage-soft font-medium" : "border-line"}`}>{m}</button>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2">
            <Button type="submit" loading={mut.isPending}>Save entry</Button>
            {editing && <Button variant="ghost" onClick={() => { setEditing(null); setV(blank); }}>Cancel</Button>}
          </div>
        </form>
      </Card>
      <Card>
        <CardHeader title="Past entries" />
        <label className="relative mb-3 block">
          <span className="sr-only">Search journal</span>
          <Search className="pointer-events-none absolute top-3 left-3 h-5 w-5 text-muted" aria-hidden />
          <Input type="search" placeholder="Search your entries" value={q} onChange={(e) => setQ(e.target.value)} className="pl-10" />
        </label>
        {entries.isPending ? <LoadingList rows={3} /> : !entries.data?.results.length ? <EmptyState title={q ? "No matching entries" : "No entries yet"} /> : (
          <ul className="flex flex-col gap-2">
            {entries.data.results.map((e) => (
              <li key={e.id} className="rounded-xl border border-line p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium">{formatDate(e.date, prefs, "long")}{e.title ? ` · ${e.title}` : ""}</p>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => startEdit(e)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleting(e)}>Delete</Button>
                  </div>
                </div>
                {e.body && <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-sm">{e.body}</p>}
                {e.gratitude.length > 0 && <p className="mt-1 text-sm text-muted">Grateful for: {e.gratitude.join(", ")}</p>}
                {e.mood && <p className="mt-1 text-xs text-muted">Mood: {MOODS[e.mood - 1]}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <ConfirmDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)} danger title="Delete this entry?" description="This can't be undone." confirmLabel="Delete"
        onConfirm={() => deleting && mut.mutate(() => api.delete(`/wellness/journal/${deleting.id}/`), { onSuccess: () => setDeleting(null) })} />
    </div>
  );
}
