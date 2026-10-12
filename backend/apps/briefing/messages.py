"""Rule-based, tone-aware message templates. No AI and no invented data: every sentence is filled from real records.

Templates are deliberately varied (a stable choice per user per day, so the dashboard doesn't flicker between
reloads), supportive and never shaming. Missed items are always framed as options, not failures.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

TONES = ("warm", "calm", "direct", "energetic", "minimal")


def pick(options: list[str], seed: str) -> str:
    """Deterministic choice: same user + day + slot → same sentence; different days → variety."""
    if not options:
        return ""
    digest = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return options[digest % len(options)]


def part_of_day(local: datetime) -> str:
    h = local.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


SALUTATION = {
    "morning": "Good morning",
    "afternoon": "Good afternoon",
    "evening": "Good evening",
    "night": "Hello",
}

OPENERS = {
    ("warm", "morning"): [
        "A new day is here. Let's take it one step at a time.",
        "It's a fresh start — let's make it a kind one.",
        "Welcome to a new day. You've got this, one thing at a time.",
    ],
    ("warm", "afternoon"): ["Hope your day is going gently.", "Let's see what's next — no rush."],
    ("warm", "evening"): ["You've made it through the day. Let's look at how it went.", "Time to slow down a little."],
    ("warm", "night"): ["It's late — be kind to yourself and rest when you can."],
    ("calm", "morning"): ["Take a breath. The day unfolds one moment at a time.", "A quiet start is still a start."],
    ("calm", "afternoon"): ["Pause, breathe, and continue at your own pace."],
    ("calm", "evening"): ["The day is winding down. Let it settle."],
    ("calm", "night"): ["Rest is part of the plan too."],
    ("direct", "morning"): ["Here's your day."],
    ("direct", "afternoon"): ["Here's where things stand."],
    ("direct", "evening"): ["Here's your day in review."],
    ("direct", "night"): ["Here's where things stand."],
    ("energetic", "morning"): ["Let's make today count!", "New day, fresh energy — let's go!", "Ready when you are — let's do this!"],
    ("energetic", "afternoon"): ["Keep that momentum going!"],
    ("energetic", "evening"): ["Look at what you got done today!"],
    ("energetic", "night"): ["Big day — time to recharge!"],
}

WEEKEND = {
    "warm": ["Today has room for a little progress and a little rest."],
    "calm": ["A slower day. Enjoy the space."],
    "energetic": ["Weekend mode — fun and a bit of progress!"],
}


def greeting(name: str, local: datetime, tone: str, seed: str) -> dict:
    pod = part_of_day(local)
    sal = SALUTATION[pod]
    if local.weekday() == 5 and pod == "morning" and tone in ("warm", "energetic"):
        sal = "Happy Saturday"
    elif local.weekday() == 6 and pod == "morning" and tone in ("warm", "energetic"):
        sal = "Happy Sunday"
    headline = f"{sal}, {name}" if name else sal
    if tone == "minimal":
        return {"headline": headline, "message": "", "part_of_day": pod}
    options = list(OPENERS.get((tone, pod), OPENERS[("warm", pod)]))
    if local.weekday() >= 5 and pod == "morning":
        options += WEEKEND.get(tone, [])
    return {"headline": headline + ("!" if tone in ("warm", "energetic") else "."), "message": pick(options, seed + pod), "part_of_day": pod}


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def schedule_sentence(n_events: int, n_tasks: int, first_label: str | None, first_time: str | None, tone: str, *,
                      minutes_until: int | None = None) -> str:
    """Summarise the day. ``minutes_until`` is how long until the named commitment starts (negative = already started)."""
    if n_events == 0 and n_tasks == 0:
        return {
            "direct": "Nothing scheduled today.",
            "minimal": "Nothing scheduled.",
            "energetic": "Your calendar is wide open — pick something meaningful!",
        }.get(tone, "Your day is open — nothing is scheduled yet.")
    parts = []
    if n_events:
        parts.append(plural(n_events, "planned activity", "planned activities"))
    if n_tasks:
        parts.append(plural(n_tasks, "task"))
    head = f"You have {' and '.join(parts)} today"
    if not (first_label and first_time):
        return head + "."
    if minutes_until is not None and minutes_until <= 0:
        return f"{head}. {first_label} is happening now."
    if minutes_until is not None and minutes_until > 0 and tone not in ("direct", "minimal"):
        tail = f", and next up is {first_label} at {first_time}."
        if tone in ("warm", "calm") and minutes_until >= 15:
            tail = tail[:-1] + ". You have time to prepare."
        return head + tail
    return f"{head}. Next: {first_label} at {first_time}."


def getting_started(top_task: str | None, tone: str, seed: str) -> str:
    if tone == "minimal":
        return ""
    if top_task:
        return pick(
            {
                "warm": [f"A good place to start: “{top_task}”.", f"How about beginning with “{top_task}”?"],
                "calm": [f"When you're ready, “{top_task}” is a gentle first step."],
                "direct": [f"Start with: {top_task}."],
                "energetic": [f"Kick things off with “{top_task}”!"],
            }.get(tone, [f"Start with: {top_task}."]),
            seed + "start",
        )
    return pick(
        {
            "warm": ["Maybe start with something small that makes you feel good."],
            "calm": ["Choose one small thing and give it your full attention."],
            "direct": ["Add a task to plan your day."],
            "energetic": ["Pick one quick win and go!"],
        }.get(tone, [""]),
        seed + "start",
    )


def evening_sentence(done: int, planned: int, remaining: int, tone: str) -> str:
    if planned == 0:
        return {"direct": "No tasks were planned today.", "minimal": ""}.get(tone, "Today wasn't about tasks — that's okay too.")
    base = f"You completed {done} of your {plural(planned, 'planned task')}."
    if tone == "minimal":
        return base
    if done == planned:
        extra = {"energetic": " Every single one — fantastic!", "direct": "", "calm": " A complete day. Well done."}.get(tone, " That's a full day's work — well done.")
    elif done > 0:
        extra = {"direct": "", "energetic": " Great progress!"}.get(tone, " That's meaningful progress.")
    else:
        extra = {"direct": ""}.get(tone, " Some days are like that. Tomorrow is a fresh start.")
    if remaining:
        extra += f" Would you like to move the remaining {plural(remaining, 'task')} to tomorrow?"
    return base + extra


def missed_habit_sentence(habit_name: str, tone: str) -> str:
    if tone == "direct":
        return f"{habit_name} not done today. Move it to tomorrow?"
    return f"You didn't get to {habit_name} today. Would you like to try again tomorrow?"


CATEGORY_LINES = {
    "fitness": ["It's time for your planned workout. Even a shorter session helps you keep your routine."],
    "reading": ["Time for a little reading. Even a few pages count."],
    "hydration": ["A glass of water would be a kind thing to do right now."],
    "sleep": ["It's nearly time to wind down. Your future self will thank you."],
    "mindfulness": ["Take a moment to pause and breathe."],
    "habits": ["A gentle nudge for your habit."],
    "affirmations": ["Your affirmation for today is ready."],
}


def minutes_phrase(minutes: int) -> str:
    if minutes <= 0:
        return "now"
    if minutes < 60:
        return f"in {plural(minutes, 'minute')}"
    hours, rem = divmod(minutes, 60)
    if hours < 24 and rem == 0:
        return f"in {plural(hours, 'hour')}"
    if hours < 24:
        return f"in {hours} h {rem} min"
    return f"in {plural(hours // 24, 'day')}"


def reminder_body(occ, reminder, prefs, now) -> str:
    """Body text for a due reminder occurrence, from the real linked item."""
    if reminder.message:
        return reminder.message
    tone = prefs.tone
    if occ.target_key.startswith("event:"):
        mins = round(reminder.offset_minutes)
        line = f"Starts {minutes_phrase(mins)}."
        return line if tone in ("direct", "minimal") else line + (" Would you like to review your notes?" if mins >= 5 else "")
    if occ.target_key.startswith("task:"):
        when = "is due" if reminder.anchor == "deadline" else "starts"
        line = f"{occ.title} {when} {minutes_phrase(reminder.offset_minutes)}." if reminder.offset_minutes else f"Time for: {occ.title}."
        return line
    return pick(CATEGORY_LINES.get(occ.category, ["Here's your reminder."]), f"{occ.owner_id}{occ.id}")
