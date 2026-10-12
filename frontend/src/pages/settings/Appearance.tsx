import { Card, CardHeader, SegmentedControl } from "@/components/ui/feedback";
import { Switch } from "@/components/ui/form";
import { useSession } from "@/features/auth/session";
import { useSettingSaver } from "./useSettingSaver";

export default function Appearance() {
  const { prefs } = useSession();
  const { save } = useSettingSaver();
  return (
    <Card>
      <CardHeader title="Appearance & accessibility" />
      <div className="flex flex-col gap-4">
        <div>
          <p className="mb-1.5 text-sm font-medium">Theme</p>
          <SegmentedControl label="Theme" value={prefs.theme} onChange={(theme) => save({ theme })} options={[{ value: "system", label: "Match device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
        </div>
        <div>
          <p className="mb-1.5 text-sm font-medium">Text size</p>
          <SegmentedControl label="Text size" value={String(Number(prefs.text_scale))} onChange={(v) => save({ text_scale: v })}
            options={[{ value: "0.9", label: "Smaller" }, { value: "1", label: "Default" }, { value: "1.15", label: "Larger" }, { value: "1.3", label: "Largest" }]} />
        </div>
        <Switch label="Reduce motion" description="Turns off animations (your device's reduced-motion setting is always respected too)." checked={prefs.reduced_motion} onCheckedChange={(v) => save({ reduced_motion: v })} />
      </div>
    </Card>
  );
}
