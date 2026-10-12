/**
 * Rule-based quick-entry parser. It never guesses silently: everything it interpreted is listed in ``notes`` so the UI can
 * show it before saving, and genuinely ambiguous input (e.g. "5/6") is reported in ``ambiguous`` and left unapplied.
 */
import { addDays, weekdayOf } from "./datetime";

export interface QuickParse {
  title: string;
  date: string | null;
  time: string | null;
  reminderMinutes: number | null;
  priority: "low" | "normal" | "high" | "urgent" | null;
  rrule: string | null;
  notes: string[];
  ambiguous: string[];
}

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

function pad(n: number) {
  return String(n).padStart(2, "0");
}

export function parseQuickEntry(input: string, today: string): QuickParse {
  let text = ` ${input.trim()} `;
  const out: QuickParse = { title: "", date: null, time: null, reminderMinutes: null, priority: null, rrule: null, notes: [], ambiguous: [] };
  const take = (re: RegExp, fn: (m: RegExpMatchArray) => boolean | void) => {
    const m = text.match(re);
    if (m && fn(m) !== false) text = text.replace(m[0], " ");
  };

  // Reminder: "remind me 15 minutes before", "reminder 1 hour before"
  take(/\b(?:and\s+)?remind(?:er|\s+me)?\s+(\d{1,3})\s*(min(?:ute)?s?|h(?:ours?|rs?)?)\s+(?:before|earlier|ahead)\b/i, (m) => {
    const n = Number(m[1]) * (/^h/i.test(m[2]) ? 60 : 1);
    out.reminderMinutes = n;
    out.notes.push(`Reminder ${n} minutes before`);
  });

  // Priority
  take(/\s!(urgent|high|low)\b|\b(urgent)(?:ly)?\b/i, (m) => {
    out.priority = (m[1] ?? m[2]).toLowerCase() as QuickParse["priority"];
    out.notes.push(`Priority: ${out.priority}`);
  });

  // Recurrence
  take(/\bevery\s+(day|weekday|week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b/i, (m) => {
    const w = m[1].toLowerCase();
    const map: Record<string, string> = { day: "FREQ=DAILY", weekday: "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", week: "FREQ=WEEKLY", month: "FREQ=MONTHLY", year: "FREQ=YEARLY" };
    out.rrule = map[w] ?? `FREQ=WEEKLY;BYDAY=${CODES[WEEKDAYS.indexOf(w)]}`;
    out.notes.push(`Repeats every ${w}`);
    if (!map[w]) {
      const target = WEEKDAYS.indexOf(w);
      out.date = addDays(today, (target - weekdayOf(today) + 7) % 7);
    }
  });

  // Time: "at 10", "10am", "10:30 pm", "14:00", "noon", "midnight"
  take(/\b(?:at\s+)?(noon|midday|midnight)\b/i, (m) => {
    out.time = /mid(?:night)/i.test(m[1]) && m[1].toLowerCase() === "midnight" ? "00:00" : "12:00";
    out.notes.push(`Time: ${out.time}`);
  });
  if (!out.time) {
    take(/\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?=\W)/i, (m) => {
      let h = Number(m[1]);
      const min = Number(m[2] ?? 0);
      if (h < 1 || h > 12 || min > 59) return false;
      const pm = /^p/i.test(m[3]);
      if (pm && h < 12) h += 12;
      if (!pm && h === 12) h = 0;
      out.time = `${pad(h)}:${pad(min)}`;
      out.notes.push(`Time: ${out.time}`);
    });
  }
  if (!out.time) {
    take(/\bat\s+(\d{1,2})(?::(\d{2}))?\b/i, (m) => {
      const h = Number(m[1]);
      const min = Number(m[2] ?? 0);
      if (h > 23 || min > 59) return false;
      out.time = `${pad(h)}:${pad(min)}`;
      out.notes.push(h <= 12 && h >= 1 && !m[2] ? `Time: ${out.time} (24-hour clock — add "pm" if you meant the afternoon)` : `Time: ${out.time}`);
    });
  }
  if (!out.time) {
    take(/\b([01]?\d|2[0-3]):([0-5]\d)\b/, (m) => {
      out.time = `${pad(Number(m[1]))}:${m[2]}`;
      out.notes.push(`Time: ${out.time}`);
    });
  }

  // Date
  if (!out.date) {
    take(/\b(today|tonight|tomorrow|day after tomorrow)\b/i, (m) => {
      const w = m[1].toLowerCase();
      out.date = w === "tomorrow" ? addDays(today, 1) : w === "day after tomorrow" ? addDays(today, 2) : today;
      out.notes.push(`Date: ${w}`);
    });
  }
  if (!out.date) {
    take(/\bin\s+(\d{1,3})\s+(day|week)s?\b/i, (m) => {
      const n = Number(m[1]) * (m[2].toLowerCase() === "week" ? 7 : 1);
      out.date = addDays(today, n);
      out.notes.push(`Date: in ${n} days`);
    });
  }
  if (!out.date) {
    take(/\b(?:on\s+)?(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i, (m) => {
      const target = WEEKDAYS.indexOf(m[2].toLowerCase());
      let diff = (target - weekdayOf(today) + 7) % 7;
      if (diff === 0) diff = 7;
      out.date = addDays(today, diff);
      out.notes.push(`Date: ${m[1] ? "next " : ""}${m[2]}`);
    });
  }
  if (!out.date) {
    take(/\b(\d{4})-(\d{2})-(\d{2})\b/, (m) => {
      out.date = `${m[1]}-${m[2]}-${m[3]}`;
      out.notes.push(`Date: ${out.date}`);
    });
  }
  if (!out.date) {
    // "12 Oct", "Oct 12", "12th of October". Two separate passes so a non-month word ("passport 12") can't swallow
    // the day of a real date ("12 Oct").
    const patterns: [RegExp, (m: RegExpMatchArray) => [string, string]][] = [
      [/\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3,9})\b/gi, (m) => [m[1], m[2]]],
      [/\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b/gi, (m) => [m[2], m[1]]],
    ];
    search: for (const [re, pick] of patterns) {
      for (const m of text.matchAll(re)) {
        const [dayText, wordText] = pick(m);
        const day = Number(dayText);
        const word = wordText.toLowerCase();
        const mon = MONTHS.indexOf(word.slice(0, 3));
        if (mon < 0 || day < 1 || day > 31 || !MONTH_NAMES[mon].startsWith(word)) continue;
        let year = Number(today.slice(0, 4));
        if (`${year}-${pad(mon + 1)}-${pad(day)}` < today) year += 1;
        out.date = `${year}-${pad(mon + 1)}-${pad(day)}`;
        out.notes.push(`Date: ${out.date}`);
        text = text.replace(m[0], " ");
        break search;
      }
    }
  }
  // Numeric day/month is ambiguous across locales — report, don't apply.
  take(/\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b/, (m) => {
    if (out.date) return false;
    out.ambiguous.push(`“${m[0].trim()}” could be day/month or month/day — please pick the date below.`);
  });

  out.title = text.replace(/\s+(at|on|by|and)\s*$/i, "").replace(/\s{2,}/g, " ").trim();
  out.title = out.title.charAt(0).toUpperCase() + out.title.slice(1);
  return out;
}
