import clsx from "clsx";
import { Download, PlusSquare, Share } from "lucide-react";
import { useState } from "react";
import { promptInstall, useInstallMode } from "@/lib/install";
import { Dialog } from "./ui/Dialog";
import { useToast } from "./ui/Toast";

type Variant = "button" | "icon" | "menu" | "sidebar";

/**
 * DayWell's own "Install app" control. Renders nothing when the app is already installed or the browser can't install it
 * (e.g. desktop Firefox); on iPhone/iPad it opens short "Add to Home Screen" instructions instead.
 */
export function InstallApp({ variant = "button", collapsed = false, className }: { variant?: Variant; collapsed?: boolean; className?: string }) {
  const mode = useInstallMode();
  const toast = useToast();
  const [iosHelp, setIosHelp] = useState(false);
  if (mode === "installed" || mode === "unavailable") return null;

  const onClick = async () => {
    if (mode === "ios") {
      setIosHelp(true);
      return;
    }
    const outcome = await promptInstall();
    if (outcome === "accepted") toast.success("DayWell is installing", "Open it from your home screen or app list.");
  };

  const label = "Install app";
  const styles: Record<Variant, string> = {
    button: "inline-flex h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-control)] border border-primary bg-sage-soft px-4 text-sm font-semibold text-primary-strong hover:bg-sage",
    icon: "inline-flex min-h-8 items-center gap-1 rounded-full border border-line bg-surface px-2.5 text-xs font-semibold text-primary-strong hover:bg-sage-soft",
    menu: "flex w-full items-center justify-center gap-2 rounded-xl border border-primary bg-sage-soft p-3 text-sm font-medium text-primary-strong",
    sidebar: clsx("flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-primary-strong hover:bg-sage-soft", collapsed && "justify-center px-0"),
  };

  return (
    <>
      <button type="button" onClick={onClick} className={clsx(styles[variant], className)} aria-label={variant === "icon" || collapsed ? "Install DayWell app" : undefined}
        title={collapsed ? label : undefined}>
        <Download className={variant === "icon" ? "h-3.5 w-3.5" : "h-5 w-5 shrink-0"} aria-hidden />
        {variant === "icon" ? "Install" : !collapsed && label}
      </button>
      <Dialog open={iosHelp} onOpenChange={setIosHelp} title="Install DayWell on your iPhone or iPad" size="sm">
        <ol className="space-y-3 text-sm">
          <li className="flex gap-3"><Share className="h-5 w-5 shrink-0 text-primary" aria-hidden />
            <span>Tap the <strong>Share</strong> button in Safari's toolbar.</span></li>
          <li className="flex gap-3"><PlusSquare className="h-5 w-5 shrink-0 text-primary" aria-hidden />
            <span>Choose <strong>Add to Home Screen</strong>, then tap <strong>Add</strong>.</span></li>
          <li className="flex gap-3"><Download className="h-5 w-5 shrink-0 text-primary" aria-hidden />
            <span>Open DayWell from your Home Screen. Notifications on iPhone work only from the installed app.</span></li>
        </ol>
      </Dialog>
    </>
  );
}
