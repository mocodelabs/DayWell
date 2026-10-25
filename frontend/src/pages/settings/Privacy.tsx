import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, LogOut, Monitor } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Card, CardHeader } from "@/components/ui/feedback";
import { Field, FormError, Input, Switch } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession, useSignOut } from "@/features/auth/session";
import { keys } from "@/hooks/queries";
import { api, ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { useSettingSaver } from "./useSettingSaver";

interface SessionRow { session_key: string; user_agent: string; ip_address: string | null; created_at: string; last_seen_at: string; current: boolean }

export default function Privacy() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<SessionRow[]>("/auth/sessions/") });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [pwError, setPwError] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [del, setDel] = useState({ password: "", confirm: "" });
  const [delError, setDelError] = useState("");

  const logout = useSignOut();
  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError("");
    try {
      await api.post("/auth/password/change/", pw);
      setPw({ current_password: "", new_password: "" });
      toast.success("Password changed", "Your other sessions were signed out.");
      void sessions.refetch();
    } catch (err) {
      setPwError(err instanceof ApiError ? Object.values(err.fields).flat().join(" ") || err.message : "Something went wrong.");
    }
  };
  const exportData = async () => {
    try {
      const data = await api.get<unknown>("/account/export/");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `daywell-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Export ready", "Your data was downloaded as a JSON file.");
    } catch (err) {
      toast.error("Export failed", (err as Error).message);
    }
  };
  const deleteAccount = async () => {
    setDelError("");
    try {
      await api.post("/account/delete/", del);
      qc.clear();
      qc.setQueryData(keys.me, null);
      navigate("/login", { replace: true });
    } catch (err) {
      setDelError(err instanceof ApiError ? Object.values(err.fields).flat().join(" ") || err.message : "Something went wrong.");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader title="Privacy" />
        <p className="mb-2 text-sm text-muted">Everything you add is private to your account. There are no public profiles, and your activity data is never sold.</p>
        <Switch label="AI-generated suggestions" description="Not available in this version. When added, it will be off unless you turn it on, and it will never change your calendar without asking."
          checked={prefs.ai_suggestions_enabled} disabled onCheckedChange={(v) => save({ ai_suggestions_enabled: v })} />
        <Switch label="Allow journal entries to be used by AI features" description="Off by default. Journal entries are never sent to third parties without this consent."
          checked={prefs.journal_ai_consent} onCheckedChange={(v) => save({ journal_ai_consent: v })} />
      </Card>
      <Card>
        <CardHeader title="Your data" />
        <p className="mb-3 text-sm text-muted">Download a complete copy of your data (tasks, calendar, reminders and history, habits, reading, workouts, journal and more) as JSON.</p>
        <Button variant="secondary" icon={<Download className="h-4 w-4" aria-hidden />} onClick={exportData}>Export my data</Button>
      </Card>
      <Card>
        <CardHeader title="Active sessions" action={<Button size="sm" variant="secondary" icon={<LogOut className="h-4 w-4" aria-hidden />} onClick={logout}>Sign out</Button>} />
        <ul className="divide-y divide-line">
          {sessions.data?.map((s) => (
            <li key={s.session_key} className="flex items-center gap-3 py-2 text-sm">
              <Monitor className="h-5 w-5 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate">{s.user_agent || "Unknown device"}{s.current && <span className="ml-2 text-primary">(this device)</span>}</p>
                <p className="text-xs text-muted">Signed in {formatDateTime(s.created_at, prefs)} · last active {formatDateTime(s.last_seen_at, prefs)}{s.ip_address ? ` · ${s.ip_address}` : ""}</p>
              </div>
              {!s.current && <Button size="sm" variant="ghost" onClick={() => api.delete(`/auth/sessions/${s.session_key}/`).then(() => sessions.refetch())}>Sign out</Button>}
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Change password" />
        <form onSubmit={changePassword} className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2"><FormError message={pwError} /></div>
          <Field label="Current password">{({ id }) => <Input id={id} type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />}</Field>
          <Field label="New password" hint="At least 10 characters.">{({ id, describedBy }) => <Input id={id} type="password" autoComplete="new-password" aria-describedby={describedBy} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />}</Field>
          <Button type="submit" className="sm:col-span-2 sm:justify-self-start">Change password</Button>
        </form>
      </Card>
      <Card className="border-danger/40">
        <CardHeader title="Delete account" />
        <p className="mb-3 text-sm text-muted">Permanently deletes your account and all of your data. This can't be undone — consider exporting first.</p>
        <Button variant="danger" onClick={() => setDeleteOpen(true)}>Delete my account</Button>
      </Card>
      <ConfirmDialog open={deleteOpen} onOpenChange={setDeleteOpen} danger title="Delete your account?" confirmLabel="Delete everything" onConfirm={deleteAccount}
        description="All tasks, events, reminders, habits, journal entries and history will be permanently removed.">
        <div className="flex flex-col gap-3">
          <FormError message={delError} />
          <Field label="Your password">{({ id }) => <Input id={id} type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />}</Field>
          <Field label="Type DELETE to confirm">{({ id }) => <Input id={id} value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} />}</Field>
        </div>
      </ConfirmDialog>
    </div>
  );
}
