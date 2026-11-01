"""Testing Laboratory operations: fixtures, runs and exports."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import time
from datetime import timedelta
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections, connection, transaction
from django.db.models import F
from django.utils import timezone

from core.barcodes import decode
from core.files import FileRejected, check_upload
from core.ocr import engine as ocr
from core.testlab import builtin, expect, runner

from .models import CaseResult, Fixture, TestRun

STALE_AFTER = timedelta(minutes=10)  # a run with no progress for this long was stopped (e.g. server restart)


class RunInProgress(Exception):
    pass


# --- Fixtures ------------------------------------------------------------------------------------

def fixture_input(fixture: Fixture) -> runner.FixtureInput:
    return runner.FixtureInput(fixture.module, fixture.original_name, fixture.read_bytes(), fixture.mrz_text,
                               dict(fixture.options or {}))


def screen_input(item: runner.FixtureInput) -> None:
    """Refuse anything that isn't clearly synthetic. Raises FileRejected with the reason."""
    if item.data is not None:
        check_upload(item.name, item.data)
    reason = runner.not_synthetic(item.module, runner.analyse(item))
    if reason:
        raise FileRejected(reason)


def save_file(fixture: Fixture, name: str, data: bytes) -> None:
    kind, _ = check_upload(name, data)
    fixture.original_name, fixture.file_kind = name[:255], kind
    fixture.size_bytes, fixture.sha256 = len(data), hashlib.sha256(data).hexdigest()
    if fixture.file:
        fixture.file.delete(save=False)
    fixture.file.save(name, ContentFile(data), save=False)


def load_builtins(user=None) -> tuple[int, int]:
    """Create or refresh the standard fixtures. Returns (created, updated)."""
    created = updated = 0
    for spec in builtin.BUILTINS:
        fixture = Fixture.objects.filter(builtin_key=spec.key).first()
        is_new = fixture is None
        fixture = fixture or Fixture(builtin_key=spec.key, created_by=user)
        fixture.name, fixture.description, fixture.module = spec.name, spec.description, spec.module
        fixture.tags, fixture.options = list(spec.tags), dict(spec.options)
        fixture.expected = expect.validate(spec.module, spec.expected)
        if spec.make:
            name, data = spec.make()
            fixture.input_type = Fixture.FILE
            if fixture.sha256 != hashlib.sha256(data).hexdigest():
                save_file(fixture, name, data)
        else:
            fixture.input_type, fixture.mrz_text = Fixture.MRZ_TEXT, spec.mrz_text
        fixture.save()
        created, updated = created + is_new, updated + (not is_new)
    return created, updated


# --- Runs ----------------------------------------------------------------------------------------

def versions() -> dict:
    _, engine = ocr.status()
    return {"app": settings.APP_VERSION, "decoder": decode.decoder_version(), "ocr": engine}


def mark_stale_runs() -> int:
    cutoff = timezone.now() - STALE_AFTER
    return TestRun.objects.filter(status=TestRun.RUNNING, updated_at__lt=cutoff).update(
        status=TestRun.INTERRUPTED, finished_at=timezone.now())


def select_fixtures(scope: dict):
    qs = Fixture.objects.filter(active=True)
    if scope.get("module"):
        qs = qs.filter(module=scope["module"])
    if scope.get("fixture_ids"):
        qs = qs.filter(pk__in=scope["fixture_ids"])
    fixtures = list(qs.order_by("module", "name"))
    if scope.get("tag"):  # JSON-list filtering differs between SQLite and PostgreSQL, so filter here
        fixtures = [f for f in fixtures if scope["tag"] in (f.tags or [])]
    return fixtures


def start_run(user, scope: dict, note: str = "") -> TestRun:
    mark_stale_runs()
    fixtures = select_fixtures(scope)
    if not fixtures:
        raise ValueError("No active fixtures match. Load the standard fixtures or add one first.")
    with transaction.atomic():
        if TestRun.objects.select_for_update().filter(status=TestRun.RUNNING).exists():
            raise RunInProgress("A test run is already in progress. Wait for it to finish.")
        baseline = TestRun.objects.filter(status=TestRun.COMPLETE).order_by("-created_at", "-id").first()
        run = TestRun.objects.create(scope=scope, note=note[:200], total=len(fixtures), versions=versions(),
                                     baseline=baseline, created_by=user)
    ids = [f.pk for f in fixtures]
    if getattr(settings, "TEST_LAB_RUN_IN_BACKGROUND", True):
        threading.Thread(target=_execute_in_thread, args=(run.pk, ids), daemon=True, name=run.reference).start()
    else:
        execute(run.pk, ids)
        run.refresh_from_db()
    return run


def _execute_in_thread(run_id: int, fixture_ids: list[int]) -> None:
    close_old_connections()
    try:
        execute(run_id, fixture_ids)
    finally:
        connection.close()


def execute(run_id: int, fixture_ids: list[int]) -> None:
    started = time.perf_counter()
    run = TestRun.objects.get(pk=run_id)
    status = TestRun.INTERRUPTED  # unless every fixture gets a result
    try:
        for position, fixture in enumerate(Fixture.objects.filter(pk__in=fixture_ids).order_by("module", "name"), 1):
            try:
                outcome = runner.run(fixture_input(fixture), fixture.expected)
            except Exception as exc:  # noqa: BLE001 - e.g. the fixture's file is missing from disk
                outcome = runner.CaseOutcome(runner.ERROR, None, [], f"The fixture couldn't be loaded: {exc}")
            CaseResult.objects.create(
                run=run, fixture=fixture, position=position, fixture_name=fixture.name, module=fixture.module,
                outcome=outcome.outcome, expected=fixture.expected, actual=outcome.actual,
                comparisons=outcome.comparisons, error=outcome.error, duration_ms=outcome.duration_ms)
            counter = {"PASS": "passed", "FAIL": "failed"}.get(outcome.outcome, "errors")
            TestRun.objects.filter(pk=run.pk).update(**{counter: F(counter) + 1}, updated_at=timezone.now())
        _compare_with_baseline(run)
        status = TestRun.COMPLETE
    finally:
        TestRun.objects.filter(pk=run.pk).update(status=status, finished_at=timezone.now(),
                                                 duration_ms=int((time.perf_counter() - started) * 1000))


def _compare_with_baseline(run: TestRun) -> None:
    if run.baseline_id is None:
        return
    before = dict(CaseResult.objects.filter(run_id=run.baseline_id, fixture__isnull=False)
                  .values_list("fixture_id", "outcome"))
    for case in run.cases.all():
        previous = before.get(case.fixture_id)
        if previous is None:
            change = CaseResult.NEW
        elif previous == CaseResult.PASS:
            change = CaseResult.UNCHANGED if case.outcome == CaseResult.PASS else CaseResult.NEW_FAILURE
        else:
            change = CaseResult.FIXED if case.outcome == CaseResult.PASS else CaseResult.STILL_FAILING
        CaseResult.objects.filter(pk=case.pk).update(change=change, previous_outcome=previous or "")


# --- Exports -------------------------------------------------------------------------------------

def _run_header(run: TestRun) -> dict:
    return {"reference": run.reference, "status": run.status, "created_at": run.created_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_by": run.created_by.get_username() if run.created_by else None,
            "baseline": run.baseline.reference if run.baseline else None, "scope": run.scope, "versions": run.versions,
            "totals": {"total": run.total, "passed": run.passed, "failed": run.failed, "errors": run.errors}}


def export_json(run: TestRun) -> bytes:
    cases = [{"fixture": c.fixture_name, "module": c.module, "outcome": c.outcome, "change": c.change,
              "previous_outcome": c.previous_outcome or None, "duration_ms": c.duration_ms, "error": c.error or None,
              "expected": c.expected, "comparisons": c.comparisons, "actual": c.actual} for c in run.cases.all()]
    return json.dumps({"run": _run_header(run), "cases": cases}, indent=2, default=str).encode()


def export_csv(run: TestRun) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["run", "fixture", "module", "outcome", "change", "previous_outcome", "duration_ms",
                     "differences", "error"])
    for c in run.cases.all():
        differences = "; ".join(f"{r['label']}: expected {r['expected']}, got {r['actual']}"
                                for r in c.comparisons if not r["passed"])
        writer.writerow([run.reference, c.fixture_name, c.module, c.outcome, c.change, c.previous_outcome,
                         c.duration_ms, differences, c.error])
    return ("﻿" + out.getvalue()).encode()  # the byte-order mark makes Excel read UTF-8 correctly


def export_junit(run: TestRun) -> bytes:
    """JUnit XML, the format CI systems (GitHub Actions, Jenkins, Azure DevOps) understand."""
    suite = ET.Element("testsuite", name=f"DocumentLab {run.reference}", tests=str(run.total),
                       failures=str(run.failed), errors=str(run.errors), time=f"{run.duration_ms / 1000:.3f}",
                       timestamp=run.created_at.isoformat())
    for c in run.cases.all():
        case = ET.SubElement(suite, "testcase", classname=f"documentlab.{c.module}", name=c.fixture_name,
                             time=f"{c.duration_ms / 1000:.3f}")
        if c.outcome == CaseResult.FAIL:
            lines = [f"{r['label']}: expected {r['expected']}, got {r['actual']}" for r in c.comparisons if not r["passed"]]
            ET.SubElement(case, "failure", message=lines[0] if lines else "Did not match").text = "\n".join(lines)
        elif c.outcome == CaseResult.ERROR:
            ET.SubElement(case, "error", message=c.error[:200]).text = c.error
    return ET.tostring(suite, encoding="utf-8", xml_declaration=True)
