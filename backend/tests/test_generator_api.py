import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.barcode_generator.models import GeneratedBarcode

pytestmark = pytest.mark.django_db
BASE = "/api/generator"


def make(c, **body):
    body.setdefault("format", "code128")
    body.setdefault("payload", "DL-TEST-000001")
    return c.post(f"{BASE}/barcodes/", body, format="json")


# --- Reference data --------------------------------------------------------------------------

def test_formats_lists_seven_formats_with_option_controls(client_as):
    data = client_as(Role.READ_ONLY).get(f"{BASE}/formats/").json()
    assert [f["key"] for f in data["formats"]] == ["qr", "code128", "code39", "ean13", "ean8", "upca", "pdf417"]
    qr = data["formats"][0]
    assert {o["name"] for o in qr["options"]} >= {"error_correction", "module_size", "foreground"}
    assert len(data["schemas"]) == 4


def test_sample_endpoint_returns_fictional_data(client_as):
    c = client_as(Role.ANALYST)
    assert c.get(f"{BASE}/sample/?format=ean13").json()["payload"].startswith("2")
    fields = c.get(f"{BASE}/sample/?format=qr&schema=documentlab.asset-tag.v1").json()["fields"]
    assert fields["asset_id"].startswith("TEST-")


# --- Live check -------------------------------------------------------------------------------

def test_check_returns_preview_and_verification_without_saving(client_as):
    c = client_as(Role.ANALYST)
    r = c.post(f"{BASE}/check/", {"format": "ean13", "payload": "590123412345"}, format="json").json()
    assert r["ok"] and r["expected_decode"] == "5901234123457"
    assert r["preview"]["svg_data_url"].startswith("data:image/svg+xml;base64,")
    assert r["verification"]["status"] == "PASS"
    assert GeneratedBarcode.objects.count() == 0


def test_check_reports_errors_without_a_preview(client_as):
    r = client_as(Role.ANALYST).post(f"{BASE}/check/", {"format": "ean8", "payload": "12"}, format="json").json()
    assert not r["ok"] and r["preview"] is None
    assert r["errors"][0]["field"] == "payload"


# --- Generating -------------------------------------------------------------------------------

def test_generate_saves_files_metadata_and_audit(client_as):
    c = client_as(Role.ANALYST, "ann")
    r = make(c, label="Bench test")
    assert r.status_code == 201
    body = r.json()
    assert body["test_reference"].startswith("GEN-")
    assert body["verification_status"] == "PASS"
    assert body["expected_decode"] == body["decoded_text"] == "DL-TEST-000001"
    assert body["schema_id"] == "documentlab.text.v1"
    record = GeneratedBarcode.objects.get()
    assert record.png.size > 0 and record.svg.size > 0 and len(record.png_sha256) == 64
    event = AuditEvent.objects.get(action="barcode.generated")
    assert event.metadata["test_reference"] == body["test_reference"]
    assert "DL-TEST-000001" not in str(event.metadata)  # payloads stay out of the audit log


def test_structured_pdf417_generation(client_as):
    r = make(client_as(Role.DEVELOPER), format="pdf417", payload="", schema="documentlab.test-fixture.v1",
             fields={"test_id": "TEST-FX-1", "description": "Round trip", "expected_result": "PASS"})
    assert r.status_code == 201
    assert r.json()["input_fields"]["test_id"] == "TEST-FX-1"
    assert r.json()["verification_status"] == "PASS"


def test_invalid_input_returns_400_and_saves_nothing(client_as):
    r = make(client_as(Role.ANALYST), format="ean13", payload="5901234123458")
    assert r.status_code == 400
    assert "check digit" in r.json()["detail"]
    assert GeneratedBarcode.objects.count() == 0


def test_identity_layout_is_refused_and_logged(client_as):
    payload = "@\n\x1e\rANSI 636000080002DL00410278DLDAQT64235789\nDCSSAMPLE\nDBB01011990"
    r = make(client_as(Role.ANALYST), format="pdf417", payload=payload)
    assert r.status_code == 400 and r.json()["blocked"] is True
    assert GeneratedBarcode.objects.count() == 0
    assert AuditEvent.objects.filter(action="barcode.refused").exists()


def test_read_only_users_cannot_generate(client_as):
    assert make(client_as(Role.READ_ONLY)).status_code == 403


def test_history_shows_own_barcodes_admin_sees_all(client_as):
    ann, bob, admin = client_as(Role.ANALYST, "ann"), client_as(Role.ANALYST, "bob"), client_as(Role.ADMINISTRATOR)
    make(ann), make(ann), make(bob)
    assert ann.get(f"{BASE}/barcodes/").json()["count"] == 2
    assert bob.get(f"{BASE}/barcodes/").json()["count"] == 1
    assert admin.get(f"{BASE}/barcodes/").json()["count"] == 3


def test_history_filters(client_as):
    c = client_as(Role.ANALYST)
    make(c), make(c, format="qr", payload="TEST")
    assert c.get(f"{BASE}/barcodes/?format=qr").json()["count"] == 1
    assert c.get(f"{BASE}/barcodes/?status=FAIL").json()["count"] == 0


@pytest.mark.parametrize("kind,content_type,magic", [
    ("png", "image/png", b"\x89PNG"), ("svg", "image/svg+xml", b"<"), ("pdf", "application/pdf", b"%PDF"),
])
def test_downloads(client_as, kind, content_type, magic):
    c = client_as(Role.ANALYST)
    barcode_id = make(c).json()["id"]
    r = c.get(f"{BASE}/barcodes/{barcode_id}/download/?type={kind}")
    assert r.status_code == 200 and r["Content-Type"] == content_type
    assert r.content.lstrip().startswith(magic)
    assert "attachment" in r["Content-Disposition"]
    assert GeneratedBarcode.objects.get(pk=barcode_id).download_count == 1


def test_other_users_cannot_download_your_barcode(client_as):
    barcode_id = make(client_as(Role.ANALYST, "ann")).json()["id"]
    assert client_as(Role.ANALYST, "bob").get(f"{BASE}/barcodes/{barcode_id}/download/").status_code == 404


def test_dashboard_counts_generated_barcodes(client_as):
    c = client_as(Role.ANALYST)
    make(c), make(c)
    assert c.get("/api/dashboard/summary/").json()["counts"]["barcodes_generated"] == 2


# --- Batches ---------------------------------------------------------------------------------

def upload(c, text: str, name="codes.csv", options=None):
    file = SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")
    data = {"file": file}
    if options is not None:
        data["options"] = options
    return c.post(f"{BASE}/batches/", data, format="multipart")


CSV_OK = (
    "format,payload,label,schema,asset_id,name\n"
    "ean13,590123412345,Shelf 1,,,\n"
    "code128,DL-TEST-2,,,,\n"
    "qr,,Asset,documentlab.asset-tag.v1,TEST-AST-1,Scanner\n"
    "ean8,12,Bad row,,,\n"
    "code128,=SUM(A1),Formula,,,\n"
)


def test_batch_generates_good_rows_and_reports_bad_ones(client_as):
    c = client_as(Role.ANALYST)
    r = upload(c, CSV_OK)
    assert r.status_code == 201
    body = r.json()
    assert (body["total_rows"], body["succeeded"], body["failed"]) == (5, 4, 1)
    bad = next(e for e in body["report"] if e["status"] == "REJECTED")
    assert bad["row"] == 5 and "needs 7 digits" in bad["message"]
    assert all(e["verification"] == "PASS" for e in body["report"] if e["status"] == "GENERATED")
    assert AuditEvent.objects.filter(action="barcode.batch_generated").exists()


def test_batch_zip_contains_files_report_and_labels(client_as):
    c = client_as(Role.ANALYST)
    batch_id = upload(c, CSV_OK).json()["id"]
    r = c.get(f"{BASE}/batches/{batch_id}/download/?type=zip")
    archive = zipfile.ZipFile(io.BytesIO(r.content))
    names = archive.namelist()
    assert "report.csv" in names and "labels.pdf" in names
    assert sum(n.startswith("png/") for n in names) == 4 and sum(n.startswith("svg/") for n in names) == 4
    report = archive.read("report.csv").decode()
    assert "'=SUM(A1)" in report  # formula neutralised for spreadsheet programs


def test_batch_applies_shared_options(client_as):
    c = client_as(Role.ANALYST)
    upload(c, "format,payload\nqr,TEST\n", options='{"error_correction": "H"}')
    assert GeneratedBarcode.objects.get().options["error_correction"] == "H"


@pytest.mark.parametrize("text,name,expected", [
    ("payload\nabc\n", "codes.csv", "'format' column"),
    ("format,payload\n", "codes.csv", "no data rows"),
    ("format,payload\n" + "code128,TEST\n" * 501, "codes.csv", "more than 500 rows"),
    ("format,payload\ncode128,TEST\n", "codes.xlsx", "Upload a .csv file"),
])
def test_batch_rejects_unusable_files(client_as, text, name, expected):
    r = upload(client_as(Role.ANALYST), text, name=name)
    assert r.status_code == 400 and expected in r.json()["detail"]


def test_batch_rejects_files_over_1mb(client_as):
    big = "format,payload\n" + ("code128," + "X" * 70 + "\n") * 16000
    r = upload(client_as(Role.ANALYST), big)
    assert r.status_code == 400 and "larger than 1 MB" in r.json()["detail"]


def test_read_only_users_cannot_run_batches(client_as):
    assert upload(client_as(Role.READ_ONLY), "format,payload\ncode128,T\n").status_code == 403
