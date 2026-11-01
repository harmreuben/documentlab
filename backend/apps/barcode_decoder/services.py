"""Runs an analysis and stores it. Identity-document payloads are withheld and their files removed."""
from __future__ import annotations

import csv
import io
import json

from django.db import transaction

from apps.accounts.models import Role
from apps.barcode_generator.models import GeneratedBarcode
from apps.documents.services import store_upload
from apps.reviews.services import initial_review_state
from core.barcodes.analyse import analyse
from core.files import FileRejected, check_upload, load_pages
from core.rules.catalogue import RULESET_VERSION

from .models import BarcodeAnalysis, DecodedBarcode

SENSITIVE_REASON = "Removed: the file contained identity-document data."

__all__ = ["FileRejected", "run_analysis", "export_csv", "export_json"]


def _generated_lookup(user, texts: set[str]) -> dict[str, GeneratedBarcode]:
    qs = GeneratedBarcode.objects.filter(expected_decode__in=texts)
    if user.role != Role.ADMINISTRATOR:
        qs = qs.filter(created_by=user)
    found = {}
    for g in qs.order_by("created_at"):
        found.setdefault(g.expected_decode, g)
    return found


@transaction.atomic
def run_analysis(*, user, name: str, data: bytes, expected: str = "", source_generated=None) -> BarcodeAnalysis:
    kind, file_warnings = check_upload(name, data)
    loaded = load_pages(kind, data)
    report = analyse(loaded, expected, file_warnings)

    upload = store_upload(user=user, name=name, data=data, kind=kind, page_count=loaded.page_count,
                          purpose="barcode_analysis")
    analysis = BarcodeAnalysis.objects.create(
        created_by=user, upload=upload, source_generated=source_generated,
        expected_value="" if report.sensitive else (expected or "").strip(),
        status=report.status, summary=report.summary[:300], next_action=report.next_action[:300],
        checks=[c.as_dict() for c in report.checks], pages=report.pages, warnings=report.warnings,
        sensitive=report.sensitive, duration_ms=report.duration_ms, decoder=report.decoder,
        ruleset_version=RULESET_VERSION, review_state=initial_review_state(report.status),
    )

    texts = set()
    for b in report.barcodes:
        if b.text:
            texts |= {b.text, *b.alternatives.values()}
            if b.text.startswith("0") and len(b.text) == 13:
                texts.add(b.text[1:])
    generated = _generated_lookup(user, texts) if texts else {}

    for b in report.barcodes:
        candidates = [b.text, *b.alternatives.values(), (b.text or "")[1:]] if b.text else []
        match = next((generated[t] for t in candidates if t in generated), None)
        DecodedBarcode.objects.create(analysis=analysis, matched_generated=match, **{
            k: v for k, v in b.as_dict().items() if k not in ("format_key",)
        }, format_key=b.format_key or "")

    if report.sensitive:
        upload.remove_file(SENSITIVE_REASON)
    return analysis


# --- Exports ------------------------------------------------------------------------------

def _safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_csv(analysis: BarcodeAnalysis) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["analysis", "file_sha256", "page", "barcode", "format", "status", "decoded_text",
                "data_check", "expected_match", "consistent_reads", "reason"])
    for b in analysis.barcodes.all():
        w.writerow([_safe(x) for x in (
            analysis.reference, analysis.upload.sha256, b.page, b.index, b.format_name, b.status,
            b.text if b.text is not None else "[withheld]", b.interpretation.get("data_check", ""),
            "" if b.expected_match is None else ("yes" if b.expected_match else "no"),
            f"{b.consistent_reads}/{b.attempts}", b.reason)])
    if not analysis.barcodes.exists():
        w.writerow([analysis.reference, analysis.upload.sha256, "", "", "", analysis.status, "", "", "", "", analysis.summary])
    return out.getvalue()


def export_json(analysis: BarcodeAnalysis, serializer_data: dict) -> str:
    return json.dumps(serializer_data, ensure_ascii=False, indent=2, default=str)
