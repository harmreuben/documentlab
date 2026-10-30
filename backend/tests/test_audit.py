import logging

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.audit.redaction import REDACTED, RedactingFilter, scrub

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_successful_login_is_audited(api, make_user):
    make_user("alice")
    api.post("/api/auth/login/", {"username": "alice", "password": PASSWORD}, format="json")
    event = AuditEvent.objects.get(action="auth.login")
    assert event.username == "alice"
    assert event.ip_address == "127.0.0.1"


def test_failed_login_is_audited_without_the_password(api):
    api.post("/api/auth/login/", {"username": "mallory", "password": "guess-123"}, format="json")
    event = AuditEvent.objects.get(action="auth.login_failed")
    assert event.username == "mallory"
    assert "guess-123" not in str(event.metadata)


def test_logout_is_audited(client_as):
    c = client_as(Role.ANALYST, "ann")
    c.post("/api/auth/logout/")
    assert AuditEvent.objects.filter(action="auth.logout", username="ann").exists()


def test_user_creation_is_audited_and_password_not_recorded(client_as):
    c = client_as(Role.ADMINISTRATOR, "boss")
    c.post("/api/auth/users/", {"username": "newbie", "password": PASSWORD, "role": "REVIEWER"}, format="json")
    event = AuditEvent.objects.get(action="user.created")
    assert event.username == "boss"
    assert event.metadata == {"role": "REVIEWER"}
    assert PASSWORD not in str(event.metadata)


def test_password_change_is_recorded_as_changed_only(client_as, make_user):
    c = client_as(Role.ADMINISTRATOR)
    target = make_user("pat")
    c.patch(f"/api/auth/users/{target.pk}/", {"password": "Another-Passw0rd-99"}, format="json")
    event = AuditEvent.objects.get(action="user.updated")
    assert event.metadata["changes"]["password"] == REDACTED
    assert "Another-Passw0rd-99" not in str(event.metadata)


def test_audit_events_cannot_be_edited_or_deleted(make_user):
    event = AuditEvent.objects.create(action="test.event")
    event.action = "tampered"
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()


def test_only_admins_can_read_the_audit_log(client_as):
    assert client_as(Role.ADMINISTRATOR).get("/api/audit/events/").status_code == 200
    for role in [Role.ANALYST, Role.REVIEWER, Role.DEVELOPER, Role.READ_ONLY]:
        assert client_as(role).get("/api/audit/events/").status_code == 403


def test_audit_api_cannot_write(client_as):
    c = client_as(Role.ADMINISTRATOR)
    assert c.post("/api/audit/events/", {"action": "fake"}, format="json").status_code == 405


def test_scrub_redacts_nested_sensitive_keys():
    data = {"name": "Test Person", "ssn": "000-00-0000", "nested": {"new_password": "x", "ok": 1},
            "items": [{"token": "abc"}]}
    clean = scrub(data)
    assert clean["name"] == "Test Person"
    assert clean["ssn"] == REDACTED
    assert clean["nested"] == {"new_password": REDACTED, "ok": 1}
    assert clean["items"] == [{"token": REDACTED}]


def test_log_filter_hides_ssn_patterns_and_passwords():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "check %s password=%s", ("123-45-6789", "hunter2"), None)
    RedactingFilter().filter(record)
    message = record.getMessage()
    assert "123-45-6789" not in message
    assert "hunter2" not in message
