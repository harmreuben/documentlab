"""Identity-document records. Personal data is kept only until `expires_at`, then deleted.

After deletion ("purge") a record keeps its reference, dates, document type, overall status and
the codes and statuses of its checks, so statistics and the audit trail survive, but no names,
numbers, dates, OCR text, MRZ lines or images remain.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.documents.models import UploadedFile
from apps.reviews.models import ReviewMixin, ReviewState

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _reference(prefix: str) -> str:
    return f"{prefix}-{timezone.localdate():%Y%m%d}-{''.join(secrets.choice(_ALPHABET) for _ in range(6))}"


def new_document_reference() -> str:
    return _reference("DOC")


def new_comparison_reference() -> str:
    return _reference("CMP")


def default_expiry():
    return timezone.now() + timedelta(days=settings.DOCUMENT_RETENTION_DAYS)


def _strip_checks(checks: list) -> list:
    return [{k: c.get(k) for k in ("category", "code", "name", "status")} for c in checks]


class PurgeableMixin(models.Model):
    expires_at = models.DateTimeField(default=default_expiry, db_index=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    purge_reason = models.CharField(max_length=120, blank=True)

    class Meta:
        abstract = True

    @property
    def purged(self) -> bool:
        return self.purged_at is not None


class DocumentAnalysis(ReviewMixin, PurgeableMixin):
    reference = models.CharField(max_length=32, unique=True, default=new_document_reference, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    upload = models.ForeignKey(UploadedFile, null=True, blank=True, on_delete=models.PROTECT, related_name="document_analyses")
    source = models.CharField(max_length=16)  # upload | manual_mrz
    authorised = models.BooleanField(default=False, help_text="The user confirmed they may process this document.")

    requested_type = models.CharField(max_length=20)
    detected_type = models.CharField(max_length=20)
    status = models.CharField(max_length=16, db_index=True)
    summary = models.CharField(max_length=400)
    next_action = models.CharField(max_length=300)

    # Personal data - cleared on purge.
    checks = models.JSONField(default=list)
    fields = models.JSONField(default=dict)
    mrz = models.JSONField(null=True, blank=True)
    licence = models.JSONField(null=True, blank=True)
    ocr = models.JSONField(default=list)
    pages = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    ocr_engine = models.CharField(max_length=80, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "document analyses"

    def purge(self, reason: str) -> None:
        if self.upload:
            self.upload.remove_file(f"Deleted: {reason}")
        self.checks = _strip_checks(self.checks)
        self.fields, self.mrz, self.licence, self.ocr, self.pages, self.warnings = {}, None, None, [], [], []
        self.summary = f"Personal data deleted ({reason})."
        self.next_action = "None."
        self.review_note = ""  # a note may quote the document
        if self.review_state == ReviewState.PENDING:
            self.review_state = ReviewState.EXPIRED
        self.purged_at, self.purge_reason = timezone.now(), reason[:120]
        self.save()

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"


class DocumentComparison(PurgeableMixin):
    reference = models.CharField(max_length=32, unique=True, default=new_comparison_reference, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    analyses = models.ManyToManyField(DocumentAnalysis, related_name="comparisons")
    status = models.CharField(max_length=16)
    summary = models.CharField(max_length=300)
    rows = models.JSONField(default=list)  # personal data - cleared on purge

    class Meta:
        ordering = ["-created_at", "-id"]

    def purge(self, reason: str) -> None:
        self.rows = [{k: r.get(k) for k in ("field", "label", "status")} for r in self.rows]
        self.purged_at, self.purge_reason = timezone.now(), reason[:120]
        self.save()


class SsnCheck(models.Model):
    """Only the masked form (last four digits) and the result are kept. The full number is never stored."""

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    masked = models.CharField(max_length=11)
    format_valid = models.BooleanField()
    status = models.CharField(max_length=16)
    checks = models.JSONField(default=list)
    ruleset_version = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class SsnVerification(models.Model):
    """One request to an external provider. Keeps the consent and the answer, never the full number,
    the name or the date of birth that were sent."""

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    masked = models.CharField(max_length=11)
    provider = models.CharField(max_length=80)
    outcome = models.CharField(max_length=10)          # match | no_match | error
    status = models.CharField(max_length=16)           # PASS | FAIL | UNAVAILABLE
    mismatched = models.JSONField(default=list)        # field names only
    deceased = models.BooleanField(null=True)
    provider_reference = models.CharField(max_length=80, blank=True)
    provider_message = models.CharField(max_length=200, blank=True)
    consent_method = models.CharField(max_length=24)
    consent_reference = models.CharField(max_length=80)
    consent_signed_on = models.DateField()
    purpose = models.CharField(max_length=24)
    ruleset_version = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
