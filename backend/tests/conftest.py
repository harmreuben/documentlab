import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

PASSWORD = "Test-Passw0rd-2026!"  # fictional test password used only by these tests


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_user(db):
    def _make(username="user", role=Role.READ_ONLY, **extra):
        return User.objects.create_user(username=username, password=PASSWORD, role=role, **extra)
    return _make


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def client_as(make_user):
    """Returns an API client already logged in with the given role."""
    def _client(role, username=None):
        user = make_user(username or role.lower(), role=role)
        c = APIClient()
        c.force_login(user)
        c.user = user
        return c
    return _client
