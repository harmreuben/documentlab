from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.documents.services import store_upload
from core.files import FileRejected, check_upload, load_pages
from core.identity import compare as comparer
from core.identity.analyse import analyse_document, analyse_mrz_text

from .models import DocumentAnalysis, DocumentComparison

__all__ = ["FileRejected", "analyse_upload", "analyse_typed_mrz", "compare", "purge_expired", "visible_to"]

# Roles that may see every record (reviewers check other people's work in Phase 9).
SEE_ALL = (Role.ADMINISTRATOR, Role.REVIEWER)


def visible_to(queryset, user):
    return queryset if user.role in SEE_ALL else queryset.filter(created_by=user)


def purge_expired(now=None) -> int:
    """Delete personal data whose retention period has ended. Safe to run at any time."""
    now = now or timezone.now()
    count = 0
    for record in DocumentAnalysis.objects.filter(purged_at__isnull=True, expires_at__lte=now):
        record.purge("retention period ended")
        count += 1
    for record in DocumentComparison.objects.filter(purged_at__isnull=True, expires_at__lte=now):
        record.purge("retention period ended")
        count += 1
    return count


def _save(user, report, upload=None) -> DocumentAnalysis:
    data = report.as_dict()
    return DocumentAnalysis.objects.create(
        created_by=user, upload=upload, source=report.source, authorised=True,
        requested_type=report.requested_type, detected_type=report.detected_type, status=report.status,
        summary=report.summary[:400], next_action=report.next_action[:300], checks=data["checks"],
        fields=report.fields, mrz=report.mrz, licence=report.licence, ocr=report.ocr, pages=report.pages,
        warnings=report.warnings, ocr_engine=report.ocr_engine[:80], duration_ms=report.duration_ms,
    )


@transaction.atomic
def analyse_upload(*, user, name: str, data: bytes, requested_type: str, today: date | None = None) -> DocumentAnalysis:
    kind, warnings = check_upload(name, data)
    loaded = load_pages(kind, data)
    report = analyse_document(loaded, requested_type, warnings, today)
    upload = store_upload(user=user, name=name, data=data, kind=kind, page_count=loaded.page_count,
                          purpose="document_analysis")
    return _save(user, report, upload)


def analyse_typed_mrz(*, user, text: str, requested_type: str, today: date | None = None) -> DocumentAnalysis:
    return _save(user, analyse_mrz_text(text, requested_type, today))


def compare(*, user, analyses: list[DocumentAnalysis]) -> DocumentComparison:
    docs = [{"reference": a.reference, "document_type": a.detected_type, "fields": a.fields} for a in analyses]
    result = comparer.compare(docs)
    record = DocumentComparison.objects.create(
        created_by=user, status=result["status"], summary=result["summary"][:300], rows=result["rows"],
        expires_at=min(a.expires_at for a in analyses),  # never outlives the documents it compares
    )
    record.analyses.set(analyses)
    return record
