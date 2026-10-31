import pytest

from apps.accounts.models import Role, User

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

NON_ADMIN_ROLES = [Role.ANALYST, Role.REVIEWER, Role.DEVELOPER, Role.READ_ONLY]


def test_admin_can_list_users(client_as):
    c = client_as(Role.ADMINISTRATOR)
    r = c.get("/api/auth/users/")
    assert r.status_code == 200
    assert r.json()["count"] == 1


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_other_roles_cannot_list_users(client_as, role):
    assert client_as(role).get("/api/auth/users/").status_code == 403


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_other_roles_cannot_create_users(client_as, role):
    r = client_as(role).post("/api/auth/users/", {"username": "x", "password": PASSWORD}, format="json")
    assert r.status_code == 403
    assert not User.objects.filter(username="x").exists()


def test_admin_creates_user_with_hashed_password(client_as):
    c = client_as(Role.ADMINISTRATOR)
    r = c.post("/api/auth/users/", {"username": "newanalyst", "password": PASSWORD, "role": "ANALYST"},
               format="json")
    assert r.status_code == 201
    assert "password" not in r.json()
    u = User.objects.get(username="newanalyst")
    assert u.role == Role.ANALYST and u.check_password(PASSWORD)


def test_weak_passwords_are_refused(client_as):
    c = client_as(Role.ADMINISTRATOR)
    r = c.post("/api/auth/users/", {"username": "weak", "password": "12345"}, format="json")
    assert r.status_code == 400
    assert "password" in r.json() or "non_field_errors" in r.json()


def test_new_users_default_to_read_only(client_as):
    c = client_as(Role.ADMINISTRATOR)
    c.post("/api/auth/users/", {"username": "plain", "password": PASSWORD}, format="json")
    assert User.objects.get(username="plain").role == Role.READ_ONLY


def test_users_cannot_be_deleted_only_deactivated(client_as, make_user):
    c = client_as(Role.ADMINISTRATOR)
    target = make_user("leaver")
    assert c.delete(f"/api/auth/users/{target.pk}/").status_code == 405
    r = c.patch(f"/api/auth/users/{target.pk}/", {"is_active": False}, format="json")
    assert r.status_code == 200
    target.refresh_from_db()
    assert target.is_active is False


def test_read_only_user_cannot_change_anything(client_as):
    from apps.accounts.permissions import RoleAwareDefault

    class FakeRequest:
        def __init__(self, user, method):
            self.user, self.method = user, method

    c = client_as(Role.READ_ONLY)
    perm = RoleAwareDefault()
    assert perm.has_permission(FakeRequest(c.user, "GET"), None) is True
    for method in ["POST", "PUT", "PATCH", "DELETE"]:
        assert perm.has_permission(FakeRequest(c.user, method), None) is False


def test_admin_cannot_demote_or_deactivate_themselves(client_as):
    c = client_as(Role.ADMINISTRATOR)
    me = c.user
    r = c.patch(f"/api/auth/users/{me.pk}/", {"role": "READ_ONLY"}, format="json")
    assert r.status_code == 400
    r = c.patch(f"/api/auth/users/{me.pk}/", {"is_active": False}, format="json")
    assert r.status_code == 400
    me.refresh_from_db()
    assert me.role == Role.ADMINISTRATOR and me.is_active


def test_user_list_accepts_a_page_size(client_as, make_user):
    c = client_as(Role.ADMINISTRATOR)
    for i in range(30):
        make_user(f"u{i}")
    assert len(c.get("/api/auth/users/").json()["results"]) == 25
    assert len(c.get("/api/auth/users/?page_size=100").json()["results"]) == 31
