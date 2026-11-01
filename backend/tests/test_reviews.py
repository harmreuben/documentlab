"""Review workflow: a second person decides on results that need review, without changing the result."""
import json

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.document_analysis.models import DocumentAnalysis

from .specimens import TD3_VALID

QUEUE = "/api/reviews/"


def _needs_review(client):
    """A passport MRZ analysed as an ID card: the type mismatch needs review."""
    record = client.post("/api/documents/analyses/", {"mrz_text": "\n".join(TD3_VALID), "document_type": "id_card",
                                                       "authorised": True}, format="json").json()
    assert record["status"] == "REVIEW_REQUIRED" and record["review"]["review_state"] == "PENDING"
    return record


def test_a_second_reviewer_confirms_without_changing_the_result(client_as):
    analyst, reviewer = client_as(Role.ANALYST), client_as(Role.REVIEWER)
    record = _needs_review(analyst)
    assert reviewer.get(QUEUE).json()["pending"] == 1
    assert analyst.get("/api/dashboard/summary/").json()["counts"]["pending_reviews"] == 1

    url = f"{QUEUE}document/{record['id']}/"
    assert analyst.post(url, {"decision": "CONFIRMED"}, format="json").status_code == 403
    response = reviewer.post(url, {"decision": "CONFIRMED", "note": "Checked against the card."}, format="json")
    assert response.status_code == 200 and response.json()["review_state"] == "CONFIRMED"

    detail = reviewer.get(f"/api/documents/analyses/{record['id']}/").json()
    assert detail["status"] == "REVIEW_REQUIRED"  # the technical result never changes
    assert detail["review"]["reviewed_by"] == "reviewer"
    assert reviewer.get(QUEUE).json()["pending"] == 0
    assert reviewer.post(url, {"decision": "REJECTED", "note": "x"}, format="json").status_code == 400


def test_nobody_reviews_their_own_work(client_as):
    reviewer = client_as(Role.REVIEWER)
    record = _needs_review(reviewer)
    response = reviewer.post(f"{QUEUE}document/{record['id']}/", {"decision": "CONFIRMED"}, format="json")
    assert response.status_code == 403 and "own analysis" in response.json()["detail"]
    admin = client_as(Role.ADMINISTRATOR)
    assert admin.get(QUEUE).json()["results"][0]["can_review"] is True


def test_rejection_needs_a_note_and_the_note_stays_out_of_the_audit_log(client_as):
    analyst, admin = client_as(Role.ANALYST), client_as(Role.ADMINISTRATOR)
    record = _needs_review(analyst)
    url = f"{QUEUE}document/{record['id']}/"
    assert "Say why" in admin.post(url, {"decision": "REJECTED"}, format="json").json()["detail"]
    admin.post(url, {"decision": "REJECTED", "note": "Surname on card reads ERIKSON"}, format="json")
    event = AuditEvent.objects.get(action="review.rejected")
    assert "ERIKSON" not in json.dumps(event.metadata) and event.metadata["reference"] == record["reference"]
    decided = analyst.get(f"{QUEUE}?decided=1").json()["results"]
    assert decided[0]["review_state"] == "REJECTED" and decided[0]["own"] is True


def test_deleting_the_data_expires_the_review_and_removes_the_note(client_as):
    analyst, reviewer = client_as(Role.ANALYST), client_as(Role.REVIEWER)
    waiting = _needs_review(analyst)
    noted = _needs_review(analyst)
    reviewer.post(f"{QUEUE}document/{noted['id']}/", {"decision": "CONFIRMED", "note": "Name ANNA MARIA checked"}, format="json")
    for r in (waiting, noted):
        analyst.post(f"/api/documents/analyses/{r['id']}/delete-data/")
    assert DocumentAnalysis.objects.get(pk=waiting["id"]).review_state == "EXPIRED"
    assert DocumentAnalysis.objects.get(pk=noted["id"]).review_note == ""
    assert reviewer.get(QUEUE).json()["pending"] == 0


def test_queue_scope_and_reviewer_access_to_barcode_analyses(client_as):
    from apps.barcode_decoder.models import BarcodeAnalysis
    from apps.barcode_decoder.services import run_analysis

    from .images import as_png, barcode, on_canvas
    analyst, other, reviewer = client_as(Role.ANALYST), client_as(Role.ANALYST, "other"), client_as(Role.REVIEWER)
    _needs_review(analyst)
    analysis = run_analysis(user=analyst.user, name="ean.png", data=as_png(on_canvas(barcode())))
    BarcodeAnalysis.objects.filter(pk=analysis.pk).update(status="REVIEW_REQUIRED", review_state="PENDING")
    assert other.get(QUEUE).json()["pending"] == 0      # analysts see only their own items
    assert len(reviewer.get(QUEUE).json()["results"]) == 2
    assert reviewer.get(f"/api/analyzer/analyses/{analysis.pk}/").status_code == 200
    assert other.get(f"/api/analyzer/analyses/{analysis.pk}/").status_code == 404
    assert reviewer.post(f"{QUEUE}barcode/{analysis.pk}/", {"decision": "CONFIRMED"}, format="json").status_code == 200
    assert reviewer.post(f"{QUEUE}nothing/1/", {"decision": "CONFIRMED"}, format="json").status_code == 404
