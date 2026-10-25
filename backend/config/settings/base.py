"""Shared Django settings for DayWell. Environment-specific modules import * from here."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(os.environ.get("ENV_FILE", BASE_DIR / ".env"))


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.preferences",
    "apps.tasks",
    "apps.events",
    "apps.reminders",
    "apps.habits",
    "apps.affirmations",
    "apps.reading",
    "apps.fitness",
    "apps.wellness",
    "apps.insights",
    "apps.briefing",
    "apps.billing",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "apps.core.middleware.HealthProbeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://daywell:daywell@127.0.0.1:5440/daywell"),
        conn_max_age=int(env("DB_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
    )
}
# Behind a transaction-mode pooler (PgBouncer, Neon/Supabase poolers) named server-side cursors break; disable them.
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env_bool("DB_DISABLE_SERVER_SIDE_CURSORS", False)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Optional: serve the built SPA from Django (single-origin deployments). Leave empty when nginx serves it.
FRONTEND_DIST = env("FRONTEND_DIST", "")

# --- Sessions & CSRF: cookie-based session auth, no tokens in browser storage. ---
# Sessions are read from Redis and written through to PostgreSQL (durable); a Redis outage falls back to the DB.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_NAME = "daywell_session"
SESSION_COOKIE_AGE = int(env("SESSION_COOKIE_AGE", str(60 * 60 * 24 * 30)))  # 30 days, sliding
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_NAME = "daywell_csrftoken"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5193,http://127.0.0.1:5193")

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated", "apps.billing.permissions.PremiumOrReadOnly"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.exceptions.envelope_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("THROTTLE_USER", "1200/hour"),
        "auth": env("THROTTLE_AUTH", "10/minute"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", "5/hour"),
        "sensitive": env("THROTTLE_SENSITIVE", "10/hour"),
        "test_notify": env("THROTTLE_TEST_NOTIFY", "20/hour"),
        "receipt": env("THROTTLE_RECEIPT", "600/hour"),
    },
    "NUM_PROXIES": int(env("NUM_PROXIES", "0")),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "DayWell API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "Personal operations & wellness companion. All endpoints are owner-scoped.",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Cache / Redis ---
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6390/0")
CACHES = {
    "default": {
        # Degrades to cache misses when Redis is down, so an outage can't take the API with it (see apps/core/cache.py).
        "BACKEND": "apps.core.cache.ResilientRedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "daywell",
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1, "retry_on_timeout": False},
    }
}

# Hosts without Redis (e.g. serverless trials) can keep the cache in PostgreSQL: CACHE_BACKEND=database
# (then run `manage.py createcachetable`). Locks, rate limits and the scheduler heartbeat all work the same way.
if env("CACHE_BACKEND", "redis") == "database":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "daywell_cache", "KEY_PREFIX": "daywell"}}
    SESSION_ENGINE = "django.contrib.sessions.backends.db"  # a DB-backed cache would only double the queries

# --- Scheduler without Celery beat (see apps/core/scheduler.py) ---
# Token for GET/POST /internal/tick/ (also accepts Vercel's CRON_SECRET). Empty = endpoint disabled (404).
SCHEDULER_TOKEN = env("SCHEDULER_TOKEN", "") or env("CRON_SECRET", "")
# Run due periodic jobs from the in-app alarm poll as well. Only for deployments without a Celery beat.
INLINE_SCHEDULER = env_bool("INLINE_SCHEDULER", False)

# --- Billing (Paystack). Payments are disabled until the secret key is set; trials and read-only mode still apply. ---
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", "")
BILLING_TRIAL_DAYS = int(env("BILLING_TRIAL_DAYS", "14"))
BILLING_RENEWAL_GRACE_DAYS = int(env("BILLING_RENEWAL_GRACE_DAYS", "3"))

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # use Django's LOGGING (JSON in production) for worker and beat output too
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    # The authoritative reminder clock: claim and dispatch every due occurrence.
    "dispatch-due-reminders": {"task": "reminders.dispatch_due", "schedule": timedelta(seconds=30)},
    # Keep a rolling window of materialised occurrences / recurring task instances.
    "extend-reminder-horizon": {"task": "reminders.extend_horizon", "schedule": timedelta(minutes=15)},
    "extend-task-series": {"task": "tasks.extend_series", "schedule": crontab(minute=7)},
    # Operational: report scheduler lag and clean expired data.
    "scheduler-heartbeat": {"task": "reminders.heartbeat", "schedule": timedelta(minutes=1)},
    "cleanup": {"task": "core.cleanup", "schedule": crontab(hour=3, minute=17)},
    "sync-billing-plans": {"task": "billing.sync_plans", "schedule": timedelta(hours=1)},
}

# --- Reminder engine tuning (see docs/NOTIFICATIONS_AND_ALARMS.md) ---
REMINDER_HORIZON_DAYS = int(env("REMINDER_HORIZON_DAYS", "14"))
# An occurrence older than this when the dispatcher first sees it is "missed": it is surfaced in-app, never pushed.
REMINDER_STALE_AFTER = timedelta(minutes=int(env("REMINDER_STALE_AFTER_MINUTES", "15")))
REMINDER_MAX_ATTEMPTS = int(env("REMINDER_MAX_ATTEMPTS", "4"))
REMINDER_DISPATCH_BATCH = int(env("REMINDER_DISPATCH_BATCH", "200"))
TASK_SERIES_HORIZON_DAYS = int(env("TASK_SERIES_HORIZON_DAYS", "21"))

# --- Web Push (VAPID). Push is disabled until both keys are configured. ---
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = env("VAPID_SUBJECT", "mailto:admin@localhost")
WEB_PUSH_TTL = int(env("WEB_PUSH_TTL", "900"))

# --- Email ---
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "25"))
# Trim pasted credentials: a stray newline/space (e.g. from a shell pipe) makes the SMTP login fail. Gmail app passwords
# are shown in groups of four; the spaces are not part of the password.
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = "".join(env("EMAIL_HOST_PASSWORD", "").split())
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "DayWell <no-reply@localhost>")
EMAIL_TIMEOUT = int(env("EMAIL_TIMEOUT", "10"))  # seconds; a slow mail server must not hang the request
PASSWORD_RESET_TIMEOUT = int(env("PASSWORD_RESET_TIMEOUT", "3600"))  # reset links expire after 1 hour
PASSWORD_RESET_MIN_RESPONSE_SECONDS = float(env("PASSWORD_RESET_MIN_RESPONSE_SECONDS", "2.5"))
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5193")
REQUIRE_EMAIL_VERIFICATION = env_bool("REQUIRE_EMAIL_VERIFICATION", False)

# --- Logging: structured, never logs request bodies (passwords/journal text never reach logs). ---
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOG_JSON = env_bool("LOG_JSON", False)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json" if LOG_JSON else "plain",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "daywell": {"level": LOG_LEVEL, "propagate": True},
    },
}
