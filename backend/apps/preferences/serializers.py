from rest_framework import serializers

from apps.core.timeutils import is_valid_timezone

from .models import DASHBOARD_SECTIONS, MODULES, SOUNDS, NotificationPreference, UserPreference


def _validate_days(value) -> list[int]:
    if not isinstance(value, list) or any(not isinstance(d, int) or not 0 <= d <= 6 for d in value):
        raise serializers.ValidationError("Days must be a list of numbers 0 (Monday) to 6 (Sunday).")
    return sorted(set(value))


class UserPreferenceSerializer(serializers.ModelSerializer):
    onboarding_completed = serializers.SerializerMethodField()
    complete_onboarding = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = UserPreference
        exclude = ["id", "user", "created_at"]
        read_only_fields = ["onboarding_completed_at", "updated_at"]

    def get_onboarding_completed(self, obj) -> bool:
        return obj.onboarding_completed_at is not None

    def validate_time_zone(self, value):
        if not is_valid_timezone(value):
            raise serializers.ValidationError("Unknown time zone. Use an IANA name such as Africa/Nairobi.")
        return value

    def validate_week_start(self, value):
        if not 0 <= value <= 6:
            raise serializers.ValidationError("Week start must be 0 (Monday) to 6 (Sunday).")
        return value

    def validate_text_scale(self, value):
        if not 0.85 <= float(value) <= 1.5:
            raise serializers.ValidationError("Text scale must be between 0.85 and 1.5.")
        return value

    def validate_modules(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Modules must be an object of module → true/false.")
        unknown = set(value) - set(MODULES)
        if unknown:
            raise serializers.ValidationError(f"Unknown module(s): {', '.join(sorted(unknown))}.")
        merged = {**(self.instance.modules if self.instance else MODULES)}
        merged.update({k: bool(v) for k, v in value.items()})
        return merged

    def validate_dashboard_layout(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Layout must be a list.")
        seen: list[dict] = []
        keys = set()
        for item in value:
            if not isinstance(item, dict) or item.get("key") not in DASHBOARD_SECTIONS or item["key"] in keys:
                raise serializers.ValidationError("Each layout entry needs a unique, known section key.")
            keys.add(item["key"])
            seen.append({"key": item["key"], "visible": bool(item.get("visible", True))})
        seen.extend({"key": k, "visible": True} for k in DASHBOARD_SECTIONS if k not in keys)  # never lose a section
        return seen

    def validate_work_days(self, value):
        return _validate_days(value)

    def validate_quiet_days(self, value):
        return _validate_days(value)

    def validate_focus_areas(self, value):
        if not isinstance(value, list) or len(value) > 12 or any(not isinstance(v, str) or len(v) > 40 for v in value):
            raise serializers.ValidationError("Focus areas must be a short list of labels.")
        return value

    def validate_default_sound(self, value):
        if value not in SOUNDS:
            raise serializers.ValidationError(f"Choose one of: {', '.join(SOUNDS)}.")
        return value

    def validate_alarm_volume(self, value):
        if value > 100:
            raise serializers.ValidationError("Volume is 0–100.")
        return value

    def validate_hydration_unit(self, value):
        if value not in {"ml", "oz", "glass"}:
            raise serializers.ValidationError("Unit must be ml, oz or glass.")
        return value

    def validate(self, attrs):
        start = attrs.get("work_start", getattr(self.instance, "work_start", None))
        end = attrs.get("work_end", getattr(self.instance, "work_end", None))
        if start and end and start >= end:
            raise serializers.ValidationError({"work_end": ["Working hours must end after they start."]})
        return attrs

    def update(self, instance, validated_data):
        from django.utils import timezone

        if validated_data.pop("complete_onboarding", False) and instance.onboarding_completed_at is None:
            instance.onboarding_completed_at = timezone.now()
        return super().update(instance, validated_data)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = NotificationPreference
        fields = ["id", "category", "label", "enabled", "channels", "sound", "vibrate", "snooze_minutes", "bypass_quiet_hours", "min_gap_minutes"]
        read_only_fields = ["id", "category", "label"]

    def validate_channels(self, value):
        allowed = set(NotificationPreference.Channel.values)
        if not isinstance(value, list) or any(v not in allowed for v in value):
            raise serializers.ValidationError("Channels must be a list containing in_app and/or push.")
        return sorted(set(value))

    def validate_sound(self, value):
        if value and value not in SOUNDS:
            raise serializers.ValidationError(f"Choose one of: {', '.join(SOUNDS)}.")
        return value

    def validate_snooze_minutes(self, value):
        if not 1 <= value <= 240:
            raise serializers.ValidationError("Snooze must be between 1 and 240 minutes.")
        return value
