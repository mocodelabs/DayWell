import { describe, expect, it, vi } from "vitest";
import { alarmAudio } from "./audio";
import { addDays, formatWallTime, isoToZoned, localDateOf, percent, startOfWeek, zonedToIso } from "./datetime";
import { parseQuickEntry } from "./quickparse";
import { describeRRule, parseRRule, toRRule, EMPTY_RECURRENCE } from "./recurrence";

const TODAY = "2026-10-09"; // a Friday

describe("quick entry parser", () => {
  it("understands the PRD example", () => {
    const p = parseQuickEntry("Call the supplier tomorrow at 10 AM and remind me 15 minutes before", TODAY);
    expect(p).toMatchObject({ title: "Call the supplier", date: "2026-10-10", time: "10:00", reminderMinutes: 15, ambiguous: [] });
  });

  it("handles weekdays, pm times and repeats", () => {
    expect(parseQuickEntry("Gym every monday at 6pm", TODAY)).toMatchObject({ title: "Gym", date: "2026-10-12", time: "18:00", rrule: "FREQ=WEEKLY;BYDAY=MO" });
    expect(parseQuickEntry("Dentist on Friday 3:30 pm", TODAY)).toMatchObject({ date: "2026-10-16", time: "15:30" });
    expect(parseQuickEntry("Standup every weekday at 09:15", TODAY).rrule).toBe("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR");
  });

  it("never applies an ambiguous numeric date", () => {
    const p = parseQuickEntry("Pay rent 5/6", TODAY);
    expect(p.date).toBeNull();
    expect(p.ambiguous[0]).toMatch(/day\/month or month\/day/);
  });

  it("explains 24-hour assumptions instead of silently guessing", () => {
    const p = parseQuickEntry("Call mum at 7", TODAY);
    expect(p.time).toBe("07:00");
    expect(p.notes.join(" ")).toMatch(/24-hour/);
  });

  it("parses month names, rolling into next year when past", () => {
    expect(parseQuickEntry("Renew passport 12 Oct", TODAY).date).toBe("2026-10-12");
    expect(parseQuickEntry("Book flights Jan 3", TODAY).date).toBe("2027-01-03");
  });

  it("leaves plain titles alone", () => {
    expect(parseQuickEntry("Buy milk", TODAY)).toMatchObject({ title: "Buy milk", date: null, time: null, reminderMinutes: null });
  });
});

describe("recurrence", () => {
  it("round-trips structured values", () => {
    const rule = toRRule({ ...EMPTY_RECURRENCE, freq: "WEEKLY", byDay: [0, 2, 4], end: "count", count: 10 });
    expect(rule).toBe("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10");
    expect(parseRRule(rule)).toMatchObject({ freq: "WEEKLY", byDay: [0, 2, 4], end: "count", count: 10 });
  });
  it("describes rules in plain language", () => {
    expect(describeRRule("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")).toBe("Every weekday");
    expect(describeRRule("FREQ=MONTHLY;BYMONTHDAY=5")).toBe("Every month on day 5");
    expect(describeRRule("FREQ=WEEKLY;INTERVAL=2")).toBe("Every 2 weeks");
    expect(describeRRule("FREQ=DAILY;UNTIL=20261231")).toBe("Every day, until 2026-12-31");
    expect(describeRRule("")).toBe("Does not repeat");
  });
});

describe("date & time helpers", () => {
  it("converts wall time in a zone to UTC, across DST", () => {
    expect(zonedToIso("2026-10-09", "09:00", "Africa/Nairobi")).toBe("2026-10-09T06:00:00.000Z");
    expect(zonedToIso("2026-07-01", "09:00", "America/New_York")).toBe("2026-07-01T13:00:00.000Z");
    expect(zonedToIso("2026-12-01", "09:00", "America/New_York")).toBe("2026-12-01T14:00:00.000Z");
    expect(isoToZoned("2026-10-09T06:00:00Z", "Africa/Nairobi")).toEqual({ date: "2026-10-09", time: "09:00" });
  });
  it("uses the user's zone for the local date, not the device's", () => {
    expect(localDateOf(new Date("2026-10-09T22:30:00Z"), "Africa/Nairobi")).toBe("2026-10-10");
    expect(localDateOf(new Date("2026-10-09T22:30:00Z"), "America/New_York")).toBe("2026-10-09");
  });
  it("formats and does calendar maths", () => {
    expect(formatWallTime("14:05", { time_format: "12h" })).toBe("2:05 PM");
    expect(formatWallTime("00:30", { time_format: "12h" })).toBe("12:30 AM");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(startOfWeek(TODAY, 0)).toBe("2026-10-05");
    expect(startOfWeek(TODAY, 6)).toBe("2026-10-04");
    expect(percent(null)).toBe("—");
    expect(percent(0.333)).toBe("33%");
  });
});

describe("alarm audio", () => {
  it("reports blocked playback honestly and never double-plays", async () => {
    const play = vi.fn().mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError")).mockResolvedValue(undefined);
    class FakeAudio {
      loop = false; volume = 1; paused = true; currentTime = 0; src: string;
      constructor(src: string) { this.src = src; }
      play() { this.paused = false; return play(); }
      pause() { this.paused = true; }
    }
    vi.stubGlobal("Audio", FakeAudio);
    expect(await alarmAudio.play("occ-1", "chime", 80)).toBe("blocked");
    expect(await alarmAudio.play("occ-1", "chime", 80)).toBe("played");
    expect(await alarmAudio.play("occ-1", "chime", 80)).toBe("played"); // already ringing → no second element
    expect(play).toHaveBeenCalledTimes(2);
    alarmAudio.stop();
    expect(alarmAudio.playing).toBe(false);
    vi.unstubAllGlobals();
  });
});
