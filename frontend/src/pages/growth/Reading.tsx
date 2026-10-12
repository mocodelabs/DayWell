import { BookOpen, Pause, Play, Plus, Quote, Square, Star, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { ModuleReminderCard } from "@/components/ModuleReminderCard";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog, Dialog } from "@/components/ui/Dialog";
import { Badge, Card, CardHeader, EmptyState, ErrorState, LoadingList, ProgressBar, SegmentedControl } from "@/components/ui/feedback";
import { Field, FormError, Input, Select, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { useBookNotes, useBooks, useReadingMutation, useReadingSessions, useReadingStats, useRunningSession } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDate, minutesLabel, percent, todayIn } from "@/lib/datetime";
import type { Book } from "@/lib/types";

const STATUS: Record<Book["status"], string> = { want: "Want to read", reading: "Reading", completed: "Completed", paused: "Paused" };

export default function Reading() {
  const [status, setStatus] = useState<string>("reading");
  const books = useBooks(status === "all" ? undefined : status);
  const stats = useReadingStats();
  const [editing, setEditing] = useState<Book | null | undefined>(undefined);
  const [logFor, setLogFor] = useState<Book | null>(null);
  const [detail, setDetail] = useState<Book | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <RunningTimer />
      <StatsCard stats={stats.data} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SegmentedControl label="Book status" value={status} onChange={setStatus}
          options={[{ value: "reading", label: "Reading" }, { value: "want", label: "Want to read" }, { value: "completed", label: "Finished" }, { value: "all", label: "All" }]} />
        <Button icon={<Plus className="h-4 w-4" aria-hidden />} onClick={() => setEditing(null)}>Add book</Button>
      </div>
      {books.isPending ? <LoadingList /> : books.error ? <ErrorState error={books.error} onRetry={() => books.refetch()} /> : books.data.results.length === 0 ? (
        <EmptyState icon={BookOpen} title="No books here yet" action={<Button size="sm" onClick={() => setEditing(null)}>Add a book</Button>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {books.data.results.map((b) => <BookCard key={b.id} book={b} onEdit={() => setEditing(b)} onLog={() => setLogFor(b)} onOpen={() => setDetail(b)} />)}
        </div>
      )}
      <ModuleReminderCard path="/reading/reminder/" title="Reading reminder" description="A gentle nudge to read — even 10 minutes counts." />
      <RecentSessions />
      {editing !== undefined && <BookForm book={editing} onClose={() => setEditing(undefined)} />}
      {logFor && <LogSession book={logFor} onClose={() => setLogFor(null)} />}
      {detail && <BookNotes book={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function StatsCard({ stats }: { stats?: ReturnType<typeof useReadingStats>["data"] }) {
  if (!stats) return null;
  return (
    <Card>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div><dt className="text-xs text-muted">This week</dt><dd className="text-lg font-semibold">{minutesLabel(stats.week.minutes)}</dd>{stats.week.pages > 0 && <dd className="text-xs text-muted">{stats.week.pages} pages</dd>}</div>
        <div><dt className="text-xs text-muted">This month</dt><dd className="text-lg font-semibold">{minutesLabel(stats.month.minutes)}</dd></div>
        <div><dt className="text-xs text-muted">Streak</dt><dd className="text-lg font-semibold">{stats.streak.current} day{stats.streak.current === 1 ? "" : "s"}</dd></div>
        <div><dt className="text-xs text-muted">Finished this year</dt><dd className="text-lg font-semibold">{stats.books_completed_this_year}{stats.yearly_goal.target ? ` / ${stats.yearly_goal.target}` : ""}</dd>
          {stats.yearly_goal.target && <dd className="text-xs text-muted">{percent(stats.yearly_goal.rate)} of your yearly goal</dd>}</div>
      </dl>
      <p className="mt-3 text-xs text-muted">Totals come only from sessions you've timed or logged. Taking a break simply resets the streak count — no judgement.</p>
    </Card>
  );
}

function RunningTimer() {
  const running = useRunningSession();
  const mut = useReadingMutation();
  const toast = useToast();
  const [now, setNow] = useState(Date.now());
  const [endPage, setEndPage] = useState("");
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const s = running.data;
  if (!s) return null;
  const secs = Math.max(0, Math.floor((now - new Date(s.started_at).getTime()) / 1000));
  const stop = () => mut.mutate(() => api.post(`/reading/sessions/${s.id}/stop/`, endPage ? { end_page: Number(endPage) } : {}), {
    onSuccess: () => { toast.success("Session saved", `${Math.round(secs / 60)} minutes of reading.`); running.refetch(); },
    onError: (e) => toast.error("Couldn't stop the timer", (e as Error).message),
  });
  return (
    <Card className="border-amber/60 bg-amber-soft/50">
      <div className="flex flex-wrap items-center gap-4">
        <Timer className="h-8 w-8 text-terracotta" aria-hidden />
        <div className="flex-1">
          <p className="text-sm text-muted">Reading “{s.book_title}”</p>
          <p className="font-mono text-3xl font-semibold" role="timer" aria-live="off">{String(Math.floor(secs / 3600)).padStart(2, "0")}:{String(Math.floor((secs % 3600) / 60)).padStart(2, "0")}:{String(secs % 60).padStart(2, "0")}</p>
        </div>
        <Field label="Stopped at page" optional>{({ id }) => <Input id={id} type="number" min={0} value={endPage} onChange={(e) => setEndPage(e.target.value)} className="w-28" />}</Field>
        <Button icon={<Square className="h-4 w-4" aria-hidden />} onClick={stop} loading={mut.isPending}>Stop & save</Button>
      </div>
    </Card>
  );
}

function BookCard({ book, onEdit, onLog, onOpen }: { book: Book; onEdit: () => void; onLog: () => void; onOpen: () => void }) {
  const mut = useReadingMutation();
  const toast = useToast();
  const [confirmDone, setConfirmDone] = useState(false);
  const start = () => mut.mutate(() => api.post(`/reading/books/${book.id}/timer/start/`), {
    onSuccess: () => toast.info("Timer started", "Happy reading."), onError: (e) => toast.error("Couldn't start the timer", (e as Error).message),
  });
  return (
    <Card>
      <div className="flex gap-3">
        {book.cover_url ? <img src={book.cover_url} alt="" className="h-24 w-16 rounded-md object-cover" /> : <div className="grid h-24 w-16 place-items-center rounded-md bg-sage" aria-hidden><BookOpen className="h-6 w-6 text-primary" /></div>}
        <div className="min-w-0 flex-1">
          <button onClick={onOpen} className="text-left font-semibold hover:underline">{book.title}</button>
          {book.author && <p className="text-sm text-muted">{book.author}</p>}
          <div className="mt-1 flex flex-wrap gap-1.5"><Badge>{STATUS[book.status]}</Badge>{book.rating && <Badge tone="amber"><Star className="h-3 w-3" aria-hidden />{book.rating}/5</Badge>}</div>
          {book.total_pages ? (
            <>
              <ProgressBar className="mt-2" value={book.progress} label={`Page ${book.current_page} of ${book.total_pages}`} />
              <p className="mt-1 text-xs text-muted">Page {book.current_page} of {book.total_pages}{book.minutes_total ? ` · ${minutesLabel(book.minutes_total)} read` : ""}</p>
            </>
          ) : book.minutes_total ? <p className="mt-1 text-xs text-muted">{minutesLabel(book.minutes_total)} read</p> : null}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {book.status !== "completed" && <Button size="sm" icon={<Play className="h-4 w-4" aria-hidden />} onClick={start} loading={mut.isPending}>Start timer</Button>}
        <Button size="sm" variant="soft" onClick={onLog}>Log time</Button>
        <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
        {book.status === "reading" && <Button size="sm" variant="ghost" onClick={() => setConfirmDone(true)}>Finished it</Button>}
        {book.status === "reading" && <Button size="sm" variant="ghost" icon={<Pause className="h-4 w-4" aria-hidden />} onClick={() => mut.mutate(() => api.patch(`/reading/books/${book.id}/`, { status: "paused" }))}>Pause</Button>}
      </div>
      <ConfirmDialog open={confirmDone} onOpenChange={setConfirmDone} title={`Finished “${book.title}”?`} description="It'll move to your finished shelf and count towards your yearly goal."
        confirmLabel="Mark as finished" onConfirm={() => mut.mutate(() => api.post(`/reading/books/${book.id}/complete/`), { onSuccess: () => { setConfirmDone(false); toast.success("Congratulations on finishing it!"); } })} />
    </Card>
  );
}

function BookForm({ book, onClose }: { book: Book | null; onClose: () => void }) {
  const mut = useReadingMutation();
  const [v, setV] = useState({
    title: book?.title ?? "", author: book?.author ?? "", category: book?.category ?? "", status: book?.status ?? "reading",
    total_pages: book?.total_pages ? String(book.total_pages) : "", current_page: String(book?.current_page ?? 0), target_date: book?.target_date ?? "",
    daily_goal_minutes: book?.daily_goal_minutes ? String(book.daily_goal_minutes) : "", cover_url: book?.cover_url ?? "", rating: book?.rating ? String(book.rating) : "",
    notes: book?.notes ?? "", review: book?.review ?? "",
  });
  const [error, setError] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!v.title.trim()) return setError("Add the book's title.");
    const body = { ...v, total_pages: v.total_pages ? Number(v.total_pages) : null, current_page: Number(v.current_page || 0), target_date: v.target_date || null,
      daily_goal_minutes: v.daily_goal_minutes ? Number(v.daily_goal_minutes) : null, rating: v.rating ? Number(v.rating) : null };
    mut.mutate(() => (book ? api.patch(`/reading/books/${book.id}/`, body) : api.post("/reading/books/", body)), { onSuccess: onClose, onError: (err) => setError((err as Error).message) });
  };
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setV({ ...v, [k]: e.target.value });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={book ? "Edit book" : "Add a book"} size="lg"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="book-form" loading={mut.isPending}>Save</Button></>}>
      <form id="book-form" onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><FormError message={error} /></div>
        <Field label="Title" className="sm:col-span-2">{({ id }) => <Input id={id} value={v.title} onChange={set("title")} autoFocus />}</Field>
        <Field label="Author" optional>{({ id }) => <Input id={id} value={v.author} onChange={set("author")} />}</Field>
        <Field label="Status">{({ id }) => <Select id={id} value={v.status} onChange={set("status")}>{Object.entries(STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        <Field label="Total pages" optional>{({ id }) => <Input id={id} type="number" min={1} value={v.total_pages} onChange={set("total_pages")} />}</Field>
        <Field label="Current page">{({ id }) => <Input id={id} type="number" min={0} value={v.current_page} onChange={set("current_page")} />}</Field>
        <Field label="Finish by" optional>{({ id }) => <Input id={id} type="date" value={v.target_date} onChange={set("target_date")} />}</Field>
        <Field label="Daily goal (min)" optional>{({ id }) => <Input id={id} type="number" min={1} value={v.daily_goal_minutes} onChange={set("daily_goal_minutes")} />}</Field>
        <Field label="Category" optional>{({ id }) => <Input id={id} value={v.category} onChange={set("category")} />}</Field>
        <Field label="Rating" optional>{({ id }) => <Select id={id} value={v.rating} onChange={set("rating")}><option value="">—</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} / 5</option>)}</Select>}</Field>
        <Field label="Cover image URL" optional className="sm:col-span-2">{({ id }) => <Input id={id} type="url" value={v.cover_url} onChange={set("cover_url")} />}</Field>
        <Field label="Notes" optional className="sm:col-span-2">{({ id }) => <Textarea id={id} rows={2} value={v.notes} onChange={set("notes")} />}</Field>
        <Field label="Review" optional className="sm:col-span-2">{({ id }) => <Textarea id={id} rows={2} value={v.review} onChange={set("review")} />}</Field>
      </form>
    </Dialog>
  );
}

function LogSession({ book, onClose }: { book: Book; onClose: () => void }) {
  const { prefs } = useSession();
  const mut = useReadingMutation();
  const toast = useToast();
  const [v, setV] = useState({ date: todayIn(prefs.time_zone), duration_minutes: "20", start_page: book.current_page ? String(book.current_page) : "", end_page: "", notes: "" });
  const [error, setError] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    mut.mutate(() => api.post("/reading/sessions/", {
      book: book.id, date: v.date, duration_minutes: Number(v.duration_minutes), start_page: v.start_page ? Number(v.start_page) : null,
      end_page: v.end_page ? Number(v.end_page) : null, notes: v.notes,
    }), { onSuccess: () => { toast.success("Reading logged"); onClose(); }, onError: (err) => setError((err as Error).message) });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Log reading — ${book.title}`} description="Forgot to start the timer? Add the session here."
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="log-form" loading={mut.isPending}>Save session</Button></>}>
      <form id="log-form" onSubmit={submit} className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><FormError message={error} /></div>
        <Field label="Date">{({ id }) => <Input id={id} type="date" max={todayIn(prefs.time_zone)} value={v.date} onChange={(e) => setV({ ...v, date: e.target.value })} />}</Field>
        <Field label="Minutes">{({ id }) => <Input id={id} type="number" min={1} max={720} value={v.duration_minutes} onChange={(e) => setV({ ...v, duration_minutes: e.target.value })} />}</Field>
        <Field label="From page" optional>{({ id }) => <Input id={id} type="number" min={0} value={v.start_page} onChange={(e) => setV({ ...v, start_page: e.target.value })} />}</Field>
        <Field label="To page" optional>{({ id }) => <Input id={id} type="number" min={0} value={v.end_page} onChange={(e) => setV({ ...v, end_page: e.target.value })} />}</Field>
        <Field label="Notes" optional className="col-span-2">{({ id }) => <Textarea id={id} rows={2} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />}</Field>
      </form>
    </Dialog>
  );
}

function BookNotes({ book, onClose }: { book: Book; onClose: () => void }) {
  const notes = useBookNotes(book.id);
  const mut = useReadingMutation();
  const [text, setText] = useState("");
  const [kind, setKind] = useState("note");
  const [page, setPage] = useState("");
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    mut.mutate(() => api.post(`/reading/books/${book.id}/notes/`, { kind, text, page: page ? Number(page) : null }), { onSuccess: () => { setText(""); setPage(""); notes.refetch(); } });
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={book.title} description="Notes, highlights and favourite quotes" size="lg">
      <form onSubmit={add} className="mb-4 flex flex-col gap-2">
        <div className="grid grid-cols-[1fr_6rem] gap-2">
          <Select aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value)}><option value="note">Note</option><option value="highlight">Highlight</option><option value="quote">Favourite quote</option></Select>
          <Input aria-label="Page" placeholder="Page" type="number" min={0} value={page} onChange={(e) => setPage(e.target.value)} />
        </div>
        <Textarea aria-label="Text" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write something you want to remember" />
        <Button type="submit" size="sm" loading={mut.isPending} className="self-end">Add</Button>
      </form>
      {notes.isPending ? <LoadingList rows={2} /> : (notes.data ?? []).length === 0 ? <p className="text-sm text-muted">Nothing saved yet.</p> : (
        <ul className="flex flex-col gap-2">
          {notes.data!.map((n) => (
            <li key={n.id} className="rounded-xl border border-line p-3 text-sm">
              <p className="mb-1 flex items-center gap-1.5 text-xs text-muted">{n.kind === "quote" && <Quote className="h-3 w-3" aria-hidden />}{n.kind}{n.page ? ` · p. ${n.page}` : ""}</p>
              <p className="whitespace-pre-wrap">{n.text}</p>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function RecentSessions() {
  const { prefs } = useSession();
  const s = useReadingSessions();
  const list = (s.data?.results ?? []).filter((x) => x.ended_at);
  if (!list.length) return null;
  return (
    <Card>
      <CardHeader title="Recent sessions" icon={Timer} />
      <ul className="divide-y divide-line text-sm">
        {list.slice(0, 8).map((x) => (
          <li key={x.id} className="flex justify-between gap-2 py-2">
            <span>{formatDate(x.date, prefs, "weekday")} · {x.book_title}</span>
            <span className="text-muted">{minutesLabel(x.duration_minutes)}{x.pages_read ? ` · ${x.pages_read} pages` : ""}{x.source === "manual" ? " · logged" : ""}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
