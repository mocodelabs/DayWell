"""A Redis cache that degrades instead of failing.

Redis holds only disposable data (rate-limit counters, login lockouts, the scheduler heartbeat, the Celery queue). A
Redis outage must not take the API down, so cache errors behave like cache misses: reads return the default, writes are
dropped, `add` reports "not added" (so the dispatcher's run-lock errs on the side of skipping a run).

Trade-off (documented in docs/DEPLOYMENT.md): while Redis is unreachable, rate limits and login lockouts fail OPEN.
`/health/ready/` still reports the cache as failing so monitoring alerts.
"""

from __future__ import annotations

import logging
import time

from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

logger = logging.getLogger("daywell.cache")
_last_warning = 0.0


def _warn(op: str, exc: Exception) -> None:
    global _last_warning
    now = time.monotonic()
    if now - _last_warning > 60:  # at most one warning per minute per process
        _last_warning = now
        logger.warning("Redis unavailable; cache %s degraded (rate limits fail open): %s", op, exc.__class__.__name__)


class ResilientRedisCache(RedisCache):
    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except RedisError as exc:
            _warn("get", exc)
            return default

    def get_many(self, keys, version=None):
        try:
            return super().get_many(keys, version)
        except RedisError as exc:
            _warn("get_many", exc)
            return {}

    def set(self, key, value, timeout=..., version=None):
        try:
            if timeout is ...:
                return super().set(key, value, version=version)
            return super().set(key, value, timeout, version)
        except RedisError as exc:
            _warn("set", exc)
            return None

    def set_many(self, data, timeout=..., version=None):
        try:
            if timeout is ...:
                return super().set_many(data, version=version)
            return super().set_many(data, timeout, version)
        except RedisError as exc:
            _warn("set_many", exc)
            return list(data)

    def add(self, key, value, timeout=..., version=None):
        try:
            if timeout is ...:
                return super().add(key, value, version=version)
            return super().add(key, value, timeout, version)
        except RedisError as exc:
            _warn("add", exc)
            return False

    def incr(self, key, delta=1, version=None):
        try:
            return super().incr(key, delta, version)
        except RedisError as exc:
            _warn("incr", exc)
            raise ValueError("cache unavailable") from exc  # same contract as a missing key

    def delete(self, key, version=None):
        try:
            return super().delete(key, version)
        except RedisError as exc:
            _warn("delete", exc)
            return False

    def delete_many(self, keys, version=None):
        try:
            return super().delete_many(keys, version)
        except RedisError as exc:
            _warn("delete_many", exc)
            return None

    def has_key(self, key, version=None):
        try:
            return super().has_key(key, version)
        except RedisError as exc:
            _warn("has_key", exc)
            return False

    def touch(self, key, timeout=..., version=None):
        try:
            if timeout is ...:
                return super().touch(key, version=version)
            return super().touch(key, timeout, version)
        except RedisError as exc:
            _warn("touch", exc)
            return False
