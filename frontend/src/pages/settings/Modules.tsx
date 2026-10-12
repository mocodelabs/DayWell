import { Card, CardHeader } from "@/components/ui/feedback";
import { Switch } from "@/components/ui/form";
import { useSession } from "@/features/auth/session";
import { MODULE_INFO } from "../Onboarding";
import { useSettingSaver } from "./useSettingSaver";

export default function Modules() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  return (
    <Card>
      <CardHeader title="Optional modules" />
      <p className="mb-2 text-sm text-muted">Turned-off modules disappear from Today and never send reminders. Your data is kept — turn a module back on and it's all still there.</p>
      <div className="divide-y divide-line">
        {MODULE_INFO.map((m) => (
          <Switch key={m.key} label={m.label} description={m.description} checked={!!prefs.modules[m.key]}
            onCheckedChange={(v) => save({ modules: { [m.key]: v } as never }, `${m.label} ${v ? "on" : "off"}`)} />
        ))}
      </div>
    </Card>
  );
}
