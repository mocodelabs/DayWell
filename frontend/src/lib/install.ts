/**
 * "Install app" support. Chrome/Edge/Samsung Internet fire `beforeinstallprompt` once the site is installable; we keep the
 * event (and suppress the browser's own mini-infobar) so DayWell can show its own Install button. iOS Safari has no such
 * event — there we can only explain "Share → Add to Home Screen". Imported from main.tsx so the listener is attached
 * before React renders (the event can fire very early).
 */
import { useSyncExternalStore } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export type InstallMode = "prompt" | "ios" | "installed" | "unavailable";

let deferred: BeforeInstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const ios = /iPad|iPhone|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1); // iPadOS reports "Macintosh"
  return ios && /Safari\//.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // use DayWell's own button instead of the browser's mini-infobar
    deferred = e as BeforeInstallPromptEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferred = null;
    emit();
  });
}

export function installMode(): InstallMode {
  if (installed || isStandalone()) return "installed";
  if (deferred) return "prompt";
  if (isIosSafari()) return "ios";
  return "unavailable";
}

/** Show the browser's install dialog. Resolves to the user's choice; the saved event can only be used once. */
export async function promptInstall(): Promise<"accepted" | "dismissed" | "unavailable"> {
  const event = deferred;
  if (!event) return "unavailable";
  deferred = null;
  emit();
  await event.prompt();
  const { outcome } = await event.userChoice;
  if (outcome === "accepted") installed = true;
  emit();
  return outcome;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useInstallMode(): InstallMode {
  return useSyncExternalStore(subscribe, installMode, () => "unavailable");
}

/** Tests only: forget any captured install event / installed state. */
export function resetInstallState() {
  deferred = null;
  installed = false;
  emit();
}
