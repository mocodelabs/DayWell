from django.contrib.auth import password_validation
from rest_framework import serializers

from apps.core.timeutils import is_valid_timezone

from .models import User, UserSession


class UserSerializer(serializers.ModelSerializer):
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "email_verified", "date_joined"]
        read_only_fields = ["id", "email", "email_verified", "date_joined"]

    def get_email_verified(self, obj: User) -> bool:
        return obj.email_verified_at is not None


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    display_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    time_zone = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_time_zone(self, value: str) -> str:
        if value and not is_valid_timezone(value):
            raise serializers.ValidationError("Unknown time zone.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"], User(email=attrs["email"], display_name=attrs.get("display_name", "")))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError({"current_password": ["Your current password is incorrect."]})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False)


class EmailVerifySerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)


class AccountDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    confirm = serializers.CharField(max_length=20)

    def validate(self, attrs):
        if attrs["confirm"].strip().upper() != "DELETE":
            raise serializers.ValidationError({"confirm": ["Type DELETE to confirm."]})
        if not self.context["request"].user.check_password(attrs["password"]):
            raise serializers.ValidationError({"password": ["Your password is incorrect."]})
        return attrs


class UserSessionSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = ["session_key", "user_agent", "ip_address", "created_at", "last_seen_at", "current"]

    def get_current(self, obj: UserSession) -> bool:
        return obj.session_key == self.context["request"].session.session_key
