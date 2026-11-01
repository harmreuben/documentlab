"""Testing Laboratory: fixtures (inputs with expected results), runs, and one result per fixture per run.

Fixtures hold synthetic data only. The API refuses inputs that look like a real person's document.
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.testlab.expect import MODULES

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def new_run_reference() -> str:
    return f"RUN-{timezone.localdate():%Y%m%d}-{''.join(secrets.choice(_ALPHABET) for _ in range(6))}"


def fixture_path(instance, filename: str) -> str:
    # A random name on disk; the original name is kept in the database only.
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"fixtures/{secrets.token_hex(12)}.{extension}"


class Fixture(models.Model):
    FILE, MRZ_TEXT = "file", "mrz_text"

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    module = models.CharField(max_length=16, choices=list(MODULES.items()))
    tags = models.JSONField(default=list, blank=True)
    builtin_key = models.CharField(max_length=40, unique=True, null=True, blank=True,
                                   help_text="Set for the standard fixtures; their expectations are defined in code.")
    input_type = models.CharField(max_length=10, choices=[(FILE, "File"), (MRZ_TEXT, "Typed MRZ")])
    file = models.FileField(upload_to=fixture_path, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    file_kind = models.CharField(max_length=8, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    mrz_text = models.TextField(blank=True)
    options = models.JSONField(default=dict, blank=True)
    expected = models.JSONField(default=dict)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="test_fixtures")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module", "name"]

    def __str__(self):
        return self.name

    @property
    def is_builtin(self) -> bool:
        return bool(self.builtin_key)

    def read_bytes(self) -> bytes | None:
        if not self.file:
            return None
        with self.file.open("rb") as handle:
            return handle.read()


class TestRun(models.Model):
    RUNNING, COMPLETE, INTERRUPTED = "RUNNING", "COMPLETE", "INTERRUPTED"

    reference = models.CharField(max_length=32, unique=True, default=new_run_reference)
    status = models.CharField(max_length=12, default=RUNNING,
                              choices=[(RUNNING, "Running"), (COMPLETE, "Complete"), (INTERRUPTED, "Interrupted")])
    scope = models.JSONField(default=dict, blank=True)     # {"module": ..., "tag": ..., "fixture_ids": [...]}
    note = models.CharField(max_length=200, blank=True)
    total = models.PositiveIntegerField(default=0)
    passed = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    versions = models.JSONField(default=dict, blank=True)  # app, decoder and OCR versions used
    baseline = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="test_runs")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]

    __test__ = False  # stops pytest treating this model as a test class when it's imported into tests

    def __str__(self):
        return self.reference

    @property
    def done(self) -> int:
        return self.passed + self.failed + self.errors


class CaseResult(models.Model):
    PASS, FAIL, ERROR = "PASS", "FAIL", "ERROR"
    # Compared with the same fixture in the baseline run.
    NEW, UNCHANGED, NEW_FAILURE, FIXED, STILL_FAILING = "new", "unchanged", "new_failure", "fixed", "still_failing"

    run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name="cases")
    fixture = models.ForeignKey(Fixture, null=True, blank=True, on_delete=models.SET_NULL, related_name="results")
    position = models.PositiveIntegerField(default=0)
    fixture_name = models.CharField(max_length=120)
    module = models.CharField(max_length=16)
    outcome = models.CharField(max_length=8, choices=[(PASS, "Pass"), (FAIL, "Fail"), (ERROR, "Error")])
    change = models.CharField(max_length=16, default=NEW)
    previous_outcome = models.CharField(max_length=8, blank=True)
    expected = models.JSONField(default=dict)
    actual = models.JSONField(null=True, blank=True)
    comparisons = models.JSONField(default=list)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
