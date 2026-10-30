import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_health_runs_a_real_database_check(api):
    r = api.get("/api/health/")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_login_with_correct_password_returns_profile(api, make_user):
    make_user("alice", role=Role.ANALYST)
    r = api.post("/api/auth/login/", {"username": "alice", "password": PASSWORD}, format="json")
    assert r.status_code == 200
    assert r.json()["role"] == "ANALYST"
    assert "password" not in r.json()


def test_login_with_wrong_password_is_rejected(api, make_user):
    make_user("alice")
    r = api.post("/api/auth/login/", {"username": "alice", "password": "wrong"}, format="json")
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid username or password."


def test_unknown_user_gets_the_same_message_as_wrong_password(api):
    r = api.post("/api/auth/login/", {"username": "nobody", "password": "x"}, format="json")
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid username or password."


def test_inactive_user_cannot_log_in(api, make_user):
    make_user("bob", is_active=False)
    r = api.post("/api/auth/login/", {"username": "bob", "password": PASSWORD}, format="json")
    assert r.status_code == 401


def test_login_is_rate_limited_after_five_attempts(api):
    codes = [api.post("/api/auth/login/", {"username": "x", "password": "y"}, format="json").status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_me_requires_login(api):
    assert api.get("/api/auth/me/").status_code == 403


def test_me_after_login(client_as):
    c = client_as(Role.REVIEWER, "rita")
    r = c.get("/api/auth/me/")
    assert r.status_code == 200
    assert r.json()["username"] == "rita"


def test_logout_ends_the_session(client_as):
    c = client_as(Role.READ_ONLY)
    assert c.post("/api/auth/logout/").status_code == 204
    assert c.get("/api/auth/me/").status_code == 403


def test_csrf_is_enforced_for_session_logins(make_user):
    make_user("carol", role=Role.ADMINISTRATOR)
    c = APIClient(enforce_csrf_checks=True)
    c.get("/api/auth/csrf/")
    token = c.cookies["csrftoken"].value
    # Without the token header the login is refused...
    assert c.post("/api/auth/login/", {"username": "carol", "password": PASSWORD}, format="json").status_code == 403
    # ...with it, the login works.
    r = c.post("/api/auth/login/", {"username": "carol", "password": PASSWORD}, format="json",
               HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 200


def test_passwords_are_stored_hashed(make_user):
    u = make_user("dave")
    assert u.password != PASSWORD
    assert User.objects.get(username="dave").check_password(PASSWORD)


def test_createsuperuser_gets_administrator_role(db):
    u = User.objects.create_superuser("root", "root@example.test", PASSWORD)
    assert u.role == Role.ADMINISTRATOR
