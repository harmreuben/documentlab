import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditEvent

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db
URL = "/api/dashboard/summary/"


def test_dashboard_requires_login(api):
    assert api.get(URL).status_code == 403


def test_admin_sees_real_system_counts(client_as, make_user):
    c = client_as(Role.ADMINISTRATOR, "boss")
    make_user("a1", role=Role.ANALYST)
    make_user("gone", role=Role.REVIEWER, is_active=False)
    AuditEvent.objects.create(action="auth.login", username="a1")
    AuditEvent.objects.create(action="auth.login_failed", username="x")

    data = c.get(URL).json()
    assert data["scope"] == "system"
    assert data["users"]["total"] == 3
    assert data["users"]["active"] == 2
    assert data["users"]["by_role"]["ANALYST"] == 1
    assert data["users"]["by_role"]["REVIEWER"] == 0  # inactive users are not counted
    # boss's own login (by the test client) + the two events created above
    assert data["counts"]["events_24h"] == 3
    assert data["counts"]["logins_7d"] == 2
    assert data["counts"]["failed_logins_7d"] == 1


def test_non_admin_sees_only_their_own_activity(client_as, make_user):
    c = client_as(Role.ANALYST, "ann")
    other = make_user("bob")
    AuditEvent.objects.create(action="auth.login", user=c.user, username="ann")
    AuditEvent.objects.create(action="auth.login", user=other, username="bob")

    data = c.get(URL).json()
    assert data["scope"] == "personal"
    assert data["users"] is None
    assert data["counts"]["failed_logins_7d"] is None
    assert data["counts"]["events_24h"] == 2  # ann's test-client login + the one created above
    assert {e["username"] for e in data["recent_activity"]} == {"ann"}


def test_unbuilt_modules_report_null_not_zero(client_as):
    counts = client_as(Role.ADMINISTRATOR).get(URL).json()["counts"]
    for key in ["documents_processed", "pending_reviews"]:
        assert counts[key] is None


def test_activity_covers_fourteen_days_including_empty_ones(client_as):
    data = client_as(Role.ADMINISTRATOR).get(URL).json()
    assert len(data["activity"]) == 14
    assert all(set(d) == {"date", "events"} for d in data["activity"])


def test_real_login_shows_up_on_the_dashboard(api, make_user):
    make_user("alice", role=Role.ADMINISTRATOR)
    api.post("/api/auth/login/", {"username": "alice", "password": PASSWORD}, format="json")
    data = api.get(URL).json()
    assert data["counts"]["logins_7d"] == 1
    assert data["activity"][-1]["events"] >= 1
    assert data["recent_activity"][0]["action"] == "auth.login"


def test_module_list_marks_unbuilt_modules_as_planned(client_as):
    modules = {m["key"]: m for m in client_as(Role.READ_ONLY).get(URL).json()["modules"]}
    assert len(modules) == 10
    assert modules["dashboard"]["status"] == "available"
    assert modules["generator"]["status"] == "available"
    assert modules["analyzer"]["status"] == "available"
    assert modules["documents"]["status"] == "planned"
