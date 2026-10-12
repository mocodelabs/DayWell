"""Production settings. Every secret comes from the environment; startup fails loudly if one is missing."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env, env_bool

DEBUG = False
if not SECRET_KEY or len(SECRET_KEY) < 40:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a random value of at least 40 characters.")
if "DATABASE_URL" not in __import__("os").environ:
    raise ImproperlyConfigured("DATABASE_URL must be set in production.")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Preloading is a long-term commitment to HTTPS on every subdomain; opt in explicitly once the domain is ready.
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS = ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)
X_FRAME_OPTIONS = "DENY"
LOG_JSON = True
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405
