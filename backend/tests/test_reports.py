"""PDF and CSV reports: right content, right audience, no personal data where there shouldn't be any."""
import csv
import io

import pymupdf

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.barcode_decoder.services import run_analysis

from .images import AAMVA_LIKE, as_png, barcode, on_canvas, pdf417_raw
from .specimens import TD3_VALID

SUMMARY = "/api/reports/summary/"


def _text(pdf: bytes) -> str:
    assert pdf.startswith(b"%PDF")
    return "\n".join(page.get_text() for page in pymupdf.open(stream=pdf, filetype="pdf"))


def _document(client, **extra):
    return client.post("/api/documents/analyses/", {"mrz_text": "\n".join(TD3_VALID), "authorised": True, **extra},
                       format="json").json()


def test_document_report_is_confidential_until_the_data_is_deleted(client_as):
    analyst = client_as(Role.ANALYST)
    record = _document(analyst)
    text = _text(analyst.get(record["links"]["pdf"]).content)
    assert "CONFIDENTIAL" in text and "ERIKSSON" in text and "Authenticity not checked" in text
    assert AuditEvent.objects.filter(action="report.downloaded", metadata__report="document_analysis").exists()
    analyst.post(f"/api/documents/analyses/{record['id']}/delete-data/")
    after = _text(analyst.get(record["links"]["pdf"]).content)
    assert "ERIKSSON" not in after and "L898902C3" not in after and "CONFIDENTIAL" not in after
    assert "Personal data was deleted" in after


def test_barcode_report_keeps_identity_data_withheld_and_escapes_text(client_as):
    analyst = client_as(Role.ANALYST)
    sensitive = run_analysis(user=analyst.user, name="id.png", data=as_png(on_canvas(pdf417_raw(AAMVA_LIKE))))
    text = _text(analyst.get(f"/api/analyzer/analyses/{sensitive.pk}/export/?type=pdf").content)
    assert "Withheld" in text and "SAMPLE" not in text and "T64235789" not in text
    tricky = run_analysis(user=analyst.user, name="qr.png", data=as_png(on_canvas(barcode("qr", "<b>bold</b> & more"))))
    assert "<b>bold</b> & more" in _text(analyst.get(f"/api/analyzer/analyses/{tricky.pk}/export/?type=pdf").content)


def test_summary_counts_by_scope_and_role(client_as):
    analyst, other, reviewer = client_as(Role.ANALYST), client_as(Role.ANALYST, "other"), client_as(Role.REVIEWER)
    _document(analyst)
    _document(analyst, document_type="id_card")  # needs review
    _document(other)
    mine = analyst.get(SUMMARY).json()
    assert mine["scope"] == "own" and mine["sections"]["documents"]["total"] == 2
    assert mine["sections"]["documents"]["by_status"] == {"PASS": 1, "REVIEW_REQUIRED": 1}
    assert mine["sections"]["documents"]["reviews"] == {"PENDING": 1}
    everyone = reviewer.get(SUMMARY).json()
    assert everyone["scope"] == "everyone" and everyone["sections"]["documents"]["total"] == 3
    assert {"code": "document.type", "name": "Document type matches", "module": "documents", "failed": 0, "review": 1} in everyone["rules"]
    assert "documents" not in client_as(Role.DEVELOPER).get(SUMMARY).json()["sections"]


def test_summary_downloads_contain_counts_only(client_as):
    reviewer = client_as(Role.REVIEWER)
    _document(client_as(Role.ANALYST))
    rows = list(csv.reader(io.StringIO(reviewer.get(SUMMARY + "?type=csv").content.decode("utf-8-sig"))))
    assert rows[0] == ["section", "measure", "value"] and ["Document Analysis", "result: PASS", "1"] in rows
    text = _text(reviewer.get(SUMMARY + "?type=pdf").content)
    assert "Activity summary" in text and "Document Analysis" in text
    assert "ERIKSSON" not in text and "L898902C3" not in text
    assert AuditEvent.objects.filter(action="report.downloaded", metadata__report="summary").count() == 2


def test_summary_rejects_bad_periods(client_as):
    reader = client_as(Role.READ_ONLY)
    assert reader.get(SUMMARY + "?start=yesterday").status_code == 400
    assert reader.get(SUMMARY + "?start=2026-11-02&end=2026-11-01").status_code == 400
    assert reader.get(SUMMARY + "?start=2024-01-01&end=2026-11-01").status_code == 400
    assert reader.get(SUMMARY + "?type=docx").status_code == 400
