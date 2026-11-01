import json
import logging
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.document_analysis.models import DocumentAnalysis, SsnCheck
from apps.documents.models import UploadedFile

from . import images as img
from . import specimens as sp

pytestmark = pytest.mark.django_db
BASE = "/api/documents"
IDENTITY_ROLES = [Role.ADMINISTRATOR, Role.ANALYST, Role.REVIEWER]


def typed(c, lines=None, authorised=True, kind="passport"):
    return c.post(f"{BASE}/analyses/", {"mrz_text": "\n".join(lines or sp.TD3_VALID), "document_type": kind,
                                        "authorised": authorised}, format="json")


def upload(c, data, name="licence.png", kind="driving_licence"):
    return c.post(f"{BASE}/analyses/", {"file": SimpleUploadedFile(name, data), "document_type": kind,
                                        "authorised": "true"}, format="multipart")


# --- Access ------------------------------------------------------------------------------------

@pytest.mark.parametrize("role", [Role.DEVELOPER, Role.READ_ONLY])
def test_other_roles_have_no_access_at_all(client_as, role):
    c = client_as(role)
    assert c.get(f"{BASE}/analyses/").status_code == 403
    assert typed(c).status_code == 403
    assert c.post(f"{BASE}/ssn-checks/", {"number": "123-45-6780"}, format="json").status_code == 403


@pytest.mark.parametrize("role", IDENTITY_ROLES)
def test_identity_roles_can_analyse(client_as, role):
    assert typed(client_as(role)).status_code == 201


def test_authorisation_must_be_confirmed(client_as):
    r = typed(client_as(Role.ANALYST), authorised=False)
    assert r.status_code == 400 and "authorised" in r.json()["detail"]
    assert not DocumentAnalysis.objects.exists()


def test_analysts_see_only_their_own_records_reviewers_see_all(client_as):
    ann, bob, rev = client_as(Role.ANALYST, "ann"), client_as(Role.ANALYST, "bob"), client_as(Role.REVIEWER, "rev")
    record = typed(ann).json()["id"]
    typed(bob)
    assert ann.get(f"{BASE}/analyses/").json()["count"] == 1
    assert bob.get(f"{BASE}/analyses/{record}/").status_code == 404
    assert rev.get(f"{BASE}/analyses/").json()["count"] == 2


# --- Results -----------------------------------------------------------------------------------

def test_typed_mrz_result(client_as):
    body = typed(client_as(Role.ANALYST)).json()
    assert body["reference"].startswith("DOC-") and body["status"] == "PASS"
    assert body["fields"]["surname"]["value"] == "ERIKSSON" and body["fields"]["surname"]["source"] == "MRZ"
    assert body["authenticity"]["status"] == "NOT_CHECKED"
    assert body["mrz"]["layout"] == "TD3" and len(body["mrz"]["segments"]) > 5


def test_expired_specimen_fails_with_reason(client_as):
    body = typed(client_as(Role.ANALYST), sp.TD3).json()
    assert body["status"] == "FAIL" and "Expired on 15 April 2012" in body["summary"]


def test_licence_upload(client_as):
    body = upload(client_as(Role.ANALYST), img.as_png(img.pdf417_raw(sp.LICENCE_PAYLOAD))).json()
    assert body["detected_type"] == "driving_licence"
    assert body["fields"]["birth_date"]["value"] == "1974-08-12"
    assert body["links"]["pages"] == [f"{BASE}/analyses/{body['id']}/image/?page=1"]


def test_list_masks_names_and_numbers(client_as):
    c = client_as(Role.ANALYST)
    typed(c)
    row = c.get(f"{BASE}/analyses/").json()["results"][0]
    assert row["holder"] == "E." and row["number"] == "••••••2C3"
    assert "ERIKSSON" not in json.dumps(row)


def test_audit_holds_no_identity_values(client_as):
    c = client_as(Role.ANALYST)
    typed(c)
    upload(c, img.as_png(img.pdf417_raw(sp.LICENCE_PAYLOAD)))
    text = json.dumps(list(AuditEvent.objects.filter(action="document.analysed").values_list("metadata", flat=True)))
    for value in ("ERIKSSON", "L898902C3", "T64235789", "1974", "ANNA"):
        assert value not in text


# --- Retention ---------------------------------------------------------------------------------

def test_expired_records_are_purged_on_the_next_request(client_as):
    c = client_as(Role.ANALYST)
    record_id = upload(c, img.as_png(img.pdf417_raw(sp.LICENCE_PAYLOAD))).json()["id"]
    DocumentAnalysis.objects.filter(pk=record_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    body = c.get(f"{BASE}/analyses/{record_id}/").json()
    assert body["purged_at"] and body["fields"] == {} and body["mrz"] is None and body["ocr"] == []
    assert body["links"]["pages"] == [] and "deleted" in body["summary"]
    assert all(set(check) == {"category", "code", "name", "status"} for check in body["checks"])
    assert not UploadedFile.objects.get().file
    assert c.get(f"{BASE}/analyses/{record_id}/image/?page=1").status_code == 404


def test_purge_command(client_as):
    record_id = typed(client_as(Role.ANALYST)).json()["id"]
    DocumentAnalysis.objects.filter(pk=record_id).update(expires_at=timezone.now() - timedelta(days=1))
    call_command("purge_documents")
    assert DocumentAnalysis.objects.get(pk=record_id).purged


def test_delete_now(client_as):
    ann, bob = client_as(Role.ANALYST, "ann"), client_as(Role.REVIEWER, "bob")
    record_id = typed(ann).json()["id"]
    assert bob.post(f"{BASE}/analyses/{record_id}/delete-data/").status_code == 403  # reviewer, not the uploader
    body = ann.post(f"{BASE}/analyses/{record_id}/delete-data/").json()
    assert body["purged_at"] and body["fields"] == {}
    assert AuditEvent.objects.filter(action="document.data_deleted").exists()


# --- Comparison --------------------------------------------------------------------------------

def test_compare_passport_and_licence(client_as):
    c = client_as(Role.ANALYST)
    passport = typed(c).json()["id"]
    lic = upload(c, img.as_png(img.pdf417_raw(sp.LICENCE_PAYLOAD))).json()["id"]
    r = c.post(f"{BASE}/comparisons/", {"analysis_ids": [passport, lic]}, format="json")
    assert r.status_code == 201
    rows = {row["field"]: row for row in r.json()["rows"]}
    assert rows["surname"]["status"] == "PASS" and rows["birth_date"]["status"] == "PASS"
    assert rows["document_number"]["status"] == "NOT_CHECKED"


def test_compare_refuses_other_peoples_or_deleted_documents(client_as):
    ann, bob = client_as(Role.ANALYST, "ann"), client_as(Role.ANALYST, "bob")
    mine, theirs = typed(ann).json()["id"], typed(bob).json()["id"]
    assert ann.post(f"{BASE}/comparisons/", {"analysis_ids": [mine, theirs]}, format="json").status_code == 400
    other = typed(ann).json()["id"]
    ann.post(f"{BASE}/analyses/{other}/delete-data/")
    assert ann.post(f"{BASE}/comparisons/", {"analysis_ids": [mine, other]}, format="json").status_code == 400


# --- SSN ---------------------------------------------------------------------------------------

def test_ssn_check_never_stores_logs_or_returns_the_full_number(client_as, caplog):
    c = client_as(Role.ANALYST)
    with caplog.at_level(logging.DEBUG):
        r = c.post(f"{BASE}/ssn-checks/", {"number": "123-45-6780"}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["masked"] == "***-**-6780" and body["format_valid"] is True
    for haystack in (json.dumps(body), caplog.text, json.dumps(list(SsnCheck.objects.values()), default=str),
                     json.dumps(list(AuditEvent.objects.values_list("metadata", flat=True)))):
        assert "123-45-6780" not in haystack and "123456780" not in haystack and "12345" not in haystack


def test_ssn_invalid_input_is_not_echoed(client_as):
    r = client_as(Role.ANALYST).post(f"{BASE}/ssn-checks/", {"number": "9" * 30}, format="json")
    assert r.status_code == 400 and "9999" not in r.content.decode()


def test_dashboard_counts_documents(client_as):
    c = client_as(Role.ANALYST)
    typed(c)
    assert c.get("/api/dashboard/summary/").json()["counts"]["documents_processed"] == 1
