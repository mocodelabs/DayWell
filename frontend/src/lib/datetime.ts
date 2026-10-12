/**
 * Date/time helpers. All display goes through Intl with the user's IANA zone and preferences, so the browser's own
 * zone never leaks into what the user sees. Wall-clock values ("2026-10-09", "09:00") are passed through untouched.
 */
import type { Preferences } from "./types";

type Prefs = Pick<Preferences, "time_zone" | "time_format" | "date_format" | "locale" | "week_start">;

export function formatTime(iso: string | Date, prefs: Prefs): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat(prefs.locale || "en", {
    hour: "numeric", minute: "2-digit", hour12: prefs.time_format === "12h", timeZone: prefs.time_zone,
  }).format(d);
}

/** "09:00" (wall clock, already local) → user's format. */
export function formatWallTime(hhmm: string | null | undefined, prefs: Pick<Preferences, "time_format">): string {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  if (prefs.time_format === "12h") {
    const suffix = h >= 12 ? "PM" : "AM";
    return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${suffix}`;
  }
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function formatDate(isoDate: string, prefs: Prefs, style: "short" | "long" | "weekday" = "short"): string {
  const [y, mo, d] = isoDate.slice(0, 10).split("-").map(Number);
  const date = new Date(Date.UTC(y, mo - 1, d, 12));
  if (style === "long") {
    return new Intl.DateTimeFormat(prefs.locale || "en", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(date);
  }
  if (style === "weekday") {
    return new Intl.DateTimeFormat(prefs.locale || "en", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(date);
  }
  const p = (n: number) => String(n).padStart(2, "0");
  if (prefs.date_format === "MDY") return `${p(mo)}/${p(d)}/${y}`;
  if (prefs.date_format === "YMD") return `${y}-${p(mo)}-${p(d)}`;
  return `${p(d)}/${p(mo)}/${y}`;
}

export function formatDateTime(iso: string, prefs: Prefs): string {
  const d = new Date(iso);
  return `${formatDate(localDateOf(d, prefs.time_zone), prefs, "weekday")}, ${formatTime(d, prefs)}`;
}

/** The user's local calendar date (YYYY-MM-DD) for an instant. */
export function localDateOf(d: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function todayIn(timeZone: string): string {
  return localDateOf(new Date(), timeZone);
}

export function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days, 12));
  return dt.toISOString().slice(0, 10);
}

export function weekdayOf(isoDate: string): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay() + 6) % 7; // 0 = Monday
}

export function startOfWeek(isoDate: string, weekStart: number): string {
  return addDays(isoDate, -((weekdayOf(isoDate) - weekStart + 7) % 7));
}

export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const WEEKDAYS_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function relativeMinutes(iso: string, now = Date.now()): string {
  const diff = Math.round((new Date(iso).getTime() - now) / 60000);
  if (Math.abs(diff) < 1) return "now";
  const abs = Math.abs(diff);
  const text = abs < 60 ? `${abs} min` : abs < 1440 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} d`;
  return diff > 0 ? `in ${text}` : `${text} ago`;
}

export function minutesLabel(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function percent(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? "—" : `${Math.round(rate * 100)}%`;
}

/** Wall-clock date+time in the user's zone → ISO instant (used for deadlines and sleep logs). */
export function zonedToIso(date: string, time: string, timeZone: string): string {
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  let guess = Date.UTC(y, mo - 1, d, h, mi);
  for (let i = 0; i < 3; i++) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).formatToParts(new Date(guess));
    const g = (t: string) => Number(parts.find((p) => p.type === t)?.value);
    const shown = Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute"));
    const want = Date.UTC(y, mo - 1, d, h, mi);
    if (shown === want) break;
    guess += want - shown;
  }
  return new Date(guess).toISOString();
}

/** ISO instant → {date, time} wall clock in a zone. */
export function isoToZoned(iso: string, timeZone: string): { date: string; time: string } {
  const d = new Date(iso);
  const time = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d);
  return { date: localDateOf(d, timeZone), time };
}
