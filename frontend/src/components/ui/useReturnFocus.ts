import { useRef } from "react";

/**
 * Radix dialogs restore focus to their <Trigger> on close and *prevent* the default restore. DayWell opens dialogs
 * programmatically (no Trigger), so without this focus fell to <body> (WCAG 2.4.3 Focus Order).
 *
 * The element to return to is captured while rendering the first open frame — before React applies `autoFocus` inside
 * the dialog — and focus is returned there on close if it's still on the page.
 */
export function useReturnFocus(open: boolean) {
  const returnTo = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  if (open && !wasOpen.current && typeof document !== "undefined") {
    const active = document.activeElement;
    returnTo.current = active instanceof HTMLElement && active !== document.body ? active : null;
  }
  wasOpen.current = open;
  return {
    onCloseAutoFocus: (event: Event) => {
      const target = returnTo.current;
      if (target && target.isConnected) {
        event.preventDefault();
        target.focus();
      }
      returnTo.current = null;
    },
  };
}
