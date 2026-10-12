import { useToast } from "@/components/ui/Toast";
import { useUpdatePreferences } from "@/hooks/queries";
import type { Preferences } from "@/lib/types";

/** Save one or more preference fields immediately, with a quiet confirmation. */
export function useSettingSaver() {
  const update = useUpdatePreferences();
  const toast = useToast();
  const save = (patch: Partial<Preferences>, message = "Saved") =>
    update.mutate(patch, {
      onSuccess: () => toast.success(message),
      onError: (e) => toast.error("Couldn't save", (e as Error).message),
    });
  return { save, saving: update.isPending };
}
