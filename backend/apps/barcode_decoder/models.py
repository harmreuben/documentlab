import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.barcode_generator.models import GeneratedBarcode
from apps.documents.models import UploadedFile

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def new_analysis_reference() -> str:
    """e.g. ANA-20261101-7F3KQ9"""
    return f"ANA-{timezone.localdate():%Y%m%d}-{''.join(secrets.choice(_ALPHABET) for _ in range(6))}"


class Status(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"
    NOT_SUPPORTED = "NOT_SUPPORTED", "Not supported"
    UNAVAILABLE = "UNAVAILABLE", "Unavailable"
    NOT_CHECKED = "NOT_CHECKED", "Not checked"


class BarcodeAnalysis(models.Model):
    reference = models.CharField(max_length=32, unique=True, default=new_analysis_reference, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="analyses")
    upload = models.ForeignKey(UploadedFile, on_delete=models.PROTECT, related_name="barcode_analyses")
    source_generated = models.ForeignKey(GeneratedBarcode, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    expected_value = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    summary = models.CharField(max_length=300)
    next_action = models.CharField(max_length=300)
    checks = models.JSONField(default=list)
    pages = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    sensitive = models.BooleanField(default=False)
    duration_ms = models.PositiveIntegerField(default=0)
    decoder = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "barcode analyses"

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"


class DecodedBarcode(models.Model):
    analysis = models.ForeignKey(BarcodeAnalysis, on_delete=models.CASCADE, related_name="barcodes")
    page = models.PositiveIntegerField()
    index = models.PositiveIntegerField()
    format_name = models.CharField(max_length=40)
    format_key = models.CharField(max_length=16, blank=True)
    supported = models.BooleanField()
    text = models.TextField(null=True, blank=True, help_text="Null when withheld (identity-document data).")
    byte_length = models.PositiveIntegerField()
    valid = models.BooleanField()
    error = models.CharField(max_length=200, blank=True)
    points = models.JSONField(default=list)
    tilt = models.FloatField(default=0)
    ec_level = models.CharField(max_length=16, blank=True)
    symbology_identifier = models.CharField(max_length=8, blank=True)
    consistent_reads = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    alternatives = models.JSONField(default=dict, blank=True)
    interpretation = models.JSONField(default=dict)
    findings = models.JSONField(default=list, blank=True)
    expected_match = models.BooleanField(null=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    reason = models.CharField(max_length=300)
    matched_generated = models.ForeignKey(GeneratedBarcode, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["page", "index"]
