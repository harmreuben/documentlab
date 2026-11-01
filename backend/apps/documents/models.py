import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def _upload_to(instance, filename):
    # The user's file name is never used on disk: only a random name and the detected type.
    return f"uploads/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{instance.kind}"


class UploadedFile(models.Model):
    """A file someone uploaded for analysis. The original name is kept for display only."""

    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="uploads")
    purpose = models.CharField(max_length=32, default="barcode_analysis")
    original_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=8)  # png | jpeg | pdf, detected from the content
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    page_count = models.PositiveIntegerField(default=1)
    file = models.FileField(upload_to=_upload_to, null=True, blank=True)
    file_removed_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def file_available(self) -> bool:
        return bool(self.file)

    def remove_file(self, reason: str) -> None:
        """Delete the stored copy but keep the record (name, size, fingerprint) for the audit trail."""
        if self.file:
            self.file.delete(save=False)
        self.file = None
        self.file_removed_reason = reason[:200]
        self.save(update_fields=["file", "file_removed_reason"])

    def __str__(self) -> str:
        return f"{self.original_name} ({self.kind}, {self.size_bytes} bytes)"
