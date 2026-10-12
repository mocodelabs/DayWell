/**
 * Structured recurrence ⇄ RFC 5545 RRULE. The server validates and expands; this only builds and describes rules.
 */
export type Freq = "none" | "DAILY" | "WEEKLY" | "MONTHLY" | "YEARLY" | "WEEKDAYS";

export interface RecurrenceValue {
  freq: Freq;
  interval: number;
  byDay: number[]; // 0=Mon … 6=Sun (WEEKLY)
  monthDay: number | null; // MONTHLY on day N
  end: "never" | "until" | "count";
  until: string; // YYYY-MM-DD
  count: number;
}

export const CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const EMPTY_RECURRENCE: RecurrenceValue = { freq: "none", interval: 1, byDay: [], monthDay: null, end: "never", until: "", count: 10 };

export function toRRule(v: RecurrenceValue): string {
  if (v.freq === "none") return "";
  const parts: string[] = [];
  if (v.freq === "WEEKDAYS") {
    parts.push("FREQ=WEEKLY", "BYDAY=MO,TU,WE,TH,FR");
  } else {
    parts.push(`FREQ=${v.freq}`);
    if (v.interval > 1) parts.push(`INTERVAL=${v.interval}`);
    if (v.freq === "WEEKLY" && v.byDay.length) parts.push(`BYDAY=${[...v.byDay].sort().map((d) => CODES[d]).join(",")}`);
    if (v.freq === "MONTHLY" && v.monthDay) parts.push(`BYMONTHDAY=${v.monthDay}`);
  }
  if (v.end === "count" && v.count > 0) parts.push(`COUNT=${v.count}`);
  if (v.end === "until" && v.until) parts.push(`UNTIL=${v.until.replaceAll("-", "")}`);
  return parts.join(";");
}

export function parseRRule(rule: string | null | undefined): RecurrenceValue {
  if (!rule) return { ...EMPTY_RECURRENCE };
  const map = Object.fromEntries(rule.replace(/^RRULE:/, "").split(";").map((p) => p.split("=") as [string, string]));
  const v: RecurrenceValue = { ...EMPTY_RECURRENCE, freq: (map.FREQ as Freq) ?? "none" };
  v.interval = map.INTERVAL ? Number(map.INTERVAL) : 1;
  v.byDay = map.BYDAY ? map.BYDAY.split(",").map((c: string) => CODES.indexOf(c)).filter((i: number) => i >= 0) : [];
  v.monthDay = map.BYMONTHDAY ? Number(map.BYMONTHDAY) : null;
  if (v.freq === "WEEKLY" && v.interval === 1 && v.byDay.join(",") === "0,1,2,3,4") v.freq = "WEEKDAYS";
  if (map.COUNT) {
    v.end = "count";
    v.count = Number(map.COUNT);
  } else if (map.UNTIL) {
    v.end = "until";
    const u = map.UNTIL.slice(0, 8);
    v.until = `${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`;
  }
  return v;
}

function listDays(days: number[]): string {
  const names = days.map((d) => NAMES[d]);
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function describeRRule(rule: string | null | undefined): string {
  if (!rule) return "Does not repeat";
  const v = parseRRule(rule);
  let text: string;
  if (rule.includes("FREQ=HOURLY")) {
    text = "Several times a day";
  } else if (v.freq === "WEEKDAYS") {
    text = "Every weekday";
  } else {
    const unit = { DAILY: "day", WEEKLY: "week", MONTHLY: "month", YEARLY: "year", none: "", WEEKDAYS: "" }[v.freq];
    text = v.interval > 1 ? `Every ${v.interval} ${unit}s` : `Every ${unit}`;
    if (v.freq === "WEEKLY" && v.byDay.length) text += v.byDay.length === 7 ? " (every day)" : ` on ${listDays(v.byDay)}`;
    if (v.freq === "MONTHLY" && v.monthDay) text += ` on day ${v.monthDay}`;
    if (v.freq === "DAILY" && v.interval === 1) text = "Every day";
  }
  if (v.end === "count") text += `, ${v.count} times`;
  if (v.end === "until" && v.until) text += `, until ${v.until}`;
  return text;
}

export function daysToRRule(days: number[]): string {
  if (days.length === 0 || days.length === 7) return "FREQ=DAILY";
  return `FREQ=WEEKLY;BYDAY=${[...days].sort().map((d) => CODES[d]).join(",")}`;
}
