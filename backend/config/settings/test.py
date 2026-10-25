"""Test settings: same PostgreSQL engine as production, eager Celery, local-memory cache."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-secret-key-not-for-production-use-0123456789"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast hashing in tests only
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]}}  # noqa: F405
VAPID_PUBLIC_KEY = ""
VAPID_PRIVATE_KEY = ""
LOGGING["root"]["level"] = "WARNING"  # noqa: F405

PASSWORD_RESET_MIN_RESPONSE_SECONDS = 0
