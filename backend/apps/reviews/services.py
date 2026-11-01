"""The review workflow: results that need review wait for a second person's decision.

Rules:
- Only reviewers and administrators decide, and never on their own analysis (four-eyes principle).
- A decision never changes the technical result. "Confirmed" means a person compared the flagged items
  with the source and found them correct; it does not mean the document is genuine.
- Rejections need a note. Notes are deleted with a document's personal data.
"""
from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import Role

from .models import ReviewState

REVIEWER_ROLES = (Role.ADMINISTRATOR, Role.REVIEWER)
NEEDS_REVIEW = "REVIEW_REQUIRED"


class ReviewRefused(Exception):
    pass


def initial_review_state(status: str) -> str:
    return ReviewState.PENDING if status == NEEDS_REVIEW else ReviewState.NONE


def kinds():
    from apps.barcode_decoder.models import BarcodeAnalysis
    from apps.document_analysis.models import DocumentAnalysis
    return {"barcode": BarcodeAnalysis, "document": DocumentAnalysis}


def refusal(user, record) -> str | None:
    """Why this user can't review this record now, or None if they can."""
    if user.role not in REVIEWER_ROLES:
        return "Only reviewers and administrators can review results."
    if record.review_state != ReviewState.PENDING:
        return "This result isn't waiting for review."
    if record.created_by_id == user.pk:
        return "You can't review your own analysis. Another reviewer must check it."
    if getattr(record, "purged_at", None):
        return "The document's data has been deleted, so it can't be reviewed."
    return None


def decide(user, record, decision: str, note: str):
    reason = refusal(user, record)
    if reason:
        raise ReviewRefused(reason)
    if decision not in (ReviewState.CONFIRMED, ReviewState.REJECTED):
        raise ReviewRefused("Choose to confirm or reject.")
    note = (note or "").strip()
    if decision == ReviewState.REJECTED and not note:
        raise ReviewRefused("Say why you're rejecting it, so the person who ran the analysis knows what to fix.")
    record.review_state, record.review_note = decision, note[:500]
    record.reviewed_by, record.reviewed_at = user, timezone.now()
    record.save(update_fields=["review_state", "review_note", "reviewed_by", "reviewed_at"])
    return record


def pending_count(user) -> int:
    total = 0
    for model in kinds().values():
        qs = model.objects.filter(review_state=ReviewState.PENDING)
        if user.role not in REVIEWER_ROLES:
            qs = qs.filter(created_by=user)
        total += qs.count()
    return total


def queue(user, decided: bool = False, limit: int = 200) -> list[dict]:
    """Pending items oldest first (fair order), or recent decisions newest first."""
    items = []
    for kind, model in kinds().items():
        qs = model.objects.select_related("created_by", "reviewed_by")
        qs = qs.exclude(review_state__in=["", ReviewState.PENDING]) if decided else qs.filter(review_state=ReviewState.PENDING)
        if user.role not in REVIEWER_ROLES:
            qs = qs.filter(created_by=user)
        for record in qs.order_by("-reviewed_at" if decided else "created_at")[:limit]:
            items.append(item(kind, record, user))
    key = (lambda i: i["reviewed_at"] or "") if decided else (lambda i: i["created_at"])
    return sorted(items, key=key, reverse=decided)[:limit]


def item(kind: str, record, user) -> dict:
    is_document = kind == "document"
    return {
        "kind": kind, "id": record.pk, "reference": record.reference,
        "label": "Document Analysis" if is_document else "Barcode Analyzer",
        "created_at": record.created_at.isoformat(),
        "created_by": record.created_by.get_username() if record.created_by else None,
        "status": record.status, "summary": record.summary,
        "path": f"/documents/{record.pk}" if is_document else f"/analyzer/{record.pk}",
        **review_info(record, user),
    }


def review_info(record, user=None) -> dict:
    info = {
        "review_state": record.review_state,
        "review_label": ReviewState(record.review_state).label,
        "reviewed_by": record.reviewed_by.get_username() if record.reviewed_by else None,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "review_note": record.review_note,
    }
    if user is not None:
        info["can_review"] = refusal(user, record) is None
        info["own"] = record.created_by_id == user.pk
    return info
