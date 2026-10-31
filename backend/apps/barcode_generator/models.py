import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O or 1/I, so references read back clearly


def new_test_reference() -> str:
    """e.g. GEN-20261031-7F3KQ9"""
    return f"GEN-{timezone.localdate():%Y%m%d}-{''.join(secrets.choice(_ALPHABET) for _ in range(6))}"


def _upload_to(instance, filename):
    return f"generated/{timezone.now():%Y/%m}/{filename}"


class VerificationStatus(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    UNAVAILABLE = "UNAVAILABLE", "Not checked (decoder unavailable)"


class GenerationBatch(models.Model):
    """One CSV upload. Row-by-row results are kept in `report`."""

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    source_name = models.CharField(max_length=200)
    total_rows = models.PositiveIntegerField(default=0)
    succeeded = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    options = models.JSONField(default=dict, blank=True)
    report = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class GeneratedBarcode(models.Model):
    test_reference = models.CharField(max_length=32, unique=True, default=new_test_reference, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name="generated_barcodes")
    batch = models.ForeignKey(GenerationBatch, null=True, blank=True, on_delete=models.CASCADE, related_name="barcodes")
    batch_row = models.PositiveIntegerField(null=True, blank=True)

    format = models.CharField(max_length=16, db_index=True)
    schema_id = models.CharField(max_length=64)
    label = models.CharField(max_length=80, blank=True)
    input_payload = models.TextField(blank=True, help_text="What was typed, for plain text.")
    input_fields = models.JSONField(default=dict, blank=True, help_text="Field values, for structured schemas.")
    expected_decode = models.TextField(help_text="Exactly what a reader should return.")
    check_digit = models.CharField(max_length=2, blank=True)
    options = models.JSONField(default=dict)
    render_details = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)

    png = models.FileField(upload_to=_upload_to)
    svg = models.FileField(upload_to=_upload_to)
    png_sha256 = models.CharField(max_length=64)
    width_px = models.PositiveIntegerField()
    height_px = models.PositiveIntegerField()

    verification_status = models.CharField(max_length=12, choices=VerificationStatus.choices, db_index=True)
    decoded_text = models.TextField(null=True, blank=True)
    decoded_format = models.CharField(max_length=32, blank=True)
    verification_detail = models.CharField(max_length=255, blank=True)

    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.test_reference} ({self.format})"
