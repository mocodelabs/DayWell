"""Per-user preferences: profile/locale, optional modules, dashboard layout, tone, briefings, quiet hours, notifications."""

from datetime import time

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel

# Optional modules. Disabled modules are hidden from the dashboard and never generate reminders.
MODULES: dict[str, bool] = {
    "affirmations": True,
    "reading": False,
    "fitness": False,
    "hydration": False,
    "sleep": False,
    "journal": False,
    "goals": False,
    "mindfulness": False,
    "admin": False,  # personal administration: chores, errands, bills, renewals
}

# Today-dashboard sections in default order. Users may reorder and hide them.
DASHBOARD_SECTIONS = [
    "briefing",
    "progress",
    "agenda",
    "priorities",
    "reminders",
    "habits",
    "affirmation",
    "reading",
    "fitness",
    "hydration",
    "evening",
]


class Tone(models.TextChoices):
    WARM = "warm", "Warm and friendly"
    CALM = "calm", "Calm and mindful"
    DIRECT = "direct", "Direct and concise"
    ENERGETIC = "energetic", "Energetic and motivational"
    MINIMAL = "minimal", "Minimal"


class NotificationCategory(models.TextChoices):
    TASKS = "tasks", "Tasks"
    EVENTS = "events", "Events"
    HABITS = "habits", "Habits"
    READING = "reading", "Reading"
    FITNESS = "fitness", "Fitness"
    HYDRATION = "hydration", "Hydration"
    SLEEP = "sleep", "Bedtime & wake-up"
    MINDFULNESS = "mindfulness", "Mindfulness"
    AFFIRMATIONS = "affirmations", "Affirmations"
    BRIEFING = "briefing", "Daily briefings"
    ADMIN = "admin", "Bills & personal admin"
    CUSTOM = "custom", "Custom reminders"


# Category → module that must be enabled for reminders of that category to fire.
CATEGORY_MODULE = {
    "reading": "reading",
    "fitness": "fitness",
    "hydration": "hydration",
    "sleep": "sleep",
    "mindfulness": "mindfulness",
    "affirmations": "affirmations",
    "admin": "admin",
}

SOUNDS = ["chime", "bell", "marimba", "birdsong", "soft-pulse", "classic"]


def default_modules() -> dict:
    return dict(MODULES)


def default_layout() -> list:
    return [{"key": key, "visible": True} for key in DASHBOARD_SECTIONS]


def default_weekdays() -> list:
    return [0, 1, 2, 3, 4]


def default_all_days() -> list:
    return [0, 1, 2, 3, 4, 5, 6]


class UserPreference(TimeStampedModel):
    class DateFormat(models.TextChoices):
        DMY = "DMY", "31/12/2026"
        MDY = "MDY", "12/31/2026"
        YMD = "YMD", "2026-12-31"

    class TimeFormat(models.TextChoices):
        H24 = "24h", "24-hour"
        H12 = "12h", "12-hour"

    class Theme(models.TextChoices):
        SYSTEM = "system"
        LIGHT = "light"
        DARK = "dark"

    class BriefingStyle(models.TextChoices):
        SHORT = "short"
        DETAILED = "detailed"

    class QuietBehavior(models.TextChoices):
        DELAY = "delay", "Hold until quiet hours end"
        SILENT = "silent", "Deliver silently in the app only"

    class MissedPolicy(models.TextChoices):
        SHOW = "show", "Show missed reminders in the app"
        HIDE = "hide", "Don't surface missed reminders"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences")
    # Locale & display
    time_zone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=16, default="en")
    date_format = models.CharField(max_length=3, choices=DateFormat.choices, default=DateFormat.DMY)
    time_format = models.CharField(max_length=3, choices=TimeFormat.choices, default=TimeFormat.H24)
    week_start = models.PositiveSmallIntegerField(default=0)  # 0=Monday … 6=Sunday
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.SYSTEM)
    reduced_motion = models.BooleanField(default=False)
    text_scale = models.DecimalField(max_digits=3, decimal_places=2, default=1)
    # Onboarding
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    focus_areas = models.JSONField(default=list, blank=True)
    # Modules & dashboard
    modules = models.JSONField(default=default_modules)
    dashboard_layout = models.JSONField(default=default_layout)
    # Warm interaction
    greeting_enabled = models.BooleanField(default=True)
    tone = models.CharField(max_length=12, choices=Tone.choices, default=Tone.WARM)
    briefing_style = models.CharField(max_length=10, choices=BriefingStyle.choices, default=BriefingStyle.SHORT)
    greeting_time = models.TimeField(default=time(7, 0))
    morning_notification = models.BooleanField(default=False)
    evening_summary = models.BooleanField(default=True)
    evening_time = models.TimeField(default=time(20, 0))
    # Daily rhythm
    wake_time = models.TimeField(default=time(6, 30))
    bedtime = models.TimeField(default=time(22, 30))
    work_start = models.TimeField(default=time(9, 0))
    work_end = models.TimeField(default=time(17, 0))
    work_days = models.JSONField(default=default_weekdays)
    planning_buffer_minutes = models.PositiveSmallIntegerField(default=10)
    # Wellness targets
    hydration_target = models.PositiveIntegerField(default=2000)
    hydration_unit = models.CharField(max_length=8, default="ml")  # ml | oz | glass
    glass_size_ml = models.PositiveIntegerField(default=250)
    reading_yearly_goal = models.PositiveSmallIntegerField(default=0)
    affirmation_categories = models.JSONField(default=list, blank=True)  # empty = all categories
    weekly_workout_goal = models.PositiveSmallIntegerField(default=0)
    # Notifications: global
    default_sound = models.CharField(max_length=20, default="chime")
    alarm_volume = models.PositiveSmallIntegerField(default=80)
    quiet_enabled = models.BooleanField(default=False)
    quiet_start = models.TimeField(default=time(22, 0))
    quiet_end = models.TimeField(default=time(7, 0))
    quiet_days = models.JSONField(default=default_all_days)
    quiet_behavior = models.CharField(max_length=8, choices=QuietBehavior.choices, default=QuietBehavior.DELAY)
    missed_policy = models.CharField(max_length=8, choices=MissedPolicy.choices, default=MissedPolicy.SHOW)
    # Privacy / AI (no AI provider is wired in the first release; both default off)
    ai_suggestions_enabled = models.BooleanField(default=False)
    journal_ai_consent = models.BooleanField(default=False)

    def module_enabled(self, key: str) -> bool:
        return bool(self.modules.get(key, MODULES.get(key, False)))

    def __str__(self) -> str:
        return f"Preferences for {self.user_id}"


class NotificationPreference(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app"
        PUSH = "push"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    category = models.CharField(max_length=16, choices=NotificationCategory.choices)
    enabled = models.BooleanField(default=True)
    channels = models.JSONField(default=list)  # subset of Channel values
    sound = models.CharField(max_length=20, blank=True)  # blank → UserPreference.default_sound
    vibrate = models.BooleanField(default=True)
    snooze_minutes = models.PositiveSmallIntegerField(default=10)
    bypass_quiet_hours = models.BooleanField(default=False)
    # Frequency control: at most one notification of this category per N minutes (0 = no limit).
    min_gap_minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "category"], name="notification_pref_unique_category")]
        ordering = ["category"]
