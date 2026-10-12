import { Copy, Heart, Plus, Share2, Trash2 } from "lucide-react";
import { useState } from "react";
import { ModuleReminderCard } from "@/components/ModuleReminderCard";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, ErrorState, LoadingList, SegmentedControl } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useAffirmationHistory, useAffirmationLibrary, useAffirmationMutation, useTodayAffirmation } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/datetime";

const CATEGORIES = [["confidence", "Confidence"], ["focus", "Focus"], ["gratitude", "Gratitude"], ["resilience", "Resilience"], ["self_compassion", "Self-compassion"],
  ["consistency", "Consistency"], ["learning", "Learning"], ["calmness", "Calmness"], ["growth", "Personal growth"]];

export default function Affirmations() {
  const { prefs } = useSession();
  const today = useTodayAffirmation(true);
  const mut = useAffirmationMutation();
  const toast = useToast();
  const [view, setView] = useState<"library" | "favorites" | "mine" | "history">("library");
  const [category, setCategory] = useState("");
  const [text, setText] = useState("");
  const [newCat, setNewCat] = useState("calmness");
  const lib = useAffirmationLibrary({ category: category || undefined, favorites: view === "favorites" ? "true" : undefined, custom: view === "mine" ? "true" : undefined });
  const history = useAffirmationHistory();
  const a = today.data;
  const copy = async (t: string) => {
    try {
      await navigator.clipboard.writeText(t);
      toast.success("Copied");
    } catch {
      toast.error("Couldn't copy", "Your browser blocked clipboard access.");
    }
  };
  const share = async (t: string) => {
    if (navigator.share) await navigator.share({ text: t }).catch(() => undefined);
    else void copy(t);
  };
  return (
    <div className="flex flex-col gap-4">
      {a && (
        <Card className="bg-amber-soft/50">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Today · {formatDate(a.date, prefs, "long")}</p>
          <blockquote className="mt-2 font-[family-name:var(--font-display)] text-2xl leading-snug">“{a.affirmation.text}”</blockquote>
          <div className="mt-4 flex flex-wrap gap-2">
            {!a.acknowledged_at && <Button size="sm" onClick={() => mut.mutate(() => api.post(`/affirmations/daily/${a.id}/acknowledge/`))}>I've taken this in</Button>}
            <Button size="sm" variant="soft" icon={<Heart className={a.favorite ? "h-4 w-4 fill-current" : "h-4 w-4"} aria-hidden />} aria-pressed={a.favorite}
              onClick={() => mut.mutate(() => (a.favorite ? api.delete(`/affirmations/library/${a.affirmation.id}/favorite/`) : api.post(`/affirmations/library/${a.affirmation.id}/favorite/`)))}>
              {a.favorite ? "Saved" : "Save"}
            </Button>
            <Button size="sm" variant="ghost" icon={<Copy className="h-4 w-4" aria-hidden />} onClick={() => copy(a.affirmation.text)}>Copy</Button>
            <Button size="sm" variant="ghost" icon={<Share2 className="h-4 w-4" aria-hidden />} onClick={() => share(a.affirmation.text)}>Share</Button>
          </div>
          <p className="mt-3 text-xs text-muted">Affirmations are gentle prompts, not a substitute for professional support.</p>
        </Card>
      )}
      <ModuleReminderCard path="/affirmations/reminder/" title="Daily affirmation reminder" />
      <Card>
        <CardHeader title="Library" />
        <div className="mb-3 flex flex-wrap gap-2">
          <SegmentedControl label="Affirmation list" value={view} onChange={setView}
            options={[{ value: "library", label: "All" }, { value: "favorites", label: "Saved" }, { value: "mine", label: "My own" }, { value: "history", label: "History" }]} />
          {view !== "history" && (
            <Select aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)} className="w-auto">
              <option value="">All categories</option>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Select>
          )}
        </div>
        {view === "mine" && (
          <form className="mb-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) mut.mutate(() => api.post("/affirmations/library/", { text, category: newCat }), { onSuccess: () => setText("") }); }}>
            <Input aria-label="Your affirmation" className="min-w-60 flex-1" placeholder="Write your own affirmation" value={text} onChange={(e) => setText(e.target.value)} />
            <Select aria-label="Category" className="w-auto" value={newCat} onChange={(e) => setNewCat(e.target.value)}>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            <Button type="submit" icon={<Plus className="h-4 w-4" aria-hidden />} loading={mut.isPending}>Add</Button>
          </form>
        )}
        {view === "history" ? (
          history.isPending ? <LoadingList rows={3} /> : (
            <ul className="divide-y divide-line text-sm">
              {history.data?.results.map((h) => (
                <li key={h.id} className="flex justify-between gap-3 py-2"><span>“{h.affirmation.text}”</span><span className="shrink-0 text-muted">{formatDate(h.date, prefs, "weekday")}{h.acknowledged_at ? " · ✓" : ""}</span></li>
              ))}
            </ul>
          )
        ) : lib.isPending ? <LoadingList rows={4} /> : lib.error ? <ErrorState error={lib.error} /> : (
          <ul className="divide-y divide-line">
            {lib.data.results.map((x) => (
              <li key={x.id} className="flex items-center gap-2 py-2 text-sm">
                <span className="flex-1">{x.text}</span>
                <Button size="icon" variant="ghost" aria-label={x.favorite ? "Remove from saved" : "Save"} aria-pressed={x.favorite}
                  onClick={() => mut.mutate(() => (x.favorite ? api.delete(`/affirmations/library/${x.id}/favorite/`) : api.post(`/affirmations/library/${x.id}/favorite/`)))}>
                  <Heart className={x.favorite ? "h-4 w-4 fill-current text-terracotta" : "h-4 w-4"} aria-hidden />
                </Button>
                {x.custom && <Button size="icon" variant="ghost" aria-label="Delete" onClick={() => mut.mutate(() => api.delete(`/affirmations/library/${x.id}/`))}><Trash2 className="h-4 w-4" aria-hidden /></Button>}
              </li>
            ))}
            {lib.data.results.length === 0 && <li className="py-3 text-sm text-muted">Nothing here yet.</li>}
          </ul>
        )}
      </Card>
    </div>
  );
}
