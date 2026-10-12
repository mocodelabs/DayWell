import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/features/auth/session";
import { keys } from "@/hooks/queries";
import { api } from "@/lib/api";
import { WEEKDAYS_LONG } from "@/lib/datetime";
import type { Me } from "@/lib/types";
import { useSettingSaver } from "./useSettingSaver";

export default function Profile() {
  const { user, prefs } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const { save } = useSettingSaver();
  const [name, setName] = useState(user.display_name);
  const zones = useMemo(() => {
    try {
      return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone");
    } catch {
      return [prefs.time_zone];
    }
  }, [prefs.time_zone]);
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const saveName = async () => {
    try {
      const me = await api.patch<Me>("/auth/me/", { display_name: name.trim() });
      qc.setQueryData(keys.me, me);
      toast.success("Name saved");
    } catch (e) {
      toast.error("Couldn't save", (e as Error).message);
    }
  };
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader title="Profile" />
        <div className="flex flex-col gap-3">
          <Field label="Display name" hint="Used in your greeting.">
            {({ id, describedBy }) => (
              <div className="flex gap-2"><Input id={id} aria-describedby={describedBy} value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /><Button variant="secondary" onClick={saveName}>Save</Button></div>
            )}
          </Field>
          <p className="text-sm text-muted">Email: {user.email} {user.email_verified ? "· confirmed" : "· not confirmed yet"}</p>
          {!user.email_verified && (
            <Button size="sm" variant="ghost" className="self-start" onClick={() => api.post("/auth/email/verify/resend/").then(() => toast.success("Confirmation email sent"))}>Resend confirmation email</Button>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader title="Region & formats" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Time zone" hint={browserZone !== prefs.time_zone ? `This device is set to ${browserZone}.` : "Matches this device."}>
            {({ id, describedBy }) => (
              <Select id={id} aria-describedby={describedBy} value={prefs.time_zone} onChange={(e) => save({ time_zone: e.target.value }, "Time zone updated — reminders and habits now follow it")}>
                {zones.map((z) => <option key={z} value={z}>{z.replaceAll("_", " ")}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Time format">
            {({ id }) => <Select id={id} value={prefs.time_format} onChange={(e) => save({ time_format: e.target.value as "24h" })}><option value="24h">24-hour (14:30)</option><option value="12h">12-hour (2:30 PM)</option></Select>}
          </Field>
          <Field label="Date format">
            {({ id }) => <Select id={id} value={prefs.date_format} onChange={(e) => save({ date_format: e.target.value as "DMY" })}><option value="DMY">31/12/2026</option><option value="MDY">12/31/2026</option><option value="YMD">2026-12-31</option></Select>}
          </Field>
          <Field label="Week starts on">
            {({ id }) => <Select id={id} value={prefs.week_start} onChange={(e) => save({ week_start: Number(e.target.value) })}>{WEEKDAYS_LONG.map((d, i) => <option key={d} value={i}>{d}</option>)}</Select>}
          </Field>
          <Field label="Language & number format">
            {({ id }) => <Select id={id} value={prefs.locale} onChange={(e) => save({ locale: e.target.value })}><option value="en">English</option><option value="en-GB">English (UK)</option><option value="en-US">English (US)</option></Select>}
          </Field>
        </div>
        {browserZone !== prefs.time_zone && (
          <Button size="sm" variant="soft" className="mt-3" onClick={() => save({ time_zone: browserZone }, "Time zone updated")}>Use this device's time zone ({browserZone})</Button>
        )}
        <p className="mt-3 text-xs text-muted">Changing your time zone moves your habit and personal reminders with you (07:00 stays 07:00). Calendar events keep the time zone they were created in.</p>
      </Card>
    </div>
  );
}
