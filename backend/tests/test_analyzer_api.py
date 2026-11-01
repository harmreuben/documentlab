import csv
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.barcode_decoder.models import BarcodeAnalysis
from apps.documents.models import UploadedFile

from . import images as img

pytestmark = pytest.mark.django_db
BASE = "/api/analyzer/analyses"


def upload(c, data: bytes, name="scan.png", expected=None):
    body = {"file": SimpleUploadedFile(name, data)}
    if expected is not None:
        body["expected"] = expected
    return c.post(f"{BASE}/", body, format="multipart")


def test_upload_returns_full_analysis(client_as):
    c = client_as(Role.ANALYST)
    r = upload(c, img.as_png(img.barcode()), expected="5901234123457")
    assert r.status_code == 201
    body = r.json()
    assert body["reference"].startswith("ANA-") and body["status"] == "PASS"
    assert body["upload"]["kind"] == "png" and len(body["upload"]["sha256"]) == 64
    assert body["barcodes"][0]["text"] == "5901234123457"
    assert body["barcodes"][0]["expected_match"] is True
    assert {c["category"] for c in body["checks"]} == {"file_integrity", "image_quality", "barcode_decoding",
                                                       "data_format", "expected_value"}
    assert body["links"]["pages"] == [f"{BASE}/{body['id']}/image/?page=1"]


def test_upload_is_audited_without_file_name_or_content(client_as):
    c = client_as(Role.ANALYST)
    upload(c, img.as_png(img.barcode()), name="customer-records.png")
    event = AuditEvent.objects.get(action="barcode.analysed")
    assert event.metadata["status"] == "PASS"
    assert "customer-records" not in json.dumps(event.metadata)
    assert "5901234123457" not in json.dumps(event.metadata)


def test_rejected_files_save_nothing(client_as):
    r = upload(client_as(Role.ANALYST), b"plain text pretending", name="fake.png")
    assert r.status_code == 400 and "Only PNG, JPEG and PDF" in r.json()["detail"]
    assert not UploadedFile.objects.exists() and not BarcodeAnalysis.objects.exists()


def test_missing_file(client_as):
    assert client_as(Role.ANALYST).post(f"{BASE}/", {}, format="multipart").status_code == 400


def test_identity_payload_is_withheld_and_file_deleted(client_as):
    c = client_as(Role.ANALYST)
    body = upload(c, img.as_png(img.pdf417_raw(img.AAMVA_LIKE)), name="licence.png", expected="secret").json()
    assert body["status"] == "REVIEW_REQUIRED" and body["sensitive"] is True
    assert body["barcodes"][0]["text"] is None
    assert body["expected_value"] == ""
    assert body["upload"]["file_available"] is False and "pages" not in body["links"]
    stored = UploadedFile.objects.get()
    assert not stored.file and "identity" in stored.file_removed_reason
    assert c.get(f"{BASE}/{body['id']}/image/?page=1").status_code == 404
    export = c.get(f"{BASE}/{body['id']}/export/?type=json").content.decode()
    assert "DAQ" not in export and "ANSI" not in export


def test_page_image_is_reencoded_png(client_as):
    c = client_as(Role.ANALYST)
    body = upload(c, img.as_jpeg(img.barcode()), name="photo.jpg").json()
    r = c.get(f"{BASE}/{body['id']}/image/?page=1")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).format == "PNG"


def test_pdf_pages_are_served(client_as):
    c = client_as(Role.ANALYST)
    body = upload(c, img.pdf_with([img.barcode()], blank_first=True), name="scan.pdf").json()
    assert body["upload"]["page_count"] == 2 and body["barcodes"][0]["page"] == 2
    assert c.get(f"{BASE}/{body['id']}/image/?page=2").status_code == 200
    assert c.get(f"{BASE}/{body['id']}/image/?page=9").status_code == 404


def test_decoded_barcode_is_linked_to_your_generated_one(client_as):
    c = client_as(Role.ANALYST)
    generated = c.post("/api/generator/barcodes/", {"format": "code128", "payload": "DL-TEST-777"}, format="json").json()
    body = upload(c, img.as_png(img.barcode("code128", "DL-TEST-777"))).json()
    assert body["barcodes"][0]["matched_generated"]["test_reference"] == generated["test_reference"]


def test_from_generated_analyses_the_saved_png(client_as):
    c = client_as(Role.ANALYST)
    ref = c.post("/api/generator/barcodes/", {"format": "qr", "payload": "TEST-QR"}, format="json").json()["test_reference"]
    r = c.post(f"{BASE}/from-generated/", {"test_reference": ref.lower()}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PASS" and body["source_generated"] == ref
    assert body["expected_value"] == "TEST-QR"


def test_from_generated_respects_ownership(client_as):
    ann, bob = client_as(Role.ANALYST, "ann"), client_as(Role.ANALYST, "bob")
    ref = ann.post("/api/generator/barcodes/", {"format": "qr", "payload": "TEST"}, format="json").json()["test_reference"]
    assert bob.post(f"{BASE}/from-generated/", {"test_reference": ref}, format="json").status_code == 404


def test_history_scoping_and_filters(client_as):
    ann, bob, admin = client_as(Role.ANALYST, "ann"), client_as(Role.ANALYST, "bob"), client_as(Role.ADMINISTRATOR)
    upload(ann, img.as_png(img.barcode()))
    upload(ann, img.as_png(img.blurred(img.barcode())))
    upload(bob, img.as_png(img.barcode()))
    assert ann.get(f"{BASE}/").json()["count"] == 2
    assert admin.get(f"{BASE}/").json()["count"] == 3
    assert ann.get(f"{BASE}/?status=FAIL").json()["count"] == 1
    other = BarcodeAnalysis.objects.get(created_by__username="bob")
    assert ann.get(f"{BASE}/{other.pk}/").status_code == 404
    assert ann.get(f"{BASE}/{other.pk}/image/?page=1").status_code == 404


def test_csv_export_neutralises_formulas(client_as):
    c = client_as(Role.ANALYST)
    body = upload(c, img.as_png(img.barcode("code128", "=HYPERLINK(1)"))).json()
    rows = list(csv.reader(io.StringIO(c.get(f"{BASE}/{body['id']}/export/?type=csv").content.decode("utf-8-sig"))))
    assert rows[0][0] == "analysis" and rows[1][6] == "'=HYPERLINK(1)"


def test_read_only_users_can_view_but_not_upload(client_as):
    assert upload(client_as(Role.READ_ONLY), img.as_png(img.barcode())).status_code == 403


def test_dashboard_counts_decoded_barcodes(client_as):
    c = client_as(Role.ANALYST)
    upload(c, img.as_png(img.on_canvas(img.barcode("qr", "TEST-1"), img.barcode())))
    assert c.get("/api/dashboard/summary/").json()["counts"]["barcodes_decoded"] == 2
