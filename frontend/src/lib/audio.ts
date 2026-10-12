/**
 * Foreground alarm audio. One shared controller so two alarms can never play on top of each other.
 *
 * Browsers block audio until the user has interacted with the page. ``play`` therefore reports what really happened:
 * "played" only when the play() promise resolved; "blocked" when the browser refused. We never claim an alarm sounded.
 */
export type AudioOutcome = "played" | "blocked" | "unsupported";

export const SOUNDS = ["chime", "bell", "marimba", "birdsong", "soft-pulse", "classic"] as const;
export const SOUND_LABELS: Record<string, string> = {
  chime: "Chime", bell: "Bell", marimba: "Marimba", birdsong: "Birdsong", "soft-pulse": "Soft pulse", classic: "Classic alarm",
};

class AlarmAudio {
  private el: HTMLAudioElement | null = null;
  private currentKey: string | null = null;
  private unlocked = false;

  get playing(): boolean {
    return !!this.el && !this.el.paused;
  }

  get key(): string | null {
    return this.currentKey;
  }

  /** Call from a user gesture to satisfy autoplay policies for later alarms. */
  async unlock(): Promise<void> {
    if (this.unlocked || typeof Audio === "undefined") return;
    try {
      const a = new Audio("/sounds/soft-pulse.wav");
      a.volume = 0;
      await a.play();
      a.pause();
      this.unlocked = true;
    } catch {
      /* still locked; we'll report "blocked" honestly when an alarm tries to ring */
    }
  }

  isUnlocked(): boolean {
    return this.unlocked;
  }

  async play(key: string, sound: string, volume: number, loop = true): Promise<AudioOutcome> {
    if (typeof Audio === "undefined") return "unsupported";
    if (this.currentKey === key && this.playing) return "played"; // already ringing this alarm — never double up
    this.stop();
    const el = new Audio(`/sounds/${SOUNDS.includes(sound as (typeof SOUNDS)[number]) ? sound : "chime"}.wav`);
    el.loop = loop;
    el.volume = Math.max(0, Math.min(1, volume / 100));
    this.el = el;
    this.currentKey = key;
    try {
      await el.play();
      this.unlocked = true;
      return "played";
    } catch {
      this.el = null;
      this.currentKey = null;
      return "blocked";
    }
  }

  stop(): void {
    if (this.el) {
      this.el.pause();
      this.el.currentTime = 0;
      this.el.src = "";
    }
    this.el = null;
    this.currentKey = null;
  }

  /** Short, non-looping preview (settings). */
  preview(sound: string, volume: number): Promise<AudioOutcome> {
    return this.play(`preview:${sound}:${Date.now()}`, sound, volume, false);
  }
}

export const alarmAudio = new AlarmAudio();

export function vibrate(pattern: number[] = [300, 150, 300]): boolean {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) {
    try {
      return navigator.vibrate(pattern);
    } catch {
      return false;
    }
  }
  return false;
}
