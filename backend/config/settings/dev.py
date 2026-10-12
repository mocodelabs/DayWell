"""Local development settings."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-change-me"  # noqa: F405
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
