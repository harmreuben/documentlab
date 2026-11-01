"""External SSN verification: off unless configured, consent first, minimal data, honest results."""
import json

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.document_analysis.models import SsnVerification
from apps.system.status import security_status

from .fake_provider import FakeProvider

URL = "/api/documents/ssn-verifications/"
PERSON = {"number": "212-34-5678", "first_name": "Zawadi", "last_name": "Example", "birth_date": "1980-02-03",
          "consent_method": "signed_paper", "consent_reference": "CF-2026-0042", "consent_signed_on": "2026-10-30",
          "purpose": "account_opening", "consent_confirmed": True}


@pytest.fixture
def provider(settings):
    def use(name="FakeProvider"):
        settings.SSN_VERIFICATION_PROVIDER = f"tests.fake_provider.{name}"
    FakeProvider.received.clear()
    return use


def test_off_until_a_provider_is_configured(client_as):
    analyst = client_as(Role.ANALYST)
    assert analyst.get(URL + "meta/").json()["available"] is False
    response = analyst.post(URL, PERSON, format="json")
    assert response.status_code == 503 and "No authorised verification provider" in response.json()["detail"]
    assert not SsnVerification.objects.exists()


def test_a_match_keeps_only_the_masked_number_and_the_consent(client_as, provider):
    provider()
    analyst = client_as(Role.ANALYST)
    assert analyst.get(URL + "meta/").json() | {"purposes": None, "consent_methods": None} == {
        "available": True, "provider": "Test provider", "purposes": None, "consent_methods": None}
    body = analyst.post(URL, PERSON, format="json").json()
    assert body["status"] == "PASS" and body["outcome"] == "match" and body["masked"] == "***-**-5678"
    assert "doesn't prove who is presenting it" in body["summary"]
    sent = FakeProvider.received[0]
    assert (sent.number, sent.first_name, sent.consent.reference) == ("212345678", "Zawadi", "CF-2026-0042")

    record = SsnVerification.objects.values().get()
    stored = json.dumps(record, default=str)
    for secret in ("212345678", "212-34-5678", "Zawadi", "Example", "1980-02-03"):
        assert secret not in stored
    logged = json.dumps(AuditEvent.objects.get(action="ssn.verified").metadata)
    assert "CF-2026-0042" in logged and "5678" not in logged and "Example" not in logged


def test_mismatches_name_the_fields_not_the_values(client_as, provider):
    provider()
    body = client_as(Role.REVIEWER).post(URL, {**PERSON, "last_name": "Exampel", "birth_date": "1980-03-02"},
                                         format="json").json()
    assert body["status"] == "FAIL" and body["mismatched"] == ["last_name", "birth_date"]
    assert "last name, date of birth" in body["summary"]


@pytest.mark.parametrize("name", ["BrokenProvider", "SlowProvider", "ConfusedProvider"])
def test_anything_but_a_clear_answer_is_unavailable(client_as, provider, name):
    provider(name)
    body = client_as(Role.ANALYST).post(URL, PERSON, format="json").json()
    assert body["status"] == "UNAVAILABLE" and body["outcome"] == "error"
    assert "ownership wasn't checked" in body["summary"]


def test_consent_and_format_are_checked_before_the_provider_is_asked(client_as, provider):
    provider()
    analyst = client_as(Role.ANALYST)
    assert "consent" in json.dumps(analyst.post(URL, {**PERSON, "consent_confirmed": False}, format="json").json())
    assert "future" in json.dumps(analyst.post(URL, {**PERSON, "consent_signed_on": "2099-01-01"}, format="json").json())
    invalid = analyst.post(URL, {**PERSON, "number": "666-12-3456"}, format="json")
    assert invalid.status_code == 400 and "format" in invalid.json()["detail"]
    assert FakeProvider.received == []


def test_access_is_limited_like_other_identity_data(client_as, provider):
    provider()
    ann, other = client_as(Role.ANALYST), client_as(Role.ANALYST, "other")
    ann.post(URL, PERSON, format="json")
    assert other.get(URL).json()["count"] == 0
    assert client_as(Role.REVIEWER, "rev").get(URL).json()["count"] == 1
    assert client_as(Role.DEVELOPER).get(URL).status_code == 403


def test_a_broken_configuration_shows_on_the_security_page(settings, db):
    settings.SSN_VERIFICATION_PROVIDER = "tests.fake_provider.NeedsCredentials"
    item = next(i for i in security_status()["items"] if i["key"] == "verification")
    assert item["status"] == "FAIL" and "PROVIDER_API_KEY" in item["detail"]
    settings.SSN_VERIFICATION_PROVIDER = "tests.fake_provider.DoesNotExist"
    assert "couldn't be loaded" in next(i for i in security_status()["items"] if i["key"] == "verification")["detail"]
