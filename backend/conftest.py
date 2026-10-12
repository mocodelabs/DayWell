import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


def make_user(email: str = "ada@example.com", tz: str = "Africa/Nairobi", **prefs) -> User:
    user = User.objects.create_user(email=email, password="correct horse battery", display_name=email.split("@")[0].title())
    p = user.preferences
    p.time_zone = tz
    for k, v in prefs.items():
        setattr(p, k, v)
    p.save()
    return user


@pytest.fixture
def user(db):
    return make_user()


@pytest.fixture
def other_user(db):
    return make_user("mallory@example.com")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def other_api(other_user):
    client = APIClient()
    client.force_login(other_user)
    return client


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters and lockouts live in the cache; isolate them per test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
