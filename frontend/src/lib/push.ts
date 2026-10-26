/** Browser notification + Web Push helpers. Permission is only ever requested from an explicit user action. */
import { api } from "./api";

export interface PushSupport {
  notifications: boolean;
  serviceWorker: boolean;
  push: boolean;
  permission: NotificationPermission | "unsupported";
  standalone: boolean;
  ios: boolean;
}

export function pushSupport(): PushSupport {
  const hasNotif = typeof window !== "undefined" && "Notification" in window;
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  return {
    notifications: hasNotif,
    serviceWorker: typeof navigator !== "undefined" && "serviceWorker" in navigator,
    push: typeof window !== "undefined" && "PushManager" in window,
    permission: hasNotif ? Notification.permission : "unsupported",
    standalone: typeof window !== "undefined" && (window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true),
    ios: /iPad|iPhone|iPod/.test(ua),
  };
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch {
    return null; // e.g. embedded browsers without SW support; the app still works online
  }
}

export async function requestNotificationPermission(): Promise<NotificationPermission | "unsupported"> {
  if (!("Notification" in window)) return "unsupported";
  if (Notification.permission !== "default") return Notification.permission;
  return Notification.requestPermission();
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export type SubscribeResult = { ok: true } | { ok: false; reason: string };

export async function subscribeToPush(label: string): Promise<SubscribeResult> {
  const support = pushSupport();
  if (!support.serviceWorker || !support.push) {
    return { ok: false, reason: support.ios && !support.standalone
      ? "On iPhone and iPad, add DayWell to your Home Screen first (Share → Add to Home Screen), then enable notifications from the installed app."
      : "This browser doesn't support push notifications." };
  }
  const permission = await requestNotificationPermission();
  if (permission !== "granted") {
    return { ok: false, reason: permission === "denied"
      ? "Notifications are blocked for this site. You can allow them in your browser's site settings."
      : "Notification permission wasn't granted." };
  }
  const config = await api.get<{ configured: boolean; public_key: string }>("/push/config/");
  if (!config.configured) return { ok: false, reason: "Push isn't configured on this server yet. In-app alarms still work while DayWell is open." };
  const reg = (await navigator.serviceWorker.getRegistration()) ?? (await registerServiceWorker());
  if (!reg) return fail("register", null, "The service worker couldn't be registered in this browser.");
  const ready = await Promise.race([navigator.serviceWorker.ready.then(() => true), new Promise<false>((r) => setTimeout(() => r(false), 10_000))]);
  if (!ready) return fail("sw_ready", null, "DayWell's background worker didn't start. Close DayWell completely, open it again and retry.");
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    try {
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(config.public_key) });
    } catch (e) {
      const err = e as Error;
      return fail("subscribe", err, err.name === "AbortError"
        ? "Your phone's push service refused the registration. Check that Google Play services is up to date and that battery or data saver isn't restricting Chrome, then try again."
        : `The browser refused the subscription (${err.name}).`);
    }
  }
  const json = sub.toJSON();
  try {
    await api.post("/push/subscriptions/", { endpoint: json.endpoint, keys: json.keys, label });
  } catch (e) {
    return fail("save", e as Error, `DayWell couldn't save this device: ${(e as Error).message}`);
  }
  setOptIn(true);
  return { ok: true };
}

/** Tell the server which step failed (error name + browser message only — no endpoint, keys or personal data). */
function fail(stage: string, err: Error | null, reason: string): SubscribeResult {
  void api.post("/push/client-report/", { stage, error_name: err?.name ?? "", message: (err?.message ?? "").slice(0, 200) }).catch(() => undefined);
  return { ok: false, reason };
}

export async function unsubscribeFromPush(): Promise<void> {
  setOptIn(false);
  const sub = await currentSubscription();
  if (!sub) return;
  await api.post("/push/unsubscribe/", { endpoint: sub.endpoint }).catch(() => undefined);
  await sub.unsubscribe();
}

/** Show a system notification from the open page (used when the tab is hidden and push isn't available). */
export async function showLocalNotification(title: string, body: string, tag: string): Promise<boolean> {
  if (!("Notification" in window) || Notification.permission !== "granted") return false;
  try {
    const reg = await navigator.serviceWorker?.getRegistration();
    if (reg) {
      await reg.showNotification(title, { body, tag, icon: "/icons/icon-192.png", badge: "/icons/badge-96.png", requireInteraction: true });
    } else {
      new Notification(title, { body, tag, icon: "/icons/icon-192.png" });
    }
    return true;
  } catch {
    return false;
  }
}

export function deviceLabel(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return `${browser}${os ? ` on ${os}` : ""}`;
}

const OPT_IN_KEY = "dw:push-opt-in"; // per-device preference only — never sensitive data

function setOptIn(on: boolean) {
  try {
    if (on) localStorage.setItem(OPT_IN_KEY, "1");
    else localStorage.removeItem(OPT_IN_KEY);
  } catch { /* storage unavailable (private mode) — re-sync simply won't run on this device */ }
}

function optedIn(): boolean {
  try {
    return localStorage.getItem(OPT_IN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Keep the server's copy of this device's push subscription current. Browsers may rotate or drop subscriptions
 * (`pushsubscriptionchange`); without this, push would silently stop on that device. Runs on app start and when the
 * service worker reports a change. Never prompts for permission.
 */
export async function syncPushSubscription(): Promise<"synced" | "resubscribed" | "skipped"> {
  const support = pushSupport();
  if (!support.serviceWorker || !support.push || support.permission !== "granted" || !optedIn()) return "skipped";
  const sub = await currentSubscription().catch(() => null);
  if (sub) {
    const json = sub.toJSON();
    await api.post("/push/subscriptions/", { endpoint: json.endpoint, keys: json.keys, label: deviceLabel() });
    return "synced";
  }
  const res = await subscribeToPush(deviceLabel());
  return res.ok ? "resubscribed" : "skipped";
}
